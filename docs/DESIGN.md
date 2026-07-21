# Application Tracker — Design Doc

A personal job-application tracker for a single user. The primary scenario is
running it locally; the same code can also run as a single process behind a
public URL for a demo (see §6). Distinguishing trait: **two interfaces on one
logic layer** — a web UI over REST and a terminal `tracker` CLI — so the tracker
can be driven from the browser or scripted from the shell, and the behavior never
diverges between them.

---

## 1. TL;DR

- **What**: board (Kanban) + table + job detail card + funnel dashboard.
- **Stack**: Python (FastAPI + SQLite) — backend, React + TypeScript (Vite) — frontend.
- **Statuses**: `saved → applied → screening → interview → offer → accepted`,
  plus terminal `rejected / withdrawn / ghosted`.
- **Stored per job**: the JD itself (title + full description), **where** the
  application went (channel), **what** was sent (resume file + cover letter /
  message text), an event timeline, recruiter contact, next action.
- **Two entry points**: the REST API behind the web UI, and the `tracker` CLI,
  which works without a running server — writing straight to SQLite through the
  same service layer as the API.

---

## 2. What existing trackers do (research)

Looked at Teal, Huntr, Simplify, ApplyArc, JobShinobi — the gist:

| Tool | Core idea | What this project borrows |
|-----------|--------------|--------------|
| **Huntr** | Kanban board `wishlist → applied → interview → offer → rejected`, CRM layer | board as the main view, drag-and-drop status changes |
| **Teal** | Table + funnel overview on top, resume-to-JD keyword matching | table view, tying a resume file to an application |
| **Simplify** | Chrome extension auto-fills applications on 100+ portals | (not in v1) the idea of importing a job by URL |
| **ApplyArc / JobShinobi** | Stages `Saved, Applied, Phone Screen, Interview, Offer, Rejected` + funnel metrics and follow-up cadence | conversion metrics, follow-up reminders |

Common denominator across all: **stage funnel + detail card + conversion metrics**.
What none of them offers is a scriptable CLI running on the same logic as the UI —
a terminal-first entry point for fast logging and automation. That's the angle
here.

Research benchmarks for the dashboard: Applied→Interview conversion averages ~3%,
average time from first interview to decision ~27 days (NACE, entry-level).

---

## 3. Statuses (pipeline)

Nine statuses — enough to cover the real funnel without sprawling. Interview
rounds are modeled **not** as new statuses but as timeline events (otherwise the
status enum explodes).

### Active (card "in play")

| Status | What it means | Typical next transition |
|--------|-----------|------------------------|
| `saved` | Found the job, not applied yet (wishlist) | `applied`, `withdrawn` |
| `applied` | Application sent | `screening`, `rejected`, `ghosted` |
| `screening` (UI: "In Contact") | A substantive reply came in: recruiter answered / conversation ongoing / a screen is scheduled or done — interview not yet scheduled | `interview`, `rejected`, `ghosted` |
| `interview` | Interviews underway (1..N rounds — in the timeline) | `offer`, `rejected`, `ghosted` |
| `offer` | Offer received | `accepted`, `rejected` (declined), `withdrawn` |

### Terminal (funnel closed)

| Status | What it means |
|--------|-----------|
| `accepted` | Offer accepted — success ✅ |
| `rejected` | Rejection (by the employer or the candidate — distinguished by a field/event) |
| `withdrawn` | The candidate pulled the application |
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
    title: str                   # role
    description: str             # full JD, kept verbatim
    job_url: str | None          # link to the posting

    location: str | None
    work_mode: Literal["onsite", "hybrid", "remote"] | None
    salary_min: int | None
    salary_max: int | None
    currency: str | None         # USD / EUR / RUB ...

    source: str                  # WHERE it went: linkedin | hh | indeed |
                                 # company_site | referral | recruiter | email | other
    status: Status               # enum from §3

    # WHAT was sent — the resume file itself lives in a 1:1 ResumeFile table
    # (a BLOB in the same SQLite file), replaced on each new upload.
    cover_letter: str | None     # WHAT was written: cover letter / message text

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

