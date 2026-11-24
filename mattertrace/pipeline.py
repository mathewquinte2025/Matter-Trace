"""Analysis pipeline: extraction -> candidate retrieval -> matching -> AI check ->
duplicate/conflict check -> candidate status. Also the retry path (FR-10, NFR-10).

The pipeline only produces candidates. It never sets documents.matter_id and
never produces a Confirmed status; only review.py does that, after a human acts.
"""
import json
import time
import uuid

from . import audit, auth, duplicates, extraction, intake, matching
from .ai_service import validate_ai_output
from .config import (CANDIDATE, CANDIDATE_READY, NEEDS_REVIEW, PROCESSING, PROCESSING_FAILED,
                     RECEIVED, REJECTED, SUPERSEDED)
from .db import utc_now
from .errors import AIServiceError, ExtractionError, ValidationError

RETRYABLE_STATUSES = {PROCESSING_FAILED, NEEDS_REVIEW, REJECTED}


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def decide_status(rule_scores: list[tuple[str, float]], threshold: float, margin: float,
                  warning_count: int, ai_problems: list[str]) -> tuple[str, str]:
    """Pure decision rule. Candidate Ready only when everything is clean; otherwise Needs Review.

    Neither outcome is a confirmation: both wait for a human review action.
    """
    reasons = []
    if not rule_scores:
        reasons.append("No matter identifiers (matter number, claim number, client name, DOB, "
                       "incident date) were found among the matters you can access.")
    else:
        top_matter, top_score = rule_scores[0]
        if top_score < threshold:
            reasons.append(f"Low confidence: best match {top_matter} scored {top_score:.2f}, "
                           f"below the {threshold:.2f} threshold.")
        if len(rule_scores) > 1 and rule_scores[1][1] >= top_score - margin:
            reasons.append(f"Ambiguous: {top_matter} ({top_score:.2f}) and {rule_scores[1][0]} "
                           f"({rule_scores[1][1]:.2f}) scored within {margin:.2f} of each other.")
    if warning_count:
        reasons.append(f"{warning_count} possible duplicate/conflict warning(s) must be reviewed.")
    reasons.extend(ai_problems)
    if reasons:
        return NEEDS_REVIEW, " ".join(reasons)
    top_matter, top_score = rule_scores[0]
    return CANDIDATE_READY, (f"Suggested matter {top_matter} (score {top_score:.2f}). "
                             "Not confirmed until an authorized reviewer acts.")


def load_or_extract(ctx, doc) -> list[dict]:
    """Segments are deterministic for an unchanged original, so reuse them on retry."""
    conn = ctx.conn
    rows = conn.execute("SELECT * FROM extracted_segments WHERE document_id = ? ORDER BY segment_index",
                        (doc["document_id"],)).fetchall()
    if not rows:
        segments = extraction.extract(intake.original_path(ctx, doc), doc["file_type"])
        conn.executemany(
            "INSERT INTO extracted_segments (document_id, page_number, segment_index, text) VALUES (?, ?, ?, ?)",
            [(doc["document_id"], s.page_number, s.segment_index, s.text) for s in segments],
        )
        rows = conn.execute("SELECT * FROM extracted_segments WHERE document_id = ? ORDER BY segment_index",
                            (doc["document_id"],)).fetchall()
    return [dict(r) for r in rows]


