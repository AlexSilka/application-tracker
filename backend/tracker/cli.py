"""``tracker`` CLI — the primary way to update the tracker from the terminal.

Writes straight to the same SQLite file as the web API through the shared
``tracker.services`` layer, so it works whether or not the server is running.
"""
from __future__ import annotations

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

app = typer.Typer(help="Персональный трекер откликов на вакансии.", no_args_is_help=True)


@app.callback()
def _bootstrap() -> None:
    init_db()


def _parse_status(value: str) -> Status:
    try:
        return Status(value)
    except ValueError:
        valid = ", ".join(s.value for s in Status)
        raise typer.BadParameter(f"неизвестный статус «{value}». Допустимо: {valid}")


def _fmt_salary(a) -> str:
    if a.salary_min and a.salary_max:
        rng = f"{a.salary_min}–{a.salary_max}" if a.salary_min != a.salary_max else f"{a.salary_min}"
        return f"{rng} {a.currency or ''}".strip()
    return "—"


def _line(a) -> str:
    label = STATUS_LABEL.get(a.status, a.status.value)
    return f"  #{a.id:<3} [{label:<9}] {a.company} — {a.title}  ({a.source})"


# --------------------------------------------------------------------------- #
@app.command()
def init() -> None:
    """Создать БД и таблицы."""
    init_db()
    typer.echo("БД готова.")


@app.command()
def seed(force: bool = typer.Option(False, "--force", help="стереть и пересоздать примеры")) -> None:
    """Наполнить примерами (как в макете)."""
    with open_session() as s:
        n = services.seed(s, force=force)
    typer.echo(f"Добавлено примеров: {n}" if n else "Данные уже есть (используй --force).")


@app.command()
def add(
    company: str = typer.Option(..., "--company", "-c"),
    title: str = typer.Option(..., "--title", "-t"),
    url: Optional[str] = typer.Option(None, "--url"),
    source: str = typer.Option("other", "--source", help="linkedin | hh.ru | referral | ..."),
    status: str = typer.Option("saved", "--status"),
    priority: int = typer.Option(3, "--priority", "-p", min=1, max=5),
    salary_min: Optional[int] = typer.Option(None, "--salary-min"),
    salary_max: Optional[int] = typer.Option(None, "--salary-max"),
    currency: Optional[str] = typer.Option(None, "--currency"),
    location: Optional[str] = typer.Option(None, "--location"),
    work_mode: Optional[str] = typer.Option(None, "--work-mode", help="onsite | hybrid | remote"),
    description: Optional[str] = typer.Option(None, "--description"),
    description_file: Optional[Path] = typer.Option(None, "--description-file"),
    resume: Optional[str] = typer.Option(None, "--resume", help="версия отправленного резюме"),
    tags: Optional[str] = typer.Option(None, "--tags", help="через запятую"),
    next_action: Optional[str] = typer.Option(None, "--next-action"),
    next_action_date: Optional[str] = typer.Option(None, "--next-action-date", help="YYYY-MM-DD"),
) -> None:
    """Добавить вакансию."""
    desc = description or ""
    if description_file:
        desc = description_file.read_text(encoding="utf-8")
    payload = ApplicationCreate(
        company=company,
        title=title,
        job_url=url,
        source=source,
        status=_parse_status(status),
        priority=priority,
        salary_min=salary_min,
        salary_max=salary_max,
        currency=currency,
        location=location,
        work_mode=WorkMode(work_mode) if work_mode else None,
        description=desc,
        resume_version=resume,
        tags=[t.strip() for t in tags.split(",")] if tags else [],
        next_action=next_action,
        next_action_date=date.fromisoformat(next_action_date) if next_action_date else None,
    )
    with open_session() as s:
        a = services.create_application(s, payload)
        typer.echo(f"Добавлено #{a.id}: {a.company} — {a.title}")


@app.command("list")
def list_apps(
    status: Optional[str] = typer.Option(None, "--status"),
    source: Optional[str] = typer.Option(None, "--source"),
) -> None:
    """Список вакансий."""
    with open_session() as s:
        apps = services.list_applications(
            s, status=_parse_status(status) if status else None, source=source
        )
    if not apps:
        typer.echo("Пусто.")
        return
    for a in apps:
        typer.echo(_line(a))
    typer.echo(f"\nВсего: {len(apps)}")


@app.command()
def show(app_id: int = typer.Argument(..., metavar="ID")) -> None:
    """Показать вакансию и её таймлайн."""
    with open_session() as s:
        try:
            a = services.get_application(s, app_id)
        except services.NotFound:
            typer.secho(f"#{app_id} не найдено", fg="red")
            raise typer.Exit(1)
        typer.secho(f"#{a.id}  {a.company} — {a.title}", bold=True)
        typer.echo(f"  статус:     {STATUS_LABEL.get(a.status, a.status.value)}")
        typer.echo(f"  канал:      {a.source}")
        typer.echo(f"  приоритет:  {'★' * a.priority}{'☆' * (5 - a.priority)}")
        typer.echo(f"  зарплата:   {_fmt_salary(a)}")
        if a.location:
            typer.echo(f"  локация:    {a.location} ({a.work_mode.value if a.work_mode else '—'})")
        if a.resume_version:
            typer.echo(f"  резюме:     {a.resume_version}")
        if a.next_action:
            when = f" — {a.next_action_date}" if a.next_action_date else ""
            typer.echo(f"  next:       {a.next_action}{when}")
        if a.contact_name:
            typer.echo(f"  контакт:    {a.contact_name} {a.contact_email or ''}")
        if a.description:
            typer.echo(f"\n  Вакансия:\n    {a.description[:300]}")
        typer.echo("\n  Таймлайн:")
        for e in a.events:
            when = e.occurred_at.date().isoformat()
            typer.echo(f"    {when}  [{e.kind.value}] {e.body}")