This is where the whole history of "what happened and when" lands, including the
**texts that were written** (outreach message, thank-you note, post-interview
note).

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

## 5. Two interfaces on one service layer

The web UI and the CLI are two front doors on top of **one service layer**
(`tracker/services.py`), so the logic never diverges:

```
              ┌─────────────────┐
   Web UI  ───│  FastAPI (REST) │─┐
              └─────────────────┘ │   ┌──────────────┐   ┌────────┐
                                  ├──▶│  services.py │──▶│ SQLite │
              ┌─────────────────┐ │   └──────────────┘   └────────┘
   Terminal ──│  tracker (CLI)  │─┘
              └─────────────────┘
```

The CLI is a first-class interface, not an afterthought: it needs no running
server, doesn't depend on a port, and writes straight to the same database as the
web app. That makes it the fast path for terminal entry and scripting.

```bash
tracker add --company "Acme" --title "Senior Backend Engineer" \
            --url https://... --source linkedin --description-file jd.md
tracker list --status applied
tracker show 12
tracker apply 12 --source linkedin --resume-file resume-backend-v3.pdf --cover-letter-file cl.md
tracker status 12 interview --note "passed the HR screen, system design next"
tracker note 12 "recruiter — Maria, promised an answer by Friday"
tracker metrics
```

`apply`/`status` automatically write a timeline event and move dates. The same
operations map to REST endpoints (§8) — and because both surfaces call the same
service functions, `curl` against a running server and the CLI produce identical
results; the CLI is the default because it works without one.

For a public demo, data is seeded once by `tracker seed` into a separate demo
database (via `TRACKER_DB`), kept apart from the real local `tracker.db`. So the
CLI never needs remote DB access — "how do I write to the server's DB" simply
doesn't arise.

---

## 6. Architecture and stack

### Backend
- **FastAPI** — REST + auto-generated OpenAPI (the frontend is typed from it).
- **SQLModel** (Pydantic + SQLAlchemy) — models = DB schema = validation in one place.
- **SQLite** — a `tracker.db` file, more than enough for a single user.
- **Uvicorn** — to run it.
- Migrations: v1 without Alembic (`create_all`); the schema is still moving, so
  introducing migrations now is premature — they come once it stabilizes.
- **No auth** — neither locally nor on the public demo. Since the demo is open, the
  public instance runs on a separate DB with fake data (`tracker seed`), not real
  applications (see "Running" below).

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
build and the database the process points at differ.

**Local (development):** Vite dev on **5173** proxies `/api` to FastAPI (**8787**);
updates go through the `tracker` CLI straight into `backend/tracker.db`.

**Server (demo, public URL):** the frontend is built (`vite build`), FastAPI serves
`dist/` as static (+ SPA fallback to `index.html`) — all traffic on one port and
origin, no more Vite proxy or CORS. No auth: the URL is public and `DELETE` is open,
so the demo points at a **separate** DB with fake data (`TRACKER_DB` + `tracker
seed`), not real applications — if a visitor breaks it, re-seed.

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
A slide-out panel / page: full JD, the attached resume file + cover-letter text, event
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

## 11. Design decisions

1. **Nine statuses**, interview rounds as events rather than statuses — covers the
   funnel without letting the enum sprawl.
2. **A first-class CLI, not just REST** — it works without a running server and is
   the fast path for terminal entry and scripting; both surfaces share one service
   layer, so nothing about the logic is CLI-specific.
3. **SQLite, single-user, no auth.** For the demo, the same code runs behind a
   public URL on a separate DB with fake data (`tracker seed`). Auth, multi-user,
   and Postgres are deliberately out of scope — this is a showcase, not a service.
4. **Channels** (`source`): a mix of international (LinkedIn, Indeed) and regional
   (hh.ru, Telegram) sources, matching a mixed RU + international job search.
5. **UI copy in English** — the whole interface and all identifiers are English;
   the display label for `screening` is "In Contact".
