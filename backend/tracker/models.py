"""Domain model: Application (core) + Event (timeline) + enums.

Enum member names deliberately equal their values so SQLAlchemy stores the
human-readable string regardless of whether it serialises by name or value.
"""
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlmodel import JSON, Column, Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Status(str, Enum):
    saved = "saved"
    applied = "applied"
    screening = "screening"
    interview = "interview"
    offer = "offer"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"
    ghosted = "ghosted"


class WorkMode(str, Enum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"


class EventKind(str, Enum):
    created = "created"
    status_change = "status_change"
    note = "note"
    follow_up = "follow_up"
    interview = "interview"
    email_sent = "email_sent"
    offer = "offer"
    rejection = "rejection"


# Ordered progress rank along the happy path. Terminal states (rejected /
# withdrawn / ghosted) have no rank of their own — how far they got is derived
# from their status-change history instead.
STATUS_RANK: dict[Status, int] = {
    Status.saved: 0,
    Status.applied: 1,
    Status.screening: 2,
    Status.interview: 3,
    Status.offer: 4,
    Status.accepted: 5,
}
RANK_BY_VALUE: dict[str, int] = {s.value: r for s, r in STATUS_RANK.items()}

ACTIVE_STATUSES = [Status.saved, Status.applied, Status.screening, Status.interview, Status.offer]
TERMINAL_STATUSES = [Status.accepted, Status.rejected, Status.withdrawn, Status.ghosted]

# Russian labels for CLI output and auto-generated event text.
STATUS_LABEL: dict[Status, str] = {
    Status.saved: "Сохранено",
    Status.applied: "Отклик",
    Status.screening: "Скрининг",
    Status.interview: "Интервью",
    Status.offer: "Оффер",
    Status.accepted: "Принят",
    Status.rejected: "Отказ",
    Status.withdrawn: "Снят",
    Status.ghosted: "Тишина",
}

# Channels for a mixed RU + international search (chosen by the user).
SOURCES = [
    "linkedin",
    "hh.ru",
    "indeed",
    "company site",
    "referral",
    "recruiter",
    "telegram",
    "email",
    "other",
]


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    company: str
    title: str
    description: str = ""  # full job description — we keep the JD verbatim
    job_url: Optional[str] = None

    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None

    source: str = "other"  # WHERE we applied
    status: Status = Field(default=Status.saved, index=True)
    priority: int = 3  # 1..5, how much we want it

    resume_version: Optional[str] = None  # WHAT we sent — resume label/version
    cover_letter: Optional[str] = None    # WHAT we wrote — cover letter / message text

    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_url: Optional[str] = None

    next_action: Optional[str] = None
    next_action_date: Optional[date] = None

    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    applied_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    events: list["Event"] = Relationship(
        back_populates="application",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "Event.occurred_at.desc()",
        },
    )


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    kind: EventKind = Field(default=EventKind.note)
    body: str = ""  # free text: the message we wrote, a note, interview feedback
    meta: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utcnow)

    application: Optional[Application] = Relationship(back_populates="events")


# --------------------------------------------------------------------------- #
# API schemas (request / response shapes distinct from the tables)
# --------------------------------------------------------------------------- #
class ApplicationCreate(SQLModel):
    company: str
    title: str
    description: str = ""
    job_url: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    source: str = "other"
    status: Status = Status.saved
    priority: int = 3
    resume_version: Optional[str] = None
    cover_letter: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_url: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    tags: list[str] = Field(default_factory=list)


class ApplicationUpdate(SQLModel):
    company: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    job_url: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    source: Optional[str] = None
    priority: Optional[int] = None
    resume_version: Optional[str] = None
    cover_letter: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_url: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    tags: Optional[list[str]] = None


class StatusChange(SQLModel):
    status: Status
    note: Optional[str] = None


class EventCreate(SQLModel):
    kind: EventKind = EventKind.note
    body: str = ""
    meta: Optional[dict[str, Any]] = None


class EventRead(SQLModel):
    id: int
    application_id: int
    kind: EventKind
    body: str
    meta: Optional[dict[str, Any]] = None
    occurred_at: datetime


class ApplicationRead(SQLModel):
    id: int
    company: str
    title: str
    description: str
    job_url: Optional[str]
    location: Optional[str]
    work_mode: Optional[WorkMode]
    salary_min: Optional[int]
    salary_max: Optional[int]
    currency: Optional[str]
    source: str
    status: Status
    priority: int
    resume_version: Optional[str]
    cover_letter: Optional[str]
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_url: Optional[str]
    next_action: Optional[str]
    next_action_date: Optional[date]
    tags: list[str]
    applied_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ApplicationDetail(ApplicationRead):
    events: list[EventRead] = Field(default_factory=list)