@app.command()
def apply(
    app_id: int = typer.Argument(..., metavar="ID"),
    source: Optional[str] = typer.Option(None, "--source"),
    resume: Optional[str] = typer.Option(None, "--resume"),
    cover_letter: Optional[str] = typer.Option(None, "--cover-letter"),
    cover_letter_file: Optional[Path] = typer.Option(None, "--cover-letter-file"),
) -> None:
    """Отметить как поданное: ставит статус applied и логирует, что и куда отправили."""
    cover = cover_letter
    if cover_letter_file:
        cover = cover_letter_file.read_text(encoding="utf-8")
    patch = ApplicationUpdate(
        source=source, resume_version=resume, cover_letter=cover
    )
    with open_session() as s:
        try:
            services.update_application(s, app_id, patch)
            a = services.set_status(s, app_id, Status.applied)
        except services.NotFound:
            typer.secho(f"#{app_id} не найдено", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{a.id} → Отклик отправлен ({a.source}, резюме {a.resume_version or '—'})")


@app.command()
def status(
    app_id: int = typer.Argument(..., metavar="ID"),
    new_status: str = typer.Argument(..., metavar="STATUS"),
    note: Optional[str] = typer.Option(None, "--note", "-n"),
) -> None:
    """Сменить статус (с авто-событием в таймлайне)."""
    st = _parse_status(new_status)
    with open_session() as s:
        try:
            a = services.set_status(s, app_id, st, note=note)
        except services.NotFound:
            typer.secho(f"#{app_id} не найдено", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{a.id} → {STATUS_LABEL.get(a.status, a.status.value)}")


@app.command()
def note(
    app_id: int = typer.Argument(..., metavar="ID"),
    text: str = typer.Argument(...),
) -> None:
    """Добавить заметку в таймлайн."""
    with open_session() as s:
        try:
            services.add_event(s, app_id, EventKind.note, body=text)
        except services.NotFound:
            typer.secho(f"#{app_id} не найдено", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{app_id}: заметка добавлена")


@app.command("set")
def set_fields(
    app_id: int = typer.Argument(..., metavar="ID"),
    next_action: Optional[str] = typer.Option(None, "--next-action"),
    next_action_date: Optional[str] = typer.Option(None, "--next-action-date", help="YYYY-MM-DD"),
    priority: Optional[int] = typer.Option(None, "--priority", "-p", min=1, max=5),
    resume: Optional[str] = typer.Option(None, "--resume"),
    contact_name: Optional[str] = typer.Option(None, "--contact-name"),
    contact_email: Optional[str] = typer.Option(None, "--contact-email"),
) -> None:
    """Обновить отдельные поля вакансии."""
    patch = ApplicationUpdate(
        next_action=next_action,
        next_action_date=date.fromisoformat(next_action_date) if next_action_date else None,
        priority=priority,
        resume_version=resume,
        contact_name=contact_name,
        contact_email=contact_email,
    )
    with open_session() as s:
        try:
            services.update_application(s, app_id, patch)
        except services.NotFound:
            typer.secho(f"#{app_id} не найдено", fg="red")
            raise typer.Exit(1)
    typer.echo(f"#{app_id}: обновлено")


@app.command()
def metrics() -> None:
    """Показать метрики воронки."""
    with open_session() as s:
        m = services.metrics(s)
    f = m["funnel"]
    c = m["conversions"]
    typer.secho("Воронка", bold=True)
    typer.echo(f"  подано:    {f['applied']}")
    typer.echo(f"  скрининг:  {f['screening']}")
    typer.echo(f"  интервью:  {f['interview']}")
    typer.echo(f"  оффер:     {f['offer']}")
    typer.echo(f"  принят:    {f['accepted']}")
    typer.secho("\nКонверсии", bold=True)
    typer.echo(f"  отклик → интервью:  {c['applied_to_interview']}%")
    typer.echo(f"  интервью → оффер:   {c['interview_to_offer']}%")
    typer.echo(f"  response rate:      {c['response_rate']}%")
    if m["by_channel"]:
        typer.secho("\nПо каналам", bold=True)
        for ch in m["by_channel"]:
            typer.echo(f"  {ch['source']:<14} {ch['interview']}/{ch['applied']} → {ch['rate']}%")
    if m["follow_ups"]:
        typer.secho("\nFollow-up сегодня", bold=True)
        for fu in m["follow_ups"]:
            tag = f"просрочен {fu['overdue_days']}д" if fu["overdue_days"] > 0 else "сегодня"
            typer.echo(f"  #{fu['id']} {fu['company']} — {fu['next_action']} ({tag})")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Запустить REST API (для веб-интерфейса)."""
    import uvicorn

    uvicorn.run("tracker.api:app", host=host, port=port, reload=reload)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
