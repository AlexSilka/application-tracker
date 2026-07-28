"""FastAPI REST API — a thin HTTP layer over ``tracker.services``."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from tracker import services
from tracker.db import get_session, init_db
from tracker.models import (
    ACTIVE_STATUSES,
    APPLIED_VIA,
    Direction,
    FOUND_VIA,
    STATUS_LABEL,
    TERMINAL_STATUSES,
    ApplicationCreate,
    ApplicationDetail,
    ApplicationRead,
    ApplicationUpdate,
    EventCreate,
    EventRead,
    Status,
    StatusChange,
    WorkMode,
)

app = FastAPI(title="Application Tracker", version="0.1.0")

# A resume is a document, not a media file — anything larger is a mistake we'd
# rather reject than silently bloat the SQLite file with.
MAX_RESUME_BYTES = 10 * 1024 * 1024

# The Vite dev server runs on 5173; allow it (and localhost variants) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/meta")
def meta() -> dict:
    """Enums the frontend renders from — one source of truth for statuses / channels."""
    return {
        "statuses": [
            {
                "value": s.value,
                "label": STATUS_LABEL[s],
                "active": s in ACTIVE_STATUSES,
                "terminal": s in TERMINAL_STATUSES,
            }
            for s in Status
        ],
        "active_statuses": [s.value for s in ACTIVE_STATUSES],
        "terminal_statuses": [s.value for s in TERMINAL_STATUSES],
        "found_via": FOUND_VIA,
        "applied_via": APPLIED_VIA,
        "work_modes": [w.value for w in WorkMode],
        "directions": [d.value for d in Direction],
    }


@app.get("/api/applications", response_model=list[ApplicationRead])
def list_applications(
    status: Optional[Status] = None,
    applied_via: Optional[str] = None,
    q: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
):
    return services.list_applications(session, status=status, applied_via=applied_via, q=q)


@app.post("/api/applications", response_model=ApplicationDetail, status_code=201)
def create_application(payload: ApplicationCreate, session: Session = Depends(get_session)):
    app_obj = services.create_application(session, payload)
    return services.get_application(session, app_obj.id)


@app.get("/api/applications/{app_id}", response_model=ApplicationDetail)
def get_application(app_id: int, session: Session = Depends(get_session)):
    try:
        return services.get_application(session, app_id)
    except services.NotFound:
        raise HTTPException(status_code=404, detail="application not found")


@app.patch("/api/applications/{app_id}", response_model=ApplicationDetail)
def update_application(
    app_id: int, payload: ApplicationUpdate, session: Session = Depends(get_session)
):
    try:
        services.update_application(session, app_id, payload)
        return services.get_application(session, app_id)
    except services.NotFound:
        raise HTTPException(status_code=404, detail="application not found")


@app.post("/api/applications/{app_id}/status", response_model=ApplicationDetail)
def change_status(
    app_id: int, payload: StatusChange, session: Session = Depends(get_session)
):
    try:
        services.set_status(session, app_id, payload.status, note=payload.note)
        return services.get_application(session, app_id)
    except services.NotFound:
        raise HTTPException(status_code=404, detail="application not found")


@app.post("/api/applications/{app_id}/events", response_model=EventRead, status_code=201)
def add_event(app_id: int, payload: EventCreate, session: Session = Depends(get_session)):
    try:
        return services.add_event(
            session, app_id, kind=payload.kind, body=payload.body, meta=payload.meta
        )
    except services.NotFound:
        raise HTTPException(status_code=404, detail="application not found")


@app.delete("/api/applications/{app_id}", status_code=204)
def delete_application(app_id: int, session: Session = Depends(get_session)):
    try:
        services.delete_application(session, app_id)
    except services.NotFound:
        raise HTTPException(status_code=404, detail="application not found")


@app.post("/api/applications/{app_id}/resume", response_model=ApplicationDetail)
def upload_resume(
    app_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Attach (or replace) the resume file sent for this application."""
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 10 MB)")
    try:
        services.set_resume(
            session,
            app_id,
            filename=file.filename or "resume",
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
        return services.get_application(session, app_id)
    except services.NotFound:
        raise HTTPException(status_code=404, detail="application not found")


@app.get("/api/applications/{app_id}/resume")
def download_resume(app_id: int, session: Session = Depends(get_session)):
    rf = services.get_resume(session, app_id)
    if rf is None:
        raise HTTPException(status_code=404, detail="no resume attached")
    # `inline` lets the browser preview PDFs in a new tab and still offer Save;
    # non-previewable types (docx) fall back to a download named after the file.
    return Response(
        content=rf.content,
        media_type=rf.content_type,
        headers={"Content-Disposition": f'inline; filename="{rf.filename}"'},
    )


@app.delete("/api/applications/{app_id}/resume", status_code=204)
def delete_resume(app_id: int, session: Session = Depends(get_session)):
    try:
        services.delete_resume(session, app_id)
    except services.NotFound:
        raise HTTPException(status_code=404, detail="application not found")


@app.get("/api/metrics")
def get_metrics(session: Session = Depends(get_session)):
    return services.metrics(session)
