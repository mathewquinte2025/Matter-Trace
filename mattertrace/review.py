"""Review bundle and decision service (components 9 and 10).

All authorization and status-transition rules live here, on the server side.
The UI calls `allowed_matter_actions` only to decide what to show; the same
function is re-checked inside `submit_matter_decision`, so a hidden button is
never the control. The reviewer is always the user in the AuthSession.
"""
import json
import uuid

from . import audit, auth
from .config import (CANDIDATE, CANDIDATE_READY, CONFIRMED, CORRECTED, ESCALATED, NEEDS_REVIEW,
                     PROCESSING_FAILED, REJECTED)
from .db import utc_now
from .errors import ValidationError
from .pipeline import RETRYABLE_STATUSES

MATTER_ACTIONS = ("confirm", "correct", "reject", "escalate")
FLAG_ACTIONS = ("confirm", "reject", "escalate")
MATTER_RESULT = {"confirm": CONFIRMED, "correct": CORRECTED, "reject": REJECTED, "escalate": ESCALATED}
FLAG_RESULT = {"confirm": CONFIRMED, "reject": REJECTED, "escalate": ESCALATED}

FLAG_TYPE_LABELS = {
    "exact_duplicate": "Exact duplicate",
    "near_duplicate": "Possible duplicate / other version",
    "possible_conflict": "Possible conflict",
}


def allowed_matter_actions(user, doc) -> list[str]:
    """Status transition rules for the document's matter association (Assignment 2, 7.6)."""
    if not auth.has_permission(user, "review"):
        return []
    status = doc["status"]
    if status in (CANDIDATE_READY, NEEDS_REVIEW):
        return ["confirm", "correct", "reject", "escalate"]
    if status == ESCALATED:
        # Escalations go to a supervising attorney.
        return ["confirm", "correct", "reject"] if auth.has_permission(user, "resolve_escalation") else []
    if status in (PROCESSING_FAILED, REJECTED):
        return ["correct", "escalate"]  # manual assignment path; nothing to confirm
    if status in (CONFIRMED, CORRECTED):
        return ["correct"]  # a later correction is a new, audited decision
    return []  # Received / Processing


def _new_decision_id() -> str:
    return f"DEC-{uuid.uuid4().hex[:12].upper()}"


def _matter_label(conn, matter_id) -> str:
    if not matter_id:
        return ""
    row = conn.execute("SELECT display_label FROM matters WHERE matter_id = ?", (matter_id,)).fetchone()
    return f"{matter_id} - {row['display_label']}" if row else matter_id


def list_documents(ctx, session) -> list[dict]:
    conn = ctx.conn
    user = auth.load_user(conn, session)
    rows = conn.execute("SELECT * FROM documents ORDER BY received_at DESC, document_id").fetchall()
    return [dict(r, matter_label=_matter_label(conn, r["matter_id"]))
            for r in rows if auth.can_view_document(conn, user, r)]


def permitted_matters(ctx, session) -> list[dict]:
    conn = ctx.conn
    user = auth.load_user(conn, session)
    ids = auth.permitted_matter_ids(conn, user["user_id"])
    return [dict(r) for r in conn.execute("SELECT * FROM matters WHERE active = 1 ORDER BY matter_id")
            if r["matter_id"] in ids]


