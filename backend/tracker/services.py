"""Service layer — the single source of business logic.

Both the REST API (``tracker.api``) and the CLI (``tracker.cli``) call these
functions so behaviour never diverges between the two surfaces.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from tracker.models import (
    RANK_BY_VALUE,
    STATUS_LABEL,
    STATUS_RANK,
    TERMINAL_STATUSES,
    Application,
    ApplicationCreate,
    ApplicationUpdate,
    Event,
    EventKind,
    ResumeFile,
    Status,
    utcnow,
)


class NotFound(Exception):
    """Raised when an application id does not exist."""


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def list_applications(
    session: Session,
    status: Optional[Status] = None,
    applied_via: Optional[str] = None,
    q: Optional[str] = None,
) -> list[Application]:
    stmt = select(Application)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    if applied_via is not None:
        stmt = stmt.where(Application.applied_via == applied_via)
    stmt = stmt.order_by(Application.updated_at.desc())
    apps = list(session.exec(stmt).all())
    if q:
        needle = q.lower()
        apps = [
            a
            for a in apps
            if needle in a.company.lower()
            or needle in a.title.lower()
            or needle in (a.description or "").lower()
        ]
    return apps


def get_application(session: Session, app_id: int) -> Application:
    app = session.exec(
        select(Application)
        .where(Application.id == app_id)
        .options(selectinload(Application.events), selectinload(Application.resume))
    ).first()
    if app is None:
        raise NotFound(f"application {app_id} not found")
    return app


def _require(session: Session, app_id: int) -> Application:
    app = session.get(Application, app_id)
    if app is None:
        raise NotFound(f"application {app_id} not found")
    return app


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #
def create_application(session: Session, data: ApplicationCreate) -> Application:
    app = Application.model_validate(data)
    now = utcnow()
    app.created_at = now
    app.updated_at = now
    app.status_changed_at = now
    if app.status == Status.applied and app.applied_at is None:
        app.applied_at = now
    session.add(app)
    session.commit()
    session.refresh(app)

    session.add(
        Event(
            application_id=app.id,
            kind=EventKind.created,
            body=f"Added to tracker · status: {STATUS_LABEL.get(app.status, app.status.value)}",
            occurred_at=now,
        )
    )
    if app.status == Status.applied:
        session.add(
            Event(
                application_id=app.id,
                kind=EventKind.status_change,
                body=f"Applied · {app.applied_via}",
                meta={"from": Status.saved.value, "to": Status.applied.value},
                occurred_at=now,
            )
        )
    session.commit()
    session.refresh(app)
    return app


def update_application(session: Session, app_id: int, patch: ApplicationUpdate) -> Application:
    app = _require(session, app_id)
    values = patch.model_dump(exclude_unset=True)
    for key, val in values.items():
        setattr(app, key, val)
    app.updated_at = utcnow()
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def set_status(
    session: Session,
    app_id: int,
    new_status: Status,
    note: Optional[str] = None,
    at: Optional[datetime] = None,
) -> Application:
    app = _require(session, app_id)
    now = at or utcnow()
    old = app.status
    app.status = new_status
    app.updated_at = now
    if new_status == Status.applied and app.applied_at is None:
        app.applied_at = now

    if old != new_status:
        app.status_changed_at = now
        session.add(
            Event(
                application_id=app_id,
                kind=EventKind.status_change,
                body=f"{STATUS_LABEL.get(old, old.value)} → {STATUS_LABEL.get(new_status, new_status.value)}",
                meta={"from": old.value, "to": new_status.value},
                occurred_at=now,
            )
        )
    if note:
        session.add(
            Event(application_id=app_id, kind=EventKind.note, body=note, occurred_at=now)
        )
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def add_event(
    session: Session,
    app_id: int,
    kind: EventKind,
    body: str = "",
    meta: Optional[dict] = None,
    at: Optional[datetime] = None,
) -> Event:
    _require(session, app_id)
    ev = Event(
        application_id=app_id,
        kind=kind,
        body=body,
        meta=meta,
        occurred_at=at or utcnow(),
    )
    session.add(ev)
    # Touch the parent so board ordering reflects the latest activity.
    app = session.get(Application, app_id)
    app.updated_at = ev.occurred_at
    session.add(app)
    session.commit()
    session.refresh(ev)
    return ev


def delete_application(session: Session, app_id: int) -> None:
    app = _require(session, app_id)
    session.delete(app)
    session.commit()


# --------------------------------------------------------------------------- #
# Resume file (the actual document sent — stored as a BLOB, one per application)
# --------------------------------------------------------------------------- #
def set_resume(
    session: Session, app_id: int, filename: str, content_type: str, content: bytes
) -> ResumeFile:
    """Attach or replace the resume file for an application."""
    app = _require(session, app_id)
    now = utcnow()
    rf = session.get(ResumeFile, app_id)
    if rf is None:
        rf = ResumeFile(
            application_id=app_id,
            filename=filename,
            content_type=content_type,
            content=content,
            uploaded_at=now,
        )
    else:
        rf.filename = filename
        rf.content_type = content_type
        rf.content = content
        rf.uploaded_at = now
    session.add(rf)
    app.updated_at = now  # attaching a file counts as activity — float the card up
    session.add(app)
    session.commit()
    session.refresh(rf)
    return rf


def get_resume(session: Session, app_id: int) -> Optional[ResumeFile]:
    """Return the stored resume file for download, or None if none is attached."""
    return session.get(ResumeFile, app_id)


def delete_resume(session: Session, app_id: int) -> None:
    _require(session, app_id)
    rf = session.get(ResumeFile, app_id)
    if rf is not None:
        session.delete(rf)
        session.commit()


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _reached_rank(app: Application) -> int:
    """How far this application ever got along the happy path.

    Uses status-change history so an application rejected *after* an interview
    still counts toward the interview stage of the funnel.
    """
    ranks = [STATUS_RANK.get(app.status, -1)]
    if app.applied_at is not None:
        ranks.append(STATUS_RANK[Status.applied])
    for ev in app.events:
        if ev.kind == EventKind.status_change and ev.meta:
            to = ev.meta.get("to")
            if to in RANK_BY_VALUE:
                ranks.append(RANK_BY_VALUE[to])
    return max(ranks)


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def metrics(session: Session) -> dict:
    apps = session.exec(
        select(Application).options(selectinload(Application.events))
    ).all()

    total = len(apps)
    reached = {a.id: _reached_rank(a) for a in apps}
    applied = sum(1 for r in reached.values() if r >= STATUS_RANK[Status.applied])
    in_contact = sum(1 for r in reached.values() if r >= STATUS_RANK[Status.in_contact])
    screening = sum(1 for r in reached.values() if r >= STATUS_RANK[Status.screening])
    interview = sum(1 for r in reached.values() if r >= STATUS_RANK[Status.interview])
    offer = sum(1 for r in reached.values() if r >= STATUS_RANK[Status.offer])
    accepted = sum(1 for a in apps if a.status == Status.accepted)
    active = sum(1 for a in apps if a.status not in TERMINAL_STATUSES and a.status != Status.saved)

    # per-channel conversion (applied -> interview)
    channels: dict[str, dict] = {}
    for a in apps:
        if reached[a.id] < STATUS_RANK[Status.applied]:
            continue
        c = channels.setdefault(a.applied_via, {"applied": 0, "interview": 0})
        c["applied"] += 1
        if reached[a.id] >= STATUS_RANK[Status.interview]:
            c["interview"] += 1
    by_channel = [
        {
            "applied_via": src,
            "applied": c["applied"],
            "interview": c["interview"],
            "rate": _pct(c["interview"], c["applied"]),
        }
        for src, c in sorted(channels.items(), key=lambda kv: kv[1]["applied"], reverse=True)
    ]

    today = date.today()
    follow_ups = [
        {
            "id": a.id,
            "company": a.company,
            "title": a.title,
            "next_action": a.next_action,
            "next_action_date": a.next_action_date.isoformat() if a.next_action_date else None,
            "overdue_days": (today - a.next_action_date).days if a.next_action_date else 0,
        }
        for a in apps
        if a.next_action_date is not None
        and a.next_action_date <= today
        and a.status not in TERMINAL_STATUSES
    ]
    follow_ups.sort(key=lambda f: f["overdue_days"], reverse=True)

    return {
        "total": total,
        "active": active,
        "offers": sum(1 for a in apps if a.status == Status.offer),
        "funnel": {
            "applied": applied,
            "in_contact": in_contact,
            "screening": screening,
            "interview": interview,
            "offer": offer,
            "accepted": accepted,
        },
        "conversions": {
            "applied_to_interview": _pct(interview, applied),
            "interview_to_offer": _pct(offer, interview),
            "response_rate": _pct(in_contact, applied),
        },
        "by_channel": by_channel,
        "follow_ups": follow_ups,
    }


# --------------------------------------------------------------------------- #
# Seed data (mirrors the design mockup so the UI has content immediately)
# --------------------------------------------------------------------------- #
def seed(session: Session, force: bool = False) -> int:
    existing = session.exec(select(Application)).first()
    if existing is not None and not force:
        return 0
    if force:
        for a in session.exec(select(Application)).all():
            session.delete(a)
        session.commit()

    now = utcnow()

    def days_ago(n: int) -> datetime:
        return now - timedelta(days=n)

    samples = [
        dict(company="Avito", title="Senior Backend Engineer (Python)", applied_via="hh.ru",
             status=Status.saved, salary_min=400000, salary_max=550000, currency="RUB",
             location="Moscow", work_mode="remote", tags=["python", "postgres"]),
        dict(company="Miro", title="Software Engineer, Platform", applied_via="linkedin",
             status=Status.saved, salary_min=70000, salary_max=90000, currency="EUR",
             location="Amsterdam", work_mode="hybrid", tags=["go", "kubernetes"]),
        dict(company="Nebius", title="Backend Engineer",
             found_via="linkedin", applied_via="linkedin",
             applied_ref="https://linkedin.com/jobs/view/3901847221", status=Status.applied,
             salary_min=75000, salary_max=95000, currency="EUR", location="Belgrade",
             work_mode="hybrid", applied_days=3,
             next_action="first follow-up", next_after=4, tags=["python", "grpc"]),
        dict(company="Wildberries", title="Python Developer",
             found_via="hh.ru", found_url="https://hh.ru/vacancy/88451020",
             applied_via="company site", applied_ref="https://career.wildberries.ru/vacancy/1042",
             status=Status.applied, salary_min=350000, salary_max=480000, currency="RUB",
             location="Moscow", work_mode="onsite", applied_days=9,
             next_action="follow-up — no reply", next_after=-2, tags=["python", "django"]),
        dict(company="JetBrains", title="Software Developer, YouTrack", applied_via="referral",
             status=Status.in_contact, salary_min=80000, salary_max=110000, currency="EUR",
             location="Prague", work_mode="hybrid", applied_days=5,
             next_action="recruiter call", next_after=1,
             contact_name="Anna K.", contact_email="anna@jetbrains.com", tags=["kotlin", "python"]),
        dict(company="Yandex", title="Senior Software Engineer", applied_via="referral",
             status=Status.interview, salary_min=380000, salary_max=520000, currency="RUB",
             location="Moscow", work_mode="hybrid", applied_days=12,
             next_action="tech interview (coding)", next_after=2,
             contact_name="Maria Ivanova", contact_email="m.ivanova@yandex-team.ru",
             contact_url="https://linkedin.com/in/mivanova",
             cover_letter="Hi Maria! I'm interested in the role — I've built high-load services "
                          "in Python/Go for 6 years, the last 2 on an event pipeline at 400k RPS. "
                          "Happy to discuss details.",
             description="Looking for a strong backend engineer for the data infrastructure team. "
                         "Stack: Python, Go, PostgreSQL, ClickHouse, Kubernetes. You'll design "
                         "distributed event-processing services handling up to 1M RPS, cut pipeline "
                         "latency, and mentor. 5+ years of experience required.",
             found_via="referral", found_url="https://yandex.ru/jobs/vacancies/12345",
             tags=["python", "go", "clickhouse"]),
        dict(company="Toloka", title="ML Platform Engineer", applied_via="linkedin",
             status=Status.interview, salary_min=70000, salary_max=90000, currency="EUR",
             location="Remote", work_mode="remote", applied_days=8,
             next_action="stage 2 of 3", next_after=3, tags=["python", "ml", "airflow"]),
        dict(company="Datadog", title="Software Engineer, Backend", applied_via="linkedin",
             status=Status.offer, salary_min=95000, salary_max=95000, currency="EUR",
             location="Paris", work_mode="hybrid", applied_days=21,
             next_action="reply to the offer", next_after=5, tags=["go", "python"]),
        dict(company="Ozon", title="Backend Engineer", company_url="https://job.ozon.ru",
             found_via="aggregator", found_url="https://gorod.work/vacancy/ozon-backend-2291",
             applied_via="email", applied_ref="jobs@ozon.ru", status=Status.rejected,
             salary_min=300000, salary_max=420000, currency="RUB", location="Moscow",
             work_mode="hybrid", applied_days=18, reached=Status.in_contact,
             tags=["go"]),
        dict(company="Notion", title="Software Engineer", applied_via="linkedin", status=Status.ghosted,
             salary_min=140000, salary_max=170000, currency="USD", location="Remote (US)",
             work_mode="remote", applied_days=27, tags=["typescript"]),
    ]

    count = 0
    for s in samples:
        applied_days = s.pop("applied_days", None)
        next_after = s.pop("next_after", None)
        reached = s.pop("reached", None)
        tags = s.pop("tags", [])
        status = s["status"]

        app = Application(**{k: v for k, v in s.items()}, tags=tags)
        if applied_days is not None:
            app.applied_at = days_ago(applied_days)
            app.created_at = days_ago(applied_days)
        else:
            app.created_at = days_ago(1)
        if next_after is not None:
            app.next_action_date = (now + timedelta(days=next_after)).date()
        app.updated_at = now
        app.status_changed_at = app.created_at  # entered its status when created; refined below if it moved
        session.add(app)
        session.commit()
        session.refresh(app)

        # Build a plausible timeline for applications that were actually sent.
        if applied_days is not None:
            _seed_timeline(session, app, status, applied_days, reached)
        else:
            session.add(Event(application_id=app.id, kind=EventKind.created,
                              body="Saved to wishlist", occurred_at=app.created_at))
        session.commit()

        # The card entered its current status at its latest status-change (or at
        # creation, for cards that never moved) — same rule the badge reads.
        session.refresh(app)
        changes = [e.occurred_at for e in app.events if e.kind == EventKind.status_change]
        if changes:
            app.status_changed_at = max(changes)
            session.add(app)
            session.commit()
        count += 1

    return count


def _seed_timeline(session: Session, app: Application, status: Status, applied_days: int,
                   reached: Optional[Status]) -> None:
    now = utcnow()

    def at(n: int) -> datetime:
        return now - timedelta(days=n)

    path = [Status.applied, Status.in_contact, Status.screening, Status.interview, Status.offer]
    target = reached or status
    target_rank = STATUS_RANK.get(target, STATUS_RANK[Status.applied])

    session.add(Event(application_id=app.id, kind=EventKind.status_change,
                      body=f"Applied · {app.applied_via}",
                      meta={"from": Status.saved.value, "to": Status.applied.value},
                      occurred_at=at(applied_days)))

    step = max(applied_days // (target_rank + 1), 1)
    prev = Status.applied
    for stage in path[1:]:
        if STATUS_RANK[stage] > target_rank:
            break
        day = applied_days - step * STATUS_RANK[stage]
        session.add(Event(application_id=app.id, kind=EventKind.status_change,
                          body=f"{STATUS_LABEL[prev]} → {STATUS_LABEL[stage]}",
                          meta={"from": prev.value, "to": stage.value}, occurred_at=at(day)))
        prev = stage

    if status == Status.rejected:
        session.add(Event(application_id=app.id, kind=EventKind.rejection,
                          body="Rejected after screening", occurred_at=at(1)))
    elif status == Status.ghosted:
        session.add(Event(application_id=app.id, kind=EventKind.note,
                          body="No reply for over 3 weeks — marked as ghosted", occurred_at=at(0)))

    if app.company == "Yandex":
        session.add(Event(application_id=app.id, kind=EventKind.interview,
                          body="System design (75 min). Designed a rate limiter.",
                          occurred_at=at(2)))
        session.add(Event(application_id=app.id, kind=EventKind.note,
                          body="System design went well; a coding section is next. "
                               "Review graph algorithms.", occurred_at=at(0)))
