"""``tracker`` CLI — the primary way to update the tracker from the terminal.

Writes straight to the same SQLite file as the web API through the shared
``tracker.services`` layer, so it works whether or not the server is running.
"""
from __future__ import annotations

import mimetypes
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from tracker import services
from tracker.db import init_db, open_session
from tracker.models import (
    STATUS_LABEL,
    ApplicationCreate,
    ApplicationUpdate,
    EventKind,
    Status,
    WorkMode,
)

app = typer.Typer(help="Personal job-application tracker.", no_args_is_help=True)


@app.callback()
def _bootstrap() -> None:
    init_db()


def _parse_status(value: str) -> Status:
    try:
        return Status(value)
    except ValueError:
        valid = ", ".join(s.value for s in Status)
        raise typer.BadParameter(f"unknown status '{value}'. Allowed: {valid}")


def _fmt_salary(a) -> str:
    if a.salary_min and a.salary_max:
        rng = f"{a.salary_min}–{a.salary_max}" if a.salary_min != a.salary_max else f"{a.salary_min}"
        return f"{rng} {a.currency or ''}".strip()
    return "—"


def _line(a) -> str:
    label = STATUS_LABEL.get(a.status, a.status.value)
    return f"  #{a.id:<3} [{label:<11}] {a.company} — {a.title}  ({a.applied_via})"


def _attach_resume(session, app_id: int, path: Path):
    """Read a resume file from disk and store it against the application."""
    data = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return services.set_resume(
        session, app_id, filename=path.name, content_type=content_type, content=data
    )


# --------------------------------------------------------------------------- #
@app.command()
def init() -> None:
    """Create the database and tables."""
    init_db()
    typer.echo("Database ready.")


@app.command()
def seed(force: bool = typer.Option(False, "--force", help="wipe and recreate the sample data")) -> None:
    """Populate with sample data (matching the mockup)."""
    with open_session() as s:
        n = services.seed(s, force=force)
    typer.echo(f"Seeded {n} samples." if n else "Data already present (use --force).")


@app.command()
def add(
    company: str = typer.Option(..., "--company", "-c"),
    title: str = typer.Option(..., "--title", "-t"),
    company_url: Optional[str] = typer.Option(None, "--company-url", help="the employer's own site / careers page"),
    found_via: Optional[str] = typer.Option(None, "--found-via", help="where you found it: linkedin | hh.ru | aggregator | ..."),
    found_url: Optional[str] = typer.Option(None, "--found-url", help="link to the posting where you found it"),
    applied_via: str = typer.Option("other", "--applied-via", help="how you applied: email | company site | linkedin | ..."),
    applied_ref: Optional[str] = typer.Option(None, "--applied-ref", help="exact apply target — a URL or an email"),
    status: str = typer.Option("saved", "--status"),
    priority: int = typer.Option(3, "--priority", "-p", min=1, max=5),
    salary_min: Optional[int] = typer.Option(None, "--salary-min"),
    salary_max: Optional[int] = typer.Option(None, "--salary-max"),
    currency: Optional[str] = typer.Option(None, "--currency"),
    location: Optional[str] = typer.Option(None, "--location"),
    work_mode: Optional[str] = typer.Option(None, "--work-mode", help="onsite | hybrid | remote"),
    description: Optional[str] = typer.Option(None, "--description"),
    description_file: Optional[Path] = typer.Option(None, "--description-file"),
    tags: Optional[str] = typer.Option(None, "--tags", help="comma-separated"),
    next_action: Optional[str] = typer.Option(None, "--next-action"),
    next_action_date: Optional[str] = typer.Option(None, "--next-action-date", help="YYYY-MM-DD"),
) -> None:
    """Add a job."""
    desc = description or ""
    if description_file:
        desc = description_file.read_text(encoding="utf-8")
    payload = ApplicationCreate(
        company=company,
        title=title,
        company_url=company_url,
        found_via=found_via,
        found_url=found_url,
        applied_via=applied_via,
        applied_ref=applied_ref,
        status=_parse_status(status),
        priority=priority,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        location=location,
        work_mode=WorkMode(work_mode) if work_mode else None,
        description=desc,
        tags=[t.strip() for t in tags.split(",")] if tags else [],
        next_action=next_action,
        next_action_date=date.fromisoformat(next_action_date) if next_action_date else None,
    )
    with open_session() as s:
        a = services.create_application(s, payload)
        typer.echo(f"Added #{a.id}: {a.company} — {a.title}")


