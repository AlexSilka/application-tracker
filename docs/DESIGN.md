# Application Tracker — Design Doc

A personal job-application tracker. Single user (you). Primary scenario — running
locally; for demos the same code runs on a server as a single process behind a
public URL (see §6, "Running: local and server"). Key trait: **the tracker is
updated not only by you through the web UI, but also by me (Claude) — via
CLI/API**, so it has two equal entry points on top of one logic layer.

---

## 1. TL;DR

- **What**: board (Kanban) + table + job detail card + funnel dashboard.
- **Stack**: Python (FastAPI + SQLite) — backend, React + TypeScript (Vite) — frontend.
- **Statuses**: `saved → applied → screening → interview → offer → accepted`,
  plus terminal `rejected / withdrawn / ghosted`.
- **We store per job**: the JD itself (title + full description), **where** we
  applied (channel), **what** we sent (resume version + cover letter / message
  text), an event timeline, recruiter contact, next action.
- **How I log**: the `tracker` CLI (works without a running server, writes straight
  to SQLite through the same service layer as the REST API).

---

## 2. What existing trackers do (research)

Looked at Teal, Huntr, Simplify, ApplyArc, JobShinobi — the gist:

| Tool | Core idea | What we borrow |
|-----------|--------------|--------------|
| **Huntr** | Kanban board `wishlist → applied → interview → offer → rejected`, CRM layer | board as the main view, drag-and-drop status changes |
| **Teal** | Table + funnel overview on top, resume-to-JD keyword matching | table view, tying a resume version to an application |
| **Simplify** | Chrome extension auto-fills applications on 100+ portals | (not in v1) the idea of importing a job by URL |
| **ApplyArc / JobShinobi** | Stages `Saved, Applied, Phone Screen, Interview, Offer, Rejected` + funnel metrics and follow-up cadence | conversion metrics, follow-up reminders |

Common denominator across all: **stage funnel + detail card + conversion metrics**.
None of them lets an agent (me) write to the tracker programmatically — that's our
added value.

Research benchmarks for the dashboard: Applied→Interview conversion averages ~3%,
average time from first interview to decision ~27 days (NACE, entry-level).

---

## 3. Statuses (pipeline)

Chose 9 statuses — they cover the real funnel without sprawling. Interview rounds
are modeled **not** with new statuses but as timeline events (otherwise the status
enum explodes).

### Active (card "in play")

| Status | What it means | Typical next transition |
|--------|-----------|------------------------|
| `saved` | Found the job, haven't applied yet (wishlist) | `applied`, `withdrawn` |
| `applied` | Application sent | `screening`, `rejected`, `ghosted` |
| `screening` (UI: "In Contact") | A substantive reply came in: recruiter answered / conversation ongoing / a screen is scheduled or done — interview not yet scheduled | `interview`, `rejected`, `ghosted` |
| `interview` | Interviews underway (1..N rounds — in the timeline) | `offer`, `rejected`, `ghosted` |
| `offer` | Offer received | `accepted`, `rejected` (declined), `withdrawn` |

### Terminal (funnel closed)

| Status | What it means |
|--------|-----------|
| `accepted` | Offer accepted — success ✅ |
| `rejected` | Rejection (theirs or mine — distinguished by a field/event) |
| `withdrawn` | I pulled the application |
| `ghosted` | No reply >21 days after the last touch |

**Rules:**
- A status change always appends a `status_change` event to the timeline (from → to).
- `applied` sets `applied_at = now` if empty.
- `ghosted` can be set manually or automatically (nightly check of
  `next_action_date`/last event) — auto in v2.
- On the board, active statuses are columns; terminal ones collapse into an
  "Archive" filter so the board doesn't get cluttered.

---

## 4. Data model

SQLite. Three entities: `Application` (core), `Event` (timeline), contact inline
via fields in v1 (a separate `Contact` table if needed in v2).

### Application

