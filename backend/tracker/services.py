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
    source: Optional[str] = None,
    q: Optional[str] = None,
) -> list[Application]:
    stmt = select(Application)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    if source is not None:
        stmt = stmt.where(Application.source == source)
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
        .options(selectinload(Application.events))
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
    if app.status == Status.applied and app.applied_at is None:
        app.applied_at = now
    session.add(app)
    session.commit()
    session.refresh(app)

    session.add(
        Event(
            application_id=app.id,
            kind=EventKind.created,
            body=f"Добавлено в трекер · статус «{STATUS_LABEL.get(app.status, app.status.value)}»",
            occurred_at=now,
        )
    )
    if app.status == Status.applied:
        session.add(
            Event(
                application_id=app.id,
                kind=EventKind.status_change,
                body=f"Отклик отправлен · {app.source}",
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
        c = channels.setdefault(a.source, {"applied": 0, "interview": 0})
        c["applied"] += 1
        if reached[a.id] >= STATUS_RANK[Status.interview]:
            c["interview"] += 1
    by_channel = [
        {
            "source": src,
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
            "screening": screening,
            "interview": interview,
            "offer": offer,
            "accepted": accepted,
        },
        "conversions": {
            "applied_to_interview": _pct(interview, applied),
            "interview_to_offer": _pct(offer, interview),
            "response_rate": _pct(screening, applied),
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
        dict(company="Avito", title="Senior Backend Engineer (Python)", source="hh.ru",
             status=Status.saved, priority=4, salary_min=400000, salary_max=550000, currency="RUB",
             location="Москва", work_mode="remote", tags=["python", "postgres"]),
        dict(company="Miro", title="Software Engineer, Platform", source="linkedin",
             status=Status.saved, priority=3, salary_min=70000, salary_max=90000, currency="EUR",
             location="Amsterdam", work_mode="hybrid", tags=["go", "kubernetes"]),
        dict(company="Nebius", title="Backend Engineer", source="linkedin", status=Status.applied,
             priority=4, salary_min=75000, salary_max=95000, currency="EUR", location="Belgrade",
             work_mode="hybrid", resume_version="backend-v3", applied_days=3,
             next_action="первый follow-up", next_after=4, tags=["python", "grpc"]),
        dict(company="Wildberries", title="Python Developer", source="company site",
             status=Status.applied, priority=3, salary_min=350000, salary_max=480000, currency="RUB",
             location="Москва", work_mode="onsite", resume_version="backend-v3", applied_days=9,
             next_action="follow-up, тишина", next_after=-2, tags=["python", "django"]),
        dict(company="JetBrains", title="Software Developer, YouTrack", source="referral",
             status=Status.screening, priority=5, salary_min=80000, salary_max=110000, currency="EUR",
             location="Prague", work_mode="hybrid", resume_version="backend-v3", applied_days=5,
             next_action="созвон с рекрутёром", next_after=1,
             contact_name="Anna K.", contact_email="anna@jetbrains.com", tags=["kotlin", "python"]),
        dict(company="Yandex", title="Senior Software Engineer", source="referral",
             status=Status.interview, priority=5, salary_min=380000, salary_max=520000, currency="RUB",
             location="Москва", work_mode="hybrid", resume_version="backend-v3", applied_days=12,
             next_action="тех-интервью (кодинг)", next_after=2,
             contact_name="Мария Иванова", contact_email="m.ivanova@yandex-team.ru",
             contact_url="https://linkedin.com/in/mivanova",
             cover_letter="Здравствуйте, Мария! Меня заинтересовала роль — 6 лет строю "
                          "высоконагруженные сервисы на Python/Go, последние 2 года — event-pipeline "
                          "на 400k RPS. Буду рад обсудить детали.",
             description="Ищем сильного backend-инженера в команду инфраструктуры данных. "
                         "Стек: Python, Go, PostgreSQL, ClickHouse, Kubernetes. Задачи — "
                         "проектирование распределённых сервисов обработки событий с нагрузкой "
                         "до 1М RPS, снижение latency пайплайнов, менторинг. Требуется опыт 5+ лет.",
             job_url="https://yandex.ru/jobs/vacancies/12345", tags=["python", "go", "clickhouse"]),
        dict(company="Toloka", title="ML Platform Engineer", source="linkedin",
             status=Status.interview, priority=4, salary_min=70000, salary_max=90000, currency="EUR",
             location="Remote", work_mode="remote", resume_version="ml-v1", applied_days=8,
             next_action="этап 2 из 3", next_after=3, tags=["python", "ml", "airflow"]),
        dict(company="Datadog", title="Software Engineer, Backend", source="linkedin",
             status=Status.offer, priority=5, salary_min=95000, salary_max=95000, currency="EUR",
             location="Paris", work_mode="hybrid", resume_version="backend-v3", applied_days=21,
             next_action="ответить на оффер", next_after=5, tags=["go", "python"]),
        dict(company="Ozon", title="Backend Engineer", source="hh.ru", status=Status.rejected,
             priority=3, salary_min=300000, salary_max=420000, currency="RUB", location="Москва",
             work_mode="hybrid", resume_version="backend-v2", applied_days=18, reached=Status.screening,
             tags=["go"]),
        dict(company="Notion", title="Software Engineer", source="linkedin", status=Status.ghosted,
             priority=4, salary_min=140000, salary_max=170000, currency="USD", location="Remote (US)",
             work_mode="remote", resume_version="backend-v2", applied_days=27, tags=["typescript"]),
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
        session.add(app)
        session.commit()
        session.refresh(app)

        # Build a plausible timeline for applications that were actually sent.
        if applied_days is not None:
            _seed_timeline(session, app, status, applied_days, reached)
        else:
            session.add(Event(application_id=app.id, kind=EventKind.created,
                              body="Сохранено в wishlist", occurred_at=app.created_at))
        session.commit()
        count += 1

    return count


def _seed_timeline(session: Session, app: Application, status: Status, applied_days: int,
                   reached: Optional[Status]) -> None:
    now = utcnow()

    def at(n: int) -> datetime:
        return now - timedelta(days=n)

    path = [Status.applied, Status.screening, Status.interview, Status.offer]
    target = reached or status
    target_rank = STATUS_RANK.get(target, STATUS_RANK[Status.applied])

    session.add(Event(application_id=app.id, kind=EventKind.status_change,
                      body=f"Отклик отправлен · {app.source}"
                           + (f" · резюме {app.resume_version}" if app.resume_version else ""),
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
                          body="Отказ после скрининга", occurred_at=at(1)))
    elif status == Status.ghosted:
        session.add(Event(application_id=app.id, kind=EventKind.note,
                          body="Нет ответа больше 3 недель — помечено как тишина", occurred_at=at(0)))

    if app.company == "Yandex":
        session.add(Event(application_id=app.id, kind=EventKind.interview,
                          body="Систем-дизайн (75 мин). Проектировали rate-limiter.",
                          occurred_at=at(2)))
        session.add(Event(application_id=app.id, kind=EventKind.note,
                          body="Систем-дизайн прошёл хорошо, дальше кодинг-секция. "
                               "Повторить графовые алгоритмы.", occurred_at=at(0)))