def get_review_bundle(ctx, session, document_id: str, log_view: bool = True) -> dict:
    """Everything the review screen needs, filtered to what this user may see."""
    conn = ctx.conn
    user, doc = auth.require_document_access(conn, session, document_id, "view_document")
    permitted = auth.permitted_matter_ids(conn, user["user_id"])

    candidates = []
    for c in conn.execute("SELECT * FROM matter_candidates WHERE document_id = ? ORDER BY created_at, rank",
                          (document_id,)):
        if c["matter_id"] in permitted:
            candidates.append(dict(c, reasons=json.loads(c["reasons_json"]),
                                   matter_label=_matter_label(conn, c["matter_id"])))

    flags = []
    for f in conn.execute(
            "SELECT * FROM duplicate_candidates WHERE document_id = ? OR compared_document_id = ? ORDER BY created_at",
            (document_id, document_id)):
        other_id = f["compared_document_id"] if f["document_id"] == document_id else f["document_id"]
        other = conn.execute("SELECT * FROM documents WHERE document_id = ?", (other_id,)).fetchone()
        if not auth.can_view_document(conn, user, other):
            continue
        actions = []
        if auth.has_permission(user, "review"):
            if f["review_status"] == CANDIDATE:
                actions = list(FLAG_ACTIONS)
            elif f["review_status"] == ESCALATED and auth.has_permission(user, "resolve_escalation"):
                actions = ["confirm", "reject"]
        flags.append(dict(
            f, evidence=json.loads(f["evidence_json"]), flag_label=FLAG_TYPE_LABELS[f["flag_type"]],
            direction="this document vs. existing" if f["document_id"] == document_id else "later upload vs. this document",
            other_document_id=other_id, other_filename=other["filename"], other_status=other["status"],
            other_matter=_matter_label(conn, other["matter_id"]), allowed_actions=actions,
        ))

    segments = [dict(s) for s in conn.execute(
        "SELECT * FROM extracted_segments WHERE document_id = ? ORDER BY segment_index", (document_id,))]
    decisions = [dict(d) for d in conn.execute(
        "SELECT * FROM review_decisions WHERE document_id = ? ORDER BY timestamp, rowid", (document_id,))]

    if log_view:
        audit.record(conn, user["user_id"], "view_document", "document", document_id, "success", "", document_id)
        conn.commit()

    return {
        "document": dict(doc, matter_label=_matter_label(conn, doc["matter_id"])),
        "candidates": candidates,
        "active_candidates": [c for c in candidates if c["review_status"] == CANDIDATE],
        "flags": flags,
        "segments": segments,
        "decisions": decisions,
        "allowed_actions": allowed_matter_actions(user, doc),
        "can_retry": doc["status"] in RETRYABLE_STATUSES and (
            auth.has_permission(user, "upload") or auth.has_permission(user, "review")),
        "audit_events": [dict(e) for e in audit.events_for_document(conn, document_id)],
    }


