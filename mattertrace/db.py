"""SQLite schema and connection helpers (components 3/4: document store + metadata repository)."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,
    username       TEXT NOT NULL UNIQUE,
    display_name   TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('paralegal', 'attorney', 'intake')),
    password_salt  TEXT NOT NULL,
    password_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matters (
    matter_id      TEXT PRIMARY KEY,
    display_label  TEXT NOT NULL,
    client_name    TEXT NOT NULL,
    client_dob     TEXT,            -- MM/DD/YYYY
    incident_date  TEXT,            -- MM/DD/YYYY
    claim_number   TEXT,
    insurer        TEXT,
    active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS matter_access (
    user_id    TEXT NOT NULL REFERENCES users(user_id),
    matter_id  TEXT NOT NULL REFERENCES matters(matter_id),
    PRIMARY KEY (user_id, matter_id)
);

CREATE TABLE IF NOT EXISTS documents (
    document_id         TEXT PRIMARY KEY,
    original_file_ref   TEXT NOT NULL,
    filename            TEXT NOT NULL,
    file_type           TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL,
    checksum_sha256     TEXT NOT NULL,
    received_at         TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    source_description  TEXT NOT NULL DEFAULT '',
    submitting_user_id  TEXT NOT NULL REFERENCES users(user_id),
    status              TEXT NOT NULL,
    status_reason       TEXT NOT NULL DEFAULT '',
    matter_id           TEXT REFERENCES matters(matter_id),  -- set only by a human review action
    processing_ms       INTEGER
);

CREATE TABLE IF NOT EXISTS extracted_segments (
    segment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    TEXT NOT NULL REFERENCES documents(document_id),
    page_number    INTEGER,          -- PDF page (1-based); NULL for TXT
    segment_index  INTEGER NOT NULL, -- order within the document (paragraph number for TXT)
    text           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matter_candidates (
    candidate_id       TEXT PRIMARY KEY,
    document_id        TEXT NOT NULL REFERENCES documents(document_id),
    matter_id          TEXT NOT NULL REFERENCES matters(matter_id),
    rank               INTEGER NOT NULL,
    score              REAL NOT NULL,
    uncertainty_label  TEXT NOT NULL,
    reasons_json       TEXT NOT NULL,  -- validated, structured evidence (never raw model text)
    matcher_name       TEXT NOT NULL,
    matcher_version    TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    review_status      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS duplicate_candidates (
    flag_id               TEXT PRIMARY KEY,
    document_id           TEXT NOT NULL REFERENCES documents(document_id),
    compared_document_id  TEXT NOT NULL REFERENCES documents(document_id),
    flag_type             TEXT NOT NULL CHECK (flag_type IN ('exact_duplicate', 'near_duplicate', 'possible_conflict')),
    similarity            REAL,
    evidence_json         TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    review_status         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id          TEXT PRIMARY KEY,
    document_id          TEXT NOT NULL REFERENCES documents(document_id),
    target_type          TEXT NOT NULL CHECK (target_type IN ('matter_association', 'duplicate_flag')),
    target_id            TEXT,           -- candidate_id or flag_id (NULL for manual assignment)
    reviewer_id          TEXT NOT NULL REFERENCES users(user_id),
    action               TEXT NOT NULL,
    corrected_matter_id  TEXT REFERENCES matters(matter_id),
    note                 TEXT NOT NULL DEFAULT '',
    previous_status      TEXT NOT NULL,
    resulting_status     TEXT NOT NULL,
    timestamp            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    actor_id      TEXT NOT NULL,
    action        TEXT NOT NULL,
    object_type   TEXT NOT NULL,
    object_id     TEXT,
    document_id   TEXT,
    outcome       TEXT NOT NULL,
    safe_details  TEXT NOT NULL DEFAULT ''
);

-- Append-only history: the application never updates or deletes these rows,
-- and the database refuses if anything tries.
CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_decisions_no_update BEFORE UPDATE ON review_decisions
BEGIN SELECT RAISE(ABORT, 'review_decisions is append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_decisions_no_delete BEFORE DELETE ON review_decisions
BEGIN SELECT RAISE(ABORT, 'review_decisions is append-only'); END;

-- Documents are never deleted, and their identity / original-file fields never change.
CREATE TRIGGER IF NOT EXISTS documents_no_delete BEFORE DELETE ON documents
BEGIN SELECT RAISE(ABORT, 'documents cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS documents_identity_fixed
BEFORE UPDATE OF document_id, original_file_ref, checksum_sha256, filename, received_at, source_type ON documents
BEGIN SELECT RAISE(ABORT, 'document identity and source fields are immutable'); END;
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
