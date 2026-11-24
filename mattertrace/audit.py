"""Append-only audit log (part of component 10: Decision / Audit Service).

The only write operation offered here is `record`. Details must be short,
safe descriptions -- never full document text, passwords, or stack traces.
"""
import sqlite3

from .db import utc_now


def record(
    conn: sqlite3.Connection,
    actor_id: str,
    action: str,
    object_type: str,
    object_id: str | None,
    outcome: str,
    details: str = "",
    document_id: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO audit_events
           (timestamp, actor_id, action, object_type, object_id, document_id, outcome, safe_details)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (utc_now(), actor_id, action, object_type, object_id, document_id, outcome, details[:500]),
    )


def events_for_document(conn: sqlite3.Connection, document_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM audit_events WHERE document_id = ? ORDER BY event_id", (document_id,)
    ).fetchall()


def all_events(conn: sqlite3.Connection, limit: int = 500) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM audit_events ORDER BY event_id DESC LIMIT ?", (limit,)
    ).fetchall()