def submit_matter_decision(ctx, session, document_id: str, action: str, candidate_id: str | None = None,
                           corrected_matter_id: str | None = None, note: str = "") -> str:
    """Apply a human review action to the document's matter association. Returns the new status."""
    conn = ctx.conn
    user, doc = auth.require_document_access(conn, session, document_id, f"review_{action}")
    if action not in MATTER_ACTIONS:
        raise ValidationError(f"Unknown review action '{action}'.")
    if not auth.has_permission(user, "review"):
        auth.deny(conn, user["user_id"], f"review_{action}", "document", document_id,
                  f"role '{user['role']}' may not review matter associations", document_id)
    if action not in allowed_matter_actions(user, doc):
        if doc["status"] == ESCALATED:
            auth.deny(conn, user["user_id"], f"review_{action}", "document", document_id,
                      "escalated items can only be resolved by a supervising attorney", document_id)
        raise ValidationError(f"Action '{action}' is not allowed while the document is '{doc['status']}'.")

    note = (note or "").strip()
    if action in ("reject", "escalate") and not note:
        raise ValidationError("A note explaining the reason is required to reject or escalate.")

    permitted = auth.permitted_matter_ids(conn, user["user_id"])
    active = conn.execute("SELECT * FROM matter_candidates WHERE document_id = ? AND review_status = ? ORDER BY rank",
                          (document_id, CANDIDATE)).fetchall()
    top = active[0] if active else None
    target_id = top["candidate_id"] if top else None
    new_matter = doc["matter_id"]

    if action == "confirm":
        cand = next((c for c in active if c["candidate_id"] == candidate_id), None)
        if cand is None:
            raise ValidationError("Select one of this document's current candidates to confirm.")
        if cand["matter_id"] not in permitted:
            auth.deny(conn, user["user_id"], "review_confirm", "candidate", candidate_id,
                      "not authorized for the candidate's matter", document_id)
        new_matter, target_id = cand["matter_id"], cand["candidate_id"]
        conn.execute("UPDATE matter_candidates SET review_status = ? WHERE candidate_id = ?", (CONFIRMED, target_id))
    elif action == "correct":
        if not corrected_matter_id:
            raise ValidationError("Choose the correct matter.")
        matter = conn.execute("SELECT * FROM matters WHERE matter_id = ? AND active = 1",
                              (corrected_matter_id,)).fetchone()
        if matter is None:
            raise ValidationError(f"Matter '{corrected_matter_id}' does not exist or is inactive.")
        if corrected_matter_id not in permitted:
            auth.deny(conn, user["user_id"], "review_correct", "matter", corrected_matter_id,
                      "not authorized for the selected matter", document_id)
        if corrected_matter_id == doc["matter_id"]:
            raise ValidationError("The document is already associated with that matter.")
        new_matter = corrected_matter_id
        if top:
            conn.execute("UPDATE matter_candidates SET review_status = ? WHERE candidate_id = ?",
                         (CORRECTED, top["candidate_id"]))
    elif action == "reject":
        conn.execute("UPDATE matter_candidates SET review_status = ? WHERE document_id = ? AND review_status = ?",
                     (REJECTED, document_id, CANDIDATE))
    # escalate: candidates stay open for the attorney.

    resulting = MATTER_RESULT[action]
    reason = {
        "confirm": f"Confirmed to {_matter_label(conn, new_matter)} by {user['display_name']}.",
        "correct": f"Corrected to {_matter_label(conn, new_matter)} by {user['display_name']}.",
        "reject": f"Candidate(s) rejected by {user['display_name']}: {note}",
        "escalate": f"Escalated by {user['display_name']} for attorney review: {note}",
    }[action]
    conn.execute("UPDATE documents SET status = ?, status_reason = ?, matter_id = ? WHERE document_id = ?",
                 (resulting, reason, new_matter, document_id))
    conn.execute(
        """INSERT INTO review_decisions
           (decision_id, document_id, target_type, target_id, reviewer_id, action, corrected_matter_id,
            note, previous_status, resulting_status, timestamp)
           VALUES (?, ?, 'matter_association', ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_new_decision_id(), document_id, target_id, user["user_id"], action,
         corrected_matter_id if action == "correct" else None, note, doc["status"], resulting, utc_now()),
    )
    audit.record(conn, user["user_id"], f"review_{action}", "document", document_id, "success",
                 f"{doc['status']} -> {resulting}; matter {new_matter or '(none)'}", document_id)
    conn.commit()
    return resulting


def submit_flag_decision(ctx, session, flag_id: str, action: str, note: str = "") -> str:
    """Disposition a duplicate/conflict warning. Documents are never deleted or merged."""
    conn = ctx.conn
    user = auth.load_user(conn, session)
    flag = conn.execute("SELECT * FROM duplicate_candidates WHERE flag_id = ?", (flag_id,)).fetchone()
    if flag is None:
        auth.deny(conn, user["user_id"], "review_flag", "duplicate_flag", flag_id,
                  "warning not found or not authorized")
    # The reviewer must be allowed to see both documents.
    auth.require_document_access(conn, session, flag["document_id"], "review_flag")
    auth.require_document_access(conn, session, flag["compared_document_id"], "review_flag")
    if action not in FLAG_ACTIONS:
        raise ValidationError(f"Unknown action '{action}'.")
    if not auth.has_permission(user, "review"):
        auth.deny(conn, user["user_id"], "review_flag", "duplicate_flag", flag_id,
                  f"role '{user['role']}' may not review warnings", flag["document_id"])
    status = flag["review_status"]
    if status == ESCALATED:
        if not auth.has_permission(user, "resolve_escalation"):
            auth.deny(conn, user["user_id"], "review_flag", "duplicate_flag", flag_id,
                      "escalated items can only be resolved by a supervising attorney", flag["document_id"])
        if action == "escalate":
            raise ValidationError("This warning is already escalated.")
    elif status != CANDIDATE:
        raise ValidationError(f"This warning was already reviewed ({status}).")
    note = (note or "").strip()
    if action in ("reject", "escalate") and not note:
        raise ValidationError("A note explaining the reason is required to dismiss or escalate a warning.")

    resulting = FLAG_RESULT[action]
    conn.execute("UPDATE duplicate_candidates SET review_status = ? WHERE flag_id = ?", (resulting, flag_id))
    conn.execute(
        """INSERT INTO review_decisions
           (decision_id, document_id, target_type, target_id, reviewer_id, action, corrected_matter_id,
            note, previous_status, resulting_status, timestamp)
           VALUES (?, ?, 'duplicate_flag', ?, ?, ?, NULL, ?, ?, ?, ?)""",
        (_new_decision_id(), flag["document_id"], flag_id, user["user_id"], action, note, status,
         resulting, utc_now()),
    )
    audit.record(conn, user["user_id"], f"flag_{action}", "duplicate_flag", flag_id, "success",
                 f"{flag['flag_type']} vs {flag['compared_document_id']}: {status} -> {resulting}",
                 flag["document_id"])
    conn.commit()
    return resulting


def full_audit_log(ctx, session, limit: int = 500) -> list[dict]:
    conn = ctx.conn
    auth.require_permission(conn, session, "view_full_audit", "view_audit_log", "audit_log")
    return [dict(e) for e in audit.all_events(conn, limit)]
