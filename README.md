# Application Tracker

A personal job-search tracker: a Kanban board, a filterable table, and a
conversion-funnel dashboard over a small FastAPI service. It has two front doors
— a React web app and a scriptable `tracker` CLI — that share **one service
layer**, so the business logic never forks between them.

> Design notes, the status model, and the research behind it:
> [docs/DESIGN.md](docs/DESIGN.md) · static UI preview: [docs/mockup.html](docs/mockup.html)

## Highlights

- **One service layer, two thin adapters.** The REST routes
  ([api.py](backend/tracker/api.py)) and the CLI commands
  ([cli.py](backend/tracker/cli.py)) both call
  [services.py](backend/tracker/services.py); every status transition, timeline
  entry, and funnel calculation is defined there exactly once. Adding an
  interface means adding an adapter, not re-implementing logic.
- **An append-only event timeline drives the funnel.** Each application owns a
  log of `Event`s (status changes, notes, interviews). The dashboard doesn't
  read the current status — it replays each application's history, so a role
  rejected *after* an on-site still counts toward the interview stage of the
  funnel.
- **Typed end to end.** SQLModel (Pydantic + SQLAlchemy) models are the database
  schema and request validation in one place; FastAPI derives its OpenAPI spec
  from them; and a single `/api/meta` endpoint hands the frontend its status and
  channel enums, so labels can't drift between backend and UI.
- **No UI kit.** The interface is plain React over a set of CSS design tokens
  with a light/dark theme — no component library to age out.

## Tech stack

- **Backend** — FastAPI · SQLModel · SQLite · Typer (CLI) · Uvicorn
- **Frontend** — React · TypeScript · Vite · TanStack Query · @dnd-kit

## Screens

- **Board** — active statuses as columns, one card per role; drag a card to
  change its status (each drag appends a timeline event). A "needs action"
  popover surfaces due and overdue follow-ups.
- **Table** — a dense, filterable list of every application, for when you think
  in rows rather than columns.
- **Metrics** — the funnel, stage-to-stage conversion rates, and a per-channel
  breakdown of which sources actually land interviews.
- **Job detail** — full job description, the attached resume file and
  cover-letter text, contact, next action, and the complete event timeline;
  create / edit / delete inline.

Open [docs/mockup.html](docs/mockup.html) for a static preview of the design.

## Getting started

```bash
./tools/app_start.sh     # start the API (:8787) and the web app (:5173)
./tools/app_stop.sh      # stop both
```

`app_start.sh` brings up both servers detached — they keep running after you
close the terminal — waits until each one answers, and prints the URL. On a
fresh checkout it also creates the virtualenv, installs dependencies, and seeds
sample data; re-running it restarts cleanly. Logs stream to `logs/`.

Then open **http://localhost:5173**. Interactive API docs live at
**http://127.0.0.1:8787/docs**.

<details>
<summary>Running the two servers by hand</summary>

**Backend** (port 8787)
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/tracker seed      # load sample data (once)
.venv/bin/tracker serve     # REST API on http://127.0.0.1:8787
```

**Frontend** (port 5173)
```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173  (proxies /api → 8787)
```
</details>

## The `tracker` CLI

The CLI writes straight to the database through the same service layer as the
web API, so it works whether or not the server is running. Run it from
`backend/` as `.venv/bin/tracker <command>`.

```bash
tracker add -c "Acme" -t "Senior Backend Engineer" \
            --found-via linkedin --posting-url https://... --description-file jd.md
tracker list [--status applied]
tracker show 12
tracker apply 12 --applied-via email --applied-ref jobs@acme.com \
                 --resume-file resume-backend-v3.pdf --cover-letter-file cl.md
tracker resume 12 resume-backend-v3.pdf      # attach / replace the resume file (or --remove)
tracker status 12 interview --note "passed the HR screen, system design next"
tracker note 12 "recruiter promised an answer by Friday"
tracker set 12 --next-action "write a follow-up" --next-action-date 2026-07-25
tracker metrics
tracker seed --force        # reset sample data
```

`apply` and `status` append the matching timeline event and advance dates
automatically — the same behavior the REST endpoints have, because they call the
same functions.

## Status model

```
saved · applied · in_contact · screening · interview · offer · accepted · rejected · withdrawn · ghosted
```

`saved → applied → in_contact → screening → interview → offer → accepted` is the
happy path; `rejected / withdrawn / ghosted` are terminal. `in_contact` reads as
**In Contact** — any substantive reply from an employer; `screening` is a
scheduled recruiter / HR screening call. Further interview rounds are modeled as
timeline events rather than statuses, so the enum stays small.

## REST API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/applications?status=&applied_via=&q=` | list with filters |
| `POST` | `/api/applications` | create |
| `GET` | `/api/applications/{id}` | one application + its timeline |
| `PATCH` | `/api/applications/{id}` | partial update |
| `DELETE` | `/api/applications/{id}` | delete |
| `POST` | `/api/applications/{id}/status` | change status (+ auto event) |
| `POST` | `/api/applications/{id}/events` | append a note or event |
| `GET` | `/api/metrics` | funnel + conversion aggregates |
| `GET` | `/api/meta` | status / channel / work-mode enums |

Full interactive OpenAPI docs at `/docs` while the server is running.

## Architecture

```
  Web app   ──▶  FastAPI (REST)  ─┐
                                  ├─▶  services.py  ──▶  SQLite
  Terminal  ──▶  tracker (CLI)   ─┘
```

Both surfaces are deliberately thin — routing and argument parsing only. All
behavior lives in `services.py`, the single place where status transitions,
event logging, and metrics are defined.

```
backend/
  tracker/
    models.py     SQLModel tables (Application, Event) + enums
    services.py   business logic — the single source of truth
    api.py        FastAPI routes (thin)
    cli.py        Typer CLI (thin)
    db.py         engine + sessions
frontend/
  src/
    api.ts        typed fetch client
    App.tsx       shell: view switcher, search, needs-action popover
    Board.tsx     Kanban board + job detail (drag-and-drop)
    Views.tsx     table + metrics
    JobForm.tsx   create / edit / delete
    styles.css    CSS tokens + component styles
```

## Data & configuration

State is a single SQLite file at `backend/tracker.db`. Point the app at a
different file — a throwaway database for a demo, say — with `TRACKER_DB`:

```bash
TRACKER_DB=/tmp/demo.db tracker seed
TRACKER_DB=/tmp/demo.db tracker serve
```

## Scope

A deliberately small, single-user tool: SQLite, no auth, no multi-tenant layer.
Those omissions are choices, not gaps — the reasoning, and what a later version
would add, is in [docs/DESIGN.md](docs/DESIGN.md).
