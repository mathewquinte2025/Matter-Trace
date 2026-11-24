"""Wires settings, the database connection, and the AI service together."""
import sqlite3
from dataclasses import dataclass

from . import db
from .ai_service import AIMatterService, build_ai_service
from .config import Settings, load_settings


@dataclass
class AppContext:
    conn: sqlite3.Connection
    settings: Settings
    ai_service: AIMatterService | None


def open_context(settings: Settings | None = None, seed_if_empty: bool = True) -> AppContext:
    settings = settings or load_settings()
    conn = db.connect(settings.db_path)
    db.create_schema(conn)
    ctx = AppContext(conn, settings, build_ai_service(settings.ai_service))
    if seed_if_empty and conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        from .seed import seed
        seed(ctx)
    return ctx