```python
class Application:
    id: int                      # PK
    company: str                 # company name
    title: str                   # role — "remember the title"
    description: str             # full JD — "remember the description"
    job_url: str | None          # link to the posting

    location: str | None
    work_mode: Literal["onsite", "hybrid", "remote"] | None
    salary_min: int | None
    salary_max: int | None
    currency: str | None         # USD / EUR / RUB ...

    source: str                  # WHERE we applied: linkedin | hh | indeed |
                                 # company_site | referral | recruiter | email | other
    status: Status               # enum from §3

    resume_version: str | None   # WHAT we sent: which resume (label/file)
    cover_letter: str | None     # WHAT we wrote: cover letter / message text

    contact_name: str | None     # recruiter / hiring manager
    contact_email: str | None
    contact_url: str | None      # contact's LinkedIn

    next_action: str | None      # "write a follow-up", "prep for system design"
    next_action_date: date | None

    tags: list[str]              # stack/skills (JSON column)

    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

### Event (one job's timeline)

This is where the whole history of "what happened and when" lands, including **the
texts we wrote** (outreach message, thank-you note, post-interview note).

```python
class Event:
    id: int
    application_id: int          # FK
    kind: Literal["created", "status_change", "note",
                  "follow_up", "interview", "email_sent", "offer", "rejection"]
    body: str                    # text: message / note / feedback
    meta: dict | None            # e.g. {"from": "applied", "to": "screening"}
    occurred_at: datetime
```

**Why the timeline is its own entity, not fields:** there are several interviews,
several follow-ups, many notes. Flat fields can't hold history; an event log can,
and gives a free "diary" per job.

---

## 5. How Claude updates the tracker (key requirement)

Two entry points on top of **one service layer** (`tracker/services.py`) so the
logic doesn't diverge:

```
              ┌─────────────────┐
   React UI ──│  FastAPI (REST) │─┐
              └─────────────────┘ │   ┌──────────────┐   ┌────────┐
                                  ├──▶│  services.py │──▶│ SQLite │
              ┌─────────────────┐ │   └──────────────┘   └────────┘
   Claude  ───│  tracker (CLI)  │─┘
              └─────────────────┘
```

**My primary interface is the CLI**, because it always works: no running server
needed, no port to guess, writes straight to the same DB. Claude Code runs in this
repo → I just call a command in Bash.

```bash
tracker add --company "Acme" --title "Senior Backend Engineer" \
            --url https://... --source linkedin --description-file jd.md
tracker list --status applied
tracker show 12
tracker apply 12 --source linkedin --resume backend-v3 --cover-letter-file cl.md
tracker status 12 interview --note "passed the HR screen, system design next"
tracker note 12 "recruiter — Maria, promised an answer by Friday"
tracker metrics
```

`apply`/`status` automatically write a timeline event and move dates. The same
commands map to REST endpoints (§8) — if the server is up I can also use `curl`,
but the CLI is more reliable and I make it the default.

**On the server** (demo mode) there's no live writing from me: the server is a
showcase, data is seeded once by `tracker seed` into a separate demo DB
(`TRACKER_DB`), while my real applications stay in the local `tracker.db` via the
CLI. So the CLI needs no remote DB access — the "how do I write to the server DB"
question never arises.

---

## 6. Architecture and stack

### Backend
- **FastAPI** — REST + auto-generated OpenAPI (we type the frontend from it).
- **SQLModel** (Pydantic + SQLAlchemy) — models = DB schema = validation in one place.
- **SQLite** — a `tracker.db` file, more than enough for a single user.
- **Uvicorn** — to run it.
- Migrations: v1 without Alembic (`create_all`); the schema is still moving —
  introducing migrations is premature. We'll add them once it stabilizes.
- **No auth** — neither locally nor on the public demo. Since the demo is open, the
  public instance runs on a separate DB with fake data (`tracker seed`), not my
  real applications (see "Running" below).

### Frontend
- **React + TypeScript + Vite**.
- **TanStack Query** — server state (cache, invalidation after mutations).
- **Plain CSS with tokens** — a single set of CSS variables (light/dark theme),
  component classes; no UI kit and no build step for styles. Matches the approved
  mockup 1:1.
- **@dnd-kit** — drag-and-drop of cards between columns (modern, maintained).
- **A typed fetch client** (`src/api.ts`) mirrors the backend schemas by hand. Type
  generation from OpenAPI (`openapi-typescript`) — in v2, once the contract settles.

### Repository layout
```
application-tracker/
├── docs/DESIGN.md
├── backend/
│   ├── tracker/
│   │   ├── models.py        # SQLModel: Application, Event
│   │   ├── services.py      # ← single source of logic
│   │   ├── api.py           # FastAPI routes (thin, call services)
│   │   ├── cli.py           # tracker CLI (thin, calls services)
│   │   └── db.py
│   └── pyproject.toml       # console_scripts: tracker = tracker.cli:main
└── frontend/
    ├── src/
    │   ├── api.ts           # typed fetch client + types
    │   ├── lib.ts           # formatters (salary, dates)
    │   ├── constants.ts     # status/channel/event labels
    │   ├── App.tsx          # shell: topbar (view switcher, needs-action popover)
    │   ├── Board.tsx        # board + detail card (dnd-kit)
    │   ├── Views.tsx        # table + metrics
    │   └── styles.css       # tokens + component classes
    └── package.json
