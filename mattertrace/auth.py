"""Authentication and matter-scoped authorization (component 2: Access Control).

Every service function re-checks permissions here; the UI hiding a button is
never the control. Reviewer identity always comes from the AuthSession that
`login` issued, not from form input.
"""
import hashlib
import hmac
import sqlite3
from dataclasses import dataclass

from . import audit
from .errors import AuthorizationError

ROLE_PERMISSIONS = {
    "intake": {"upload"},
    "paralegal": {"upload", "review"},
    "attorney": {"upload", "review", "resolve_escalation", "view_full_audit"},
}


@dataclass(frozen=True)
class AuthSession:
    """Issued only by `login`. Held server-side in the Streamlit session."""
    user_id: str
    username: str
    display_name: str
    role: str


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def login(conn: sqlite3.Connection, username: str, password: str) -> AuthSession | None:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
    ok = row is not None and hmac.compare_digest(
        hash_password(password, row["password_salt"]), row["password_hash"]
    )
    audit.record(
        conn,
        actor_id=row["user_id"] if row else "anonymous",
        action="login",
        object_type="session",
        object_id=None,
        outcome="success" if ok else "denied",
        details="" if ok else "invalid username or password",
    )
    conn.commit()
    if not ok:
        return None
    return AuthSession(row["user_id"], row["username"], row["display_name"], row["role"])


def load_user(conn: sqlite3.Connection, session: AuthSession) -> sqlite3.Row:
    """Re-load the user on every request so role changes take effect immediately."""
    if session is None:
        raise AuthorizationError("You must be logged in.")
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (session.user_id,)).fetchone()
    if row is None:
        raise AuthorizationError("Unknown user.")
    return row


def has_permission(user: sqlite3.Row, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(user["role"], set())


def permitted_matter_ids(conn: sqlite3.Connection, user_id: str) -> set[str]:
    rows = conn.execute(
        """SELECT ma.matter_id FROM matter_access ma
           JOIN matters m ON m.matter_id = ma.matter_id
           WHERE ma.user_id = ? AND m.active = 1""",
        (user_id,),
    ).fetchall()
    return {r["matter_id"] for r in rows}


def deny(conn, user_id: str, action: str, object_type: str, object_id, reason: str, document_id=None):
    """Log the denied attempt, commit it, and raise."""
    audit.record(conn, user_id, action, object_type, object_id, "denied", reason, document_id)
    conn.commit()
    raise AuthorizationError(reason)


def require_permission(conn, session: AuthSession, permission: str, action: str,
                       object_type: str, object_id=None, document_id=None) -> sqlite3.Row:
    user = load_user(conn, session)
    if not has_permission(user, permission):
        deny(conn, user["user_id"], action, object_type, object_id,
             f"role '{user['role']}' lacks permission '{permission}'", document_id)
    return user


def can_view_document(conn: sqlite3.Connection, user: sqlite3.Row, doc: sqlite3.Row) -> bool:
    """Matter-scoped visibility rule.

    - A document associated with a matter (by a human) is visible only to users
      with access to that matter.
    - An unassociated document is visible to its submitter and to users with
      access to at least one of its current candidate matters.
    - An unassociated document with no candidates (failed / no match) is also
      visible to supervising attorneys, who handle manual review.
    """
    permitted = permitted_matter_ids(conn, user["user_id"])
    if doc["matter_id"]:
        return doc["matter_id"] in permitted
    if doc["submitting_user_id"] == user["user_id"]:
        return True
    candidate_matters = {
        r["matter_id"] for r in conn.execute(
            "SELECT matter_id FROM matter_candidates WHERE document_id = ? AND review_status != 'Superseded'",
            (doc["document_id"],),
        )
    }
    if candidate_matters & permitted:
        return True
    return not candidate_matters and user["role"] == "attorney"


def require_document_access(conn, session: AuthSession, document_id: str, action: str):
    """Return (user, document) or log + raise AuthorizationError.

    A missing document and a forbidden document produce the same message so
    the response does not reveal which document IDs exist.
    """
    user = load_user(conn, session)
    doc = conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
    if doc is None or not can_view_document(conn, user, doc):
        deny(conn, user["user_id"], action, "document", document_id,
             "document not found or not authorized for this user",
             document_id if doc is not None else None)
    return user, doc
