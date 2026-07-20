"""Database engine and session helpers.

Single SQLite file shared by the REST API and the CLI. Override the location
with the ``TRACKER_DB`` environment variable (useful for tests / throwaway runs).
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine

DEFAULT_DB = Path(__file__).resolve().parent.parent / "tracker.db"
DB_PATH = os.environ.get("TRACKER_DB") or str(DEFAULT_DB)

# check_same_thread=False so the CLI and Uvicorn workers can share the file.
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables if they do not exist yet."""
    # Import models so they are registered on SQLModel.metadata before create_all.
    from tracker import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency: yield a session bound to the shared engine."""
    with Session(engine) as session:
        yield session


def open_session() -> Session:
    """Plain session for CLI use (caller is responsible for closing/committing)."""
    return Session(engine)
