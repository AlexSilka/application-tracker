# Application Tracker

A personal job-application tracker. One thing sets it apart from Teal / Huntr:
**the tracker is updated not only by me through the web UI, but also by Claude —
via the `tracker` CLI**. Both entry points sit on one service layer.

- **Backend**: FastAPI + SQLModel + SQLite
- **Frontend**: React + TypeScript + Vite + TanStack Query + @dnd-kit
- Design & decisions: [docs/DESIGN.md](docs/DESIGN.md) · static preview: `docs/mockup.html`

## Layout

```
backend/   FastAPI + SQLite + tracker CLI   (one service layer, services.py)
frontend/  React + TS + Vite                (Board / Table / Metrics)
docs/      DESIGN.md, mockup.html
```

## Running

### Backend (port 8787)
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/tracker seed          # seed with sample data (once)
.venv/bin/tracker serve         # REST API at http://127.0.0.1:8787
```

### Frontend (port 5173)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173  (proxies /api → 8787)
```

Open **http://localhost:5173**.

## `tracker` CLI

Writes straight to `backend/tracker.db` through the same service layer as the web
UI — **no server needed**. Run from `backend/` as `.venv/bin/tracker <cmd>`.

```bash
tracker add -c "Acme" -t "Senior Backend Engineer" \
            --url https://... --source linkedin --description-file jd.md
tracker list [--status applied]
tracker show 12
tracker apply 12 --source linkedin --resume backend-v3 --cover-letter-file cl.md
tracker status 12 interview --note "passed the HR screen, system design next"
tracker note 12 "recruiter promised an answer by Friday"
tracker set 12 --next-action "write a follow-up" --next-action-date 2026-07-25
tracker metrics
tracker seed --force            # reset sample data
```

Statuses: `saved · applied · screening · interview · offer · accepted · rejected ·
withdrawn · ghosted`. Interview rounds are timeline events, not statuses. In the UI,
`screening` is shown as **In Contact** — any substantive reply from an employer
before an interview is scheduled.

## REST API

`GET /api/applications` · `POST /api/applications` ·
`GET|PATCH|DELETE /api/applications/{id}` ·
`POST /api/applications/{id}/status` · `POST /api/applications/{id}/events` ·
`GET /api/metrics` · `GET /api/meta`. Docs: http://127.0.0.1:8787/docs

## Data

A single SQLite DB at `backend/tracker.db`. Override the path with `TRACKER_DB=/path.db`.