@app.command("list")
def list_apps(
    status: Optional[str] = typer.Option(None, "--status"),
    applied_via: Optional[str] = typer.Option(None, "--applied-via"),
) -> None:
    """List jobs."""
    with open_session() as s:
        apps = services.list_applications(
            s, status=_parse_status(status) if status else None, applied_via=applied_via
        )
    if not apps:
        typer.echo("Empty.")
        return
    for a in apps:
        typer.echo(_line(a))
    typer.echo(f"\nTotal: {len(apps)}")


@app.command()
def show(app_id: int = typer.Argument(..., metavar="ID")) -> None:
    """Show a job and its timeline."""
    with open_session() as s:
        try:
            a = services.get_application(s, app_id)
        except services.NotFound:
            typer.secho(f"#{app_id} not found", fg="red")
            raise typer.Exit(1)
        typer.secho(f"#{a.id}  {a.company} — {a.title}", bold=True)
        typer.echo(f"  status:    {STATUS_LABEL.get(a.status, a.status.value)}")
        if a.company_url:
            typer.echo(f"  site:      {a.company_url}")
        typer.echo(f"  applied:   {a.applied_via}" + (f" → {a.applied_ref}" if a.applied_ref else ""))
        if a.found_via or a.found_url:
            found = a.found_via or "—"
            typer.echo(f"  found:     {found}" + (f" ({a.found_url})" if a.found_url else ""))
        typer.echo(f"  priority:  {'★' * a.priority}{'☆' * (5 - a.priority)}")
        typer.echo(f"  salary:    {_fmt_salary(a)}")
        if a.location:
            typer.echo(f"  location:  {a.location} ({a.work_mode.value if a.work_mode else '—'})")
        if a.resume_filename:
            typer.echo(f"  resume:    {a.resume_filename}")
        if a.next_action:
            when = f" — {a.next_action_date}" if a.next_action_date else ""
            typer.echo(f"  next:      {a.next_action}{when}")
        if a.contact_name:
            typer.echo(f"  contact:   {a.contact_name} {a.contact_email or ''}")
        if a.description:
            typer.echo(f"\n  Job:\n    {a.description[:300]}")
        typer.echo("\n  Timeline:")
        for e in a.events:
            when = e.occurred_at.date().isoformat()
            typer.echo(f"    {when}  [{e.kind.value}] {e.body}")