```

Ports: frontend (Vite dev) — **5173**, backend (FastAPI) — **8787** (Vite proxies
`/api` to it). DB — `backend/tracker.db`.

### Running: local and server

Two modes on one codebase — the stack and SQLite are shared; only the frontend
build and the DB the process points at differ.

**Local (development):** Vite dev on **5173** proxies `/api` to FastAPI (**8787**);
I write via the `tracker` CLI straight into `backend/tracker.db`.

**Server (demo, public URL):** the frontend is built (`vite build`), FastAPI serves
`dist/` as static (+ SPA fallback to `index.html`) — all traffic on one port and
origin, no more Vite proxy or CORS. No auth: the URL is public and `DELETE` is open,
so the demo points at a **separate** DB with fake data (`TRACKER_DB` + `tracker
seed`), not my real applications — if they break it, I re-seed.

Deployment — a single `uvicorn` behind the host's reverse proxy (which terminates
TLS). No Docker Compose, no separate nginx, no Postgres, no auth layer — overkill
for a demo.

---

## 7. UI — screens

All interface copy is in English; internal status keys stay as-is (`saved`,
`screening`, …).

### 7.1 Board (Kanban) — main view
Columns = active statuses. A card = a job. Drag changes the status. The header has
the view switcher and a **"needs action"** button that opens a popover listing jobs
with a due or overdue next action (follow-ups and upcoming events).

A card shows: company · role · channel badge · salary range · "days in stage" · a
next-action pill (red if the date is overdue).

### 7.2 Table
A dense list with all fields, sort/filter by status, channel, date. For people who
think in lists, not boards (like Teal).

### 7.3 Job detail
A slide-out panel / page: full JD, resume version + cover-letter text, event
timeline, contact, next action. Plus the buttons "add note", "change status", "log
interview".

### 7.4 Metrics dashboard
Funnel + conversion cards + by-channel breakdown.

---

## 8. REST API

| Method | Path | Purpose |
|-------|------|-----------|
| `GET` | `/applications?status=&source=&q=` | list with filters |
| `POST` | `/applications` | create |
| `GET` | `/applications/{id}` | one job + timeline |
| `PATCH` | `/applications/{id}` | partial field update |
| `POST` | `/applications/{id}/status` | change status (+ auto event) |
| `POST` | `/applications/{id}/events` | add an event/note |
| `DELETE` | `/applications/{id}` | delete |
| `GET` | `/metrics` | aggregates for the dashboard |

---

## 9. Funnel metrics

- **Total applied** = count with status `applied` and beyond.
- **Applied → Response** (response rate) = advanced past `applied` / applied.
- **Response → Interview** = reached `interview`+ / those who responded.
- **Interview → Offer** = offers / those who reached interview.
- **By channel** — response share per linkedin / referral / company_site …
  (which channel actually works).

---

## 10. Roadmap

**v1 (MVP):**
- `Application` + `Event` model, SQLite, service layer.
- REST API + `tracker` CLI.
- Frontend: board (drag-and-drop), detail card, add/edit.
- Basic dashboard (funnel, conversions, channels).

**v2:**
- Table view with filters.
- Auto-`ghosted` on timeout (nightly).
- Import a job by URL (parse the JD off the page).
- Separate `Contact` table, multiple contacts per job.
- CSV export.

**v3 (if wanted):**
- Resume-to-JD keyword matching (like Teal).
- Reminders (notifications/emails).

---

## 11. Decisions I made on my own (tell me to change any)

1. **9 statuses**, interview rounds as events, not statuses. Can shrink to 6.
2. **CLI as my primary access** (not just REST) — for reliability.
3. **SQLite + single-user, no auth.** For the demo — the same code behind a public
   URL on a separate DB with fake data (`tracker seed`). Auth, multi-user, and
   Postgres are deliberately left out — it's a showcase, not a service.
4. **Channels** (`source`): included both global ones (linkedin/indeed) and hh —
   tell me where you actually search and I'll trim the list.
5. **UI copy in English** — the whole interface is English; code/identifiers are
   English too. The display label for `screening` is "In Contact".