def _insert_candidate(conn, document_id, matter_id, rank, score, label, reasons, name, version, now):
    conn.execute(
        """INSERT INTO matter_candidates
           (candidate_id, document_id, matter_id, rank, score, uncertainty_label, reasons_json,
            matcher_name, matcher_version, created_at, review_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (new_id("CAND"), document_id, matter_id, rank, score, label, json.dumps(reasons),
         name, version, now, CANDIDATE),
    )


def _run_ai(ctx, doc, segments, matters, rule_results, start_rank, now) -> list[str]:
    """Call the (replaceable) AI service and store validated suggestions. Returns review problems."""
    service = ctx.ai_service
    if service is None:
        return []
    by_id = {s["segment_id"]: s for s in segments}
    payload_segments = [{"segment_id": s["segment_id"], "text": s["text"]} for s in segments]
    # Minimum permitted context only.
    matter_context = [{k: m[k] for k in ("matter_id", "client_name", "claim_number", "client_dob", "incident_date")}
                      for m in matters]
    try:
        raw = service.suggest(payload_segments, matter_context)
        suggestions, warnings = validate_ai_output(raw, {m["matter_id"] for m in matters}, set(by_id))
    except AIServiceError as exc:
        return [f"{exc} Result is based on rules only; retry when the AI service is working."]
    except Exception as exc:  # timeout, connection error, provider bug...
        return [f"AI service unavailable ({type(exc).__name__}). Result is based on rules only; "
                "retry when the AI service is working."]

    problems = []
    if warnings:
        problems.append(f"{len(warnings)} AI suggestion(s) were ignored because they failed validation.")
    threshold = ctx.settings.confidence_threshold
    for offset, s in enumerate(sorted(suggestions, key=lambda x: -x.confidence)):
        reasons = [{
            "code": "AI_SIGNAL",
            "label": f"AI service ({service.name}) cited "
                     f"{extraction.location_label(by_id[sid]['page_number'], by_id[sid]['segment_index'])}",
            "source": "document",
            "segment_id": sid,
            "location": extraction.location_label(by_id[sid]["page_number"], by_id[sid]["segment_index"]),
            "excerpt": " ".join(by_id[sid]["text"].split())[:160],
        } for sid in s.segment_ids]
        _insert_candidate(ctx.conn, doc["document_id"], s.matter_id, start_rank + offset, s.confidence,
                          matching.uncertainty_label(s.confidence, threshold), reasons,
                          f"ai:{service.name}", service.version, now)
    if suggestions and rule_results:
        ai_top = max(suggestions, key=lambda x: x.confidence).matter_id
        if ai_top != rule_results[0].matter_id:
            problems.append(f"Rule-based matcher ({rule_results[0].matter_id}) and AI service ({ai_top}) "
                            "disagree on the best matter.")
    return problems


def _document_text(conn, document_id) -> str:
    rows = conn.execute("SELECT text FROM extracted_segments WHERE document_id = ? ORDER BY segment_index",
                        (document_id,)).fetchall()
    return "\n".join(r["text"] for r in rows)


def _check_duplicates(conn, user, doc, segments, now) -> int:
    """Compare against documents this user may view. Returns number of new warnings."""
    new_text = "\n".join(s["text"] for s in segments)
    count = 0
    others = conn.execute("SELECT * FROM documents WHERE document_id != ? ORDER BY received_at",
                          (doc["document_id"],)).fetchall()
    for other in others:
        if not auth.can_view_document(conn, user, other):
            continue
        result = duplicates.compare(doc, new_text, other, _document_text(conn, other["document_id"]))
        if result is None:
            continue
        already_reviewed = conn.execute(
            """SELECT 1 FROM duplicate_candidates WHERE document_id = ? AND compared_document_id = ?
               AND flag_type = ? AND review_status != ?""",
            (doc["document_id"], other["document_id"], result.flag_type, SUPERSEDED),
        ).fetchone()
        if already_reviewed:
            continue  # a human already dispositioned this exact warning; don't duplicate it
        conn.execute(
            """INSERT INTO duplicate_candidates
               (flag_id, document_id, compared_document_id, flag_type, similarity, evidence_json,
                created_at, review_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_id("FLAG"), doc["document_id"], other["document_id"], result.flag_type,
             result.similarity, json.dumps(result.evidence), now, CANDIDATE),
        )
        count += 1
    return count


def _set_status(conn, document_id, status, reason, processing_ms=None):
    conn.execute("UPDATE documents SET status = ?, status_reason = ?, processing_ms = COALESCE(?, processing_ms) "
                 "WHERE document_id = ?", (status, reason, processing_ms, document_id))