@app.command()
def apply(
    app_id: int = typer.Argument(..., metavar="ID"),
    applied_via: Optional[str] = typer.Option(None, "--applied-via"),
    applied_ref: Optional[str] = typer.Option(None, "--applied-ref", help="exact apply target — a URL or an email"),
    resume_file: Optional[Path] = typer.Option(None, "--resume-file", help="resume file sent"),
    cover_letter: Optional[str] = typer.Option(None, "--cover-letter"),
    cover_letter_file: Optional[Path] = typer.Option(None, "--cover-letter-file"),
) -> None:
    """Mark as applied: sets status to applied and logs what/where you sent."""
    cover = cover_letter
    if cover_letter_file:
        cover = cover_letter_file.read_text(encoding="utf-8")
    # Only patch fields the user actually passed — building the update with explicit
    # Nones would clear any applied_via / applied_ref / cover already on the record.
    updates: dict = {}
    if applied_via is not None:
        updates["applied_via"] = applied_via
    if applied_ref is not None:
        updates["applied_ref"] = applied_ref
    if cover is not None:
        updates["cover_letter"] = cover
    patch = ApplicationUpdate(**updates)
    with open_session() as s:
        try:
            services.update_application(s, app_id, patch)
            if resume_file is not None:
                _attach_resume(s, app_id, resume_file)
            a = services.set_status(s, app_id, Status.applied)
        except services.NotFound:
            typer.secho(f"#{app_id} not found", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{a.id} → Applied ({a.applied_via})")


@app.command()
def status(
    app_id: int = typer.Argument(..., metavar="ID"),
    new_status: str = typer.Argument(..., metavar="STATUS"),
    note: Optional[str] = typer.Option(None, "--note", "-n"),
) -> None:
    """Change status (auto-logs a timeline event)."""
    st = _parse_status(new_status)
    with open_session() as s:
        try:
            a = services.set_status(s, app_id, st, note=note)
        except services.NotFound:
            typer.secho(f"#{app_id} not found", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{a.id} → {STATUS_LABEL.get(a.status, a.status.value)}")


@app.command()
def note(
    app_id: int = typer.Argument(..., metavar="ID"),
    text: str = typer.Argument(...),
) -> None:
    """Add a note to the timeline."""
    with open_session() as s:
        try:
            services.add_event(s, app_id, EventKind.note, body=text)
        except services.NotFound:
            typer.secho(f"#{app_id} not found", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{app_id}: note added")


@app.command("set")
def set_fields(
    app_id: int = typer.Argument(..., metavar="ID"),
    next_action: Optional[str] = typer.Option(None, "--next-action"),
    next_action_date: Optional[str] = typer.Option(None, "--next-action-date", help="YYYY-MM-DD"),
    priority: Optional[int] = typer.Option(None, "--priority", "-p", min=1, max=5),
    contact_name: Optional[str] = typer.Option(None, "--contact-name"),
    contact_email: Optional[str] = typer.Option(None, "--contact-email"),
) -> None:
    """Update individual job fields."""
    patch = ApplicationUpdate(
        next_action=next_action,
        next_action_date=date.fromisoformat(next_action_date) if next_action_date else None,
        priority=priority,
        contact_name=contact_name,
        contact_email=contact_email,
    )
    with open_session() as s:
        try:
            services.update_application(s, app_id, patch)
        except services.NotFound:
            typer.secho(f"#{app_id} not found", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{app_id}: updated")


@app.command()
def resume(
    app_id: int = typer.Argument(..., metavar="ID"),
    path: Optional[Path] = typer.Argument(None, metavar="FILE", help="resume file to attach"),
    remove: bool = typer.Option(False, "--remove", help="detach the current resume"),
) -> None:
    """Attach (or remove) the resume file sent for a job."""
    with open_session() as s:
        try:
            if remove:
                services.delete_resume(s, app_id)
                typer.echo(f"#{app_id}: resume removed")
                return
            if path is None:
                raise typer.BadParameter("give a FILE path to attach, or --remove")
            rf = _attach_resume(s, app_id, path)
        except services.NotFound:
            typer.secho(f"#{app_id} not found", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{app_id}: attached {rf.filename} ({len(rf.content)} bytes)")


@app.command()
def metrics() -> None:
    """Show funnel metrics."""
    with open_session() as s:
        m = services.metrics(s)
    f = m["funnel"]
    c = m["conversions"]
    typer.secho("Funnel", bold=True)
    typer.echo(f"  applied:     {f['applied']}")
    typer.echo(f"  in contact:  {f['screening']}")
    typer.echo(f"  interview:   {f['interview']}")
    typer.echo(f"  offer:       {f['offer']}")
    typer.echo(f"  accepted:    {f['accepted']}")
    typer.secho("\nConversions", bold=True)
    typer.echo(f"  applied → interview:  {c['applied_to_interview']}%")
    typer.echo(f"  interview → offer:    {c['interview_to_offer']}%")
    typer.echo(f"  response rate:        {c['response_rate']}%")
    if m["by_channel"]:
        typer.secho("\nBy channel", bold=True)
        for ch in m["by_channel"]:
            typer.echo(f"  {ch['applied_via']:<14} {ch['interview']}/{ch['applied']} → {ch['rate']}%")
    if m["follow_ups"]:
        typer.secho("\nFollow-ups today", bold=True)
        for fu in m["follow_ups"]:
            tag = f"overdue {fu['overdue_days']}d" if fu["overdue_days"] > 0 else "today"
            typer.echo(f"  #{fu['id']} {fu['company']} — {fu['next_action']} ({tag})")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Run the REST API (for the web UI)."""
    import uvicorn

    uvicorn.run("tracker.api:app", host=host, port=port, reload=reload)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
