# Отклики — трекер вакансий

Персональный трекер откликов на работу. Одна особенность отличает его от Teal /
Huntr: **трекер обновляю не только я через веб-интерфейс, но и Claude — через
`tracker` CLI**. Обе точки входа сидят на одном сервисном слое.

- **Бэкенд**: FastAPI + SQLModel + SQLite
- **Фронт**: React + TypeScript + Vite + TanStack Query + @dnd-kit
- Дизайн и решения: [docs/DESIGN.md](docs/DESIGN.md) · превью-макет: `docs/mockup.html`

## Структура

```
backend/   FastAPI + SQLite + tracker-CLI   (один сервисный слой services.py)
frontend/  React + TS + Vite                (доска / таблица / метрики)
docs/      DESIGN.md, mockup.html
```

## Запуск

### Бэкенд (порт 8787)
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/tracker seed          # наполнить примерами (один раз)
.venv/bin/tracker serve         # REST API на http://127.0.0.1:8787
```

### Фронт (порт 5173)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173  (проксирует /api → 8787)
```

Открыть **http://localhost:5173**.

## `tracker` CLI

Пишет прямо в `backend/tracker.db` через тот же сервисный слой, что и веб —
**сервер для этого поднимать не нужно**. Запускать из `backend/` как
`.venv/bin/tracker <cmd>`.

```bash
tracker add -c "Acme" -t "Senior Backend Engineer" \
            --url https://... --source linkedin --description-file jd.md
tracker list [--status applied]
tracker show 12
tracker apply 12 --source linkedin --resume backend-v3 --cover-letter-file cl.md
tracker status 12 interview --note "прошёл HR-скрининг, дальше систем-дизайн"
tracker note 12 "рекрутёр обещал ответ до пятницы"
tracker set 12 --next-action "написать follow-up" --next-action-date 2026-07-25
tracker metrics
tracker seed --force            # сбросить примеры
```

Статусы: `saved · applied · screening · interview · offer · accepted ·
rejected · withdrawn · ghosted`. Раунды интервью — событиями в таймлайне.

## REST API

`GET /api/applications` · `POST /api/applications` ·
`GET|PATCH|DELETE /api/applications/{id}` ·
`POST /api/applications/{id}/status` · `POST /api/applications/{id}/events` ·
`GET /api/metrics` · `GET /api/meta`. Docs: http://127.0.0.1:8787/docs

## Данные

Одна SQLite-БД `backend/tracker.db`. Переопределить путь — `TRACKER_DB=/path.db`.