def process_document(ctx, session, document_id: str) -> str:
    """Analyze a Received (or retryable) document. Returns the resulting status."""
    conn = ctx.conn
    user, doc = auth.require_document_access(conn, session, document_id, "analyze_document")
    if not (auth.has_permission(user, "upload") or auth.has_permission(user, "review")):
        auth.deny(conn, user["user_id"], "analyze_document", "document", document_id,
                  "role may not run analysis", document_id)
    if doc["status"] != RECEIVED and doc["status"] not in RETRYABLE_STATUSES:
        raise ValidationError(f"A document in status '{doc['status']}' cannot be analyzed.")

    started = time.perf_counter()
    _set_status(conn, document_id, PROCESSING, "Extracting text and generating candidates.")
    conn.commit()
    now = utc_now()
    try:
        segments = load_or_extract(ctx, doc)
        # Earlier un-reviewed candidates/warnings are kept for history but no longer active.
        conn.execute("UPDATE matter_candidates SET review_status = ? WHERE document_id = ? AND review_status = ?",
                     (SUPERSEDED, document_id, CANDIDATE))
        conn.execute("UPDATE duplicate_candidates SET review_status = ? WHERE document_id = ? AND review_status = ?",
                     (SUPERSEDED, document_id, CANDIDATE))

        permitted = auth.permitted_matter_ids(conn, user["user_id"])
        matters = [m for m in conn.execute("SELECT * FROM matters WHERE active = 1 ORDER BY matter_id")
                   if m["matter_id"] in permitted]
        metadata = {"filename": doc["filename"], "source description": doc["source_description"]}
        rule_results = matching.match_document(segments, metadata, matters)
        threshold = ctx.settings.confidence_threshold
        for rank, c in enumerate(rule_results, start=1):
            _insert_candidate(conn, document_id, c.matter_id, rank, c.score,
                              matching.uncertainty_label(c.score, threshold), c.reasons,
                              matching.MATCHER_NAME, matching.MATCHER_VERSION, now)

        ai_problems = _run_ai(ctx, doc, segments, matters, rule_results, len(rule_results) + 1, now)
        warning_count = _check_duplicates(conn, user, doc, segments, now)
        status, reason = decide_status([(c.matter_id, c.score) for c in rule_results], threshold,
                                       ctx.settings.ambiguity_margin, warning_count, ai_problems)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _set_status(conn, document_id, status, reason, elapsed_ms)
        audit.record(conn, user["user_id"], "analyze_document", "document", document_id, "success",
                     f"{len(rule_results)} rule candidate(s), {warning_count} duplicate/conflict warning(s); "
                     f"status {status}; {elapsed_ms} ms", document_id)
        conn.commit()
        return status
    except ExtractionError as exc:
        message = str(exc)
    except Exception as exc:  # never report success after an unexpected failure
        message = (f"Unexpected processing error ({type(exc).__name__}). The original file is preserved; "
                   "retry or review manually.")
    conn.rollback()
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    _set_status(conn, document_id, PROCESSING_FAILED, message, elapsed_ms)
    audit.record(conn, user["user_id"], "analyze_document", "document", document_id, "failed",
                 message, document_id)
    conn.commit()
    return PROCESSING_FAILED


def retry_processing(ctx, session, document_id: str) -> str:
    conn = ctx.conn
    user, doc = auth.require_document_access(conn, session, document_id, "retry_processing")
    if doc["status"] not in RETRYABLE_STATUSES:
        raise ValidationError(f"Retry is only available for: {', '.join(sorted(RETRYABLE_STATUSES))}.")
    audit.record(conn, user["user_id"], "retry_processing", "document", document_id, "requested",
                 f"previous status {doc['status']}", document_id)
    conn.commit()
    return process_document(ctx, session, document_id)


def intake_and_process(ctx, session, filename, data, source_type, source_description="") -> str:
    document_id = intake.register_document(ctx, session, filename, data, source_type, source_description)
    process_document(ctx, session, document_id)
    return document_id
