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


class Direction(str, Enum):
    outbound = "outbound"  # I found the posting and applied
    inbound = "inbound"  # a recruiter / employer reached out to me


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

# Human-readable labels for CLI output, /api/meta and auto-generated event text.
# `screening` shows as "In Contact" per the design (a substantive employer reply).
STATUS_LABEL: dict[Status, str] = {
    Status.saved: "Saved",
    Status.applied: "Applied",
    Status.screening: "In Contact",
    Status.interview: "Interview",
    Status.offer: "Offer",
    Status.accepted: "Accepted",
    Status.rejected: "Rejected",
    Status.withdrawn: "Withdrawn",
    Status.ghosted: "Ghosted",
}

# A channel has two facets we track on separate fields (see Application):
#   found_via   — where the job was first spotted (first-touch / discovery surface)
#   applied_via — how the application was actually submitted (last-touch; the funnel
#                 groups on this, so it stays a small, stable set of apply mechanisms)
# Both are suggested-not-enforced: the column is a plain string and these lists just
# feed the dropdowns. A mixed RU + international search, so both span both worlds.
FOUND_VIA = [
    "linkedin",
    "hh.ru",
    "indeed",
    "aggregator",
    "telegram",
    "google",
    "referral",
    "company site",
    "other",
]
APPLIED_VIA = [
    "linkedin",
    "email",
    "company site",
    "hh.ru",
    "referral",
    "recruiter",
    "other",
]


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    company: str
    company_url: Optional[str] = None  # the employer's own site / careers page
    title: str
    description: str = ""  # full job description — we keep the JD verbatim

    # WHERE we found it (first-touch): the discovery channel + the listing link we saw.
    found_via: Optional[str] = None  # linkedin | hh.ru | aggregator | referral | ...
    found_url: Optional[str] = None  # link to the posting where we found it

    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None

    # HOW we applied (last-touch): the channel the funnel groups on + the exact
    # destination we sent it to (a company-site URL or an email address).
    applied_via: str = "other"  # email | company site | linkedin | referral | ...
    applied_ref: Optional[str] = None  # exact apply target — a URL or an email

    # Did I reach out (outbound) or did a recruiter / employer contact me (inbound)?
    direction: Direction = Field(default=Direction.outbound)

    status: Status = Field(default=Status.saved, index=True)

    cover_letter: Optional[str] = None  # WHAT we wrote — cover letter / message text

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

    # WHAT we sent — the actual resume file, one per application (upload replaces).
    resume: Optional["ResumeFile"] = Relationship(
        back_populates="application",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )

    @property
    def resume_filename(self) -> Optional[str]:
        """Name of the attached resume file, if any — surfaced on ApplicationDetail."""
        return self.resume.filename if self.resume else None


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="application.id", index=True)
    kind: EventKind = Field(default=EventKind.note)
    body: str = ""  # free text: the message we wrote, a note, interview feedback
    meta: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    occurred_at: datetime = Field(default_factory=utcnow)

    application: Optional[Application] = Relationship(back_populates="events")


class ResumeFile(SQLModel, table=True):
    """The resume file sent for a given application — the ground truth of what a
    recruiter actually received. Stored as a BLOB in the same SQLite file so the
    whole tracker stays a single, copy-to-back-up artifact. The application id is
    the primary key, enforcing one resume per job (a new upload replaces it).
    Kept in its own table so listing the board never drags the file bytes along.
    """

    application_id: int = Field(foreign_key="application.id", primary_key=True)
    filename: str
    content_type: str = "application/octet-stream"
    content: bytes
    uploaded_at: datetime = Field(default_factory=utcnow)

    application: Optional[Application] = Relationship(back_populates="resume")


# --------------------------------------------------------------------------- #
# API schemas (request / response shapes distinct from the tables)
# --------------------------------------------------------------------------- #
class ApplicationCreate(SQLModel):
    company: str
    company_url: Optional[str] = None
    title: str
    description: str = ""
    found_via: Optional[str] = None
    found_url: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    applied_via: str = "other"
    applied_ref: Optional[str] = None
    direction: Direction = Direction.outbound
    status: Status = Status.saved
    cover_letter: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_url: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
    tags: list[str] = Field(default_factory=list)


class ApplicationUpdate(SQLModel):
    company: Optional[str] = None
    company_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    found_via: Optional[str] = None
    found_url: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    applied_via: Optional[str] = None
    applied_ref: Optional[str] = None
    direction: Optional[Direction] = None
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
    company_url: Optional[str]
    title: str
    description: str
    found_via: Optional[str]
    found_url: Optional[str]
    location: Optional[str]
    work_mode: Optional[WorkMode]
    salary_min: Optional[int]
    salary_max: Optional[int]
    currency: Optional[str]
    applied_via: str
    applied_ref: Optional[str]
    direction: Direction
    status: Status
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
    resume_filename: Optional[str] = None  # attached resume file, if any
    events: list[EventRead] = Field(default_factory=list)
