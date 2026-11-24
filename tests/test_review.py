"""FR-05, FR-06, FR-07, FR-09, NFR-02, NFR-04, NFR-09: review actions, authorization, history."""
import pytest

from conftest import audit_rows, doc_row
from mattertrace import auth, review
from mattertrace.errors import AuthorizationError, ValidationError


def top_candidate(ctx, doc_id):
    return ctx.conn.execute("SELECT * FROM matter_candidates WHERE document_id = ? AND review_status = 'Candidate' "
                            "ORDER BY rank", (doc_id,)).fetchone()


def decisions(ctx, doc_id):
    return ctx.conn.execute("SELECT * FROM review_decisions WHERE document_id = ? ORDER BY rowid", (doc_id,)).fetchall()


def test_confirm_records_reviewer_from_session(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    cand = top_candidate(ctx, doc_id)
    assert review.submit_matter_decision(ctx, sessions["pat"], doc_id, "confirm", candidate_id=cand["candidate_id"]) == "Confirmed"
    doc = doc_row(ctx, doc_id)
    assert doc["matter_id"] == "MT-1001" and doc["status"] == "Confirmed"
    [d] = decisions(ctx, doc_id)
    assert (d["reviewer_id"], d["action"], d["target_id"], d["previous_status"], d["resulting_status"]) == \
        ("U-PAT", "confirm", cand["candidate_id"], "Candidate Ready", "Confirmed")
    assert d["timestamp"]
    assert audit_rows(ctx, action="review_confirm", actor_id="U-PAT", object_id=doc_id)


def test_correct_keeps_original_candidate_in_history(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    cand = top_candidate(ctx, doc_id)
    review.submit_matter_decision(ctx, sessions["pat"], doc_id, "correct", corrected_matter_id="MT-1004")
    doc = doc_row(ctx, doc_id)
    assert doc["matter_id"] == "MT-1004" and doc["status"] == "Corrected"
    original = ctx.conn.execute("SELECT * FROM matter_candidates WHERE candidate_id = ?", (cand["candidate_id"],)).fetchone()
    assert original["matter_id"] == "MT-1001" and original["review_status"] == "Corrected"
    [d] = decisions(ctx, doc_id)
    assert d["target_id"] == cand["candidate_id"] and d["corrected_matter_id"] == "MT-1004"


def test_history_survives_multiple_decisions(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    cand = top_candidate(ctx, doc_id)
    review.submit_matter_decision(ctx, sessions["pat"], doc_id, "confirm", candidate_id=cand["candidate_id"])
    review.submit_matter_decision(ctx, sessions["pat"], doc_id, "correct", corrected_matter_id="MT-1002")
    review.submit_matter_decision(ctx, sessions["avery"], doc_id, "correct", corrected_matter_id="MT-1001")
    trail = [(d["reviewer_id"], d["action"], d["previous_status"], d["resulting_status"]) for d in decisions(ctx, doc_id)]
    assert trail == [("U-PAT", "confirm", "Candidate Ready", "Confirmed"),
                     ("U-PAT", "correct", "Confirmed", "Corrected"),
                     ("U-AVERY", "correct", "Corrected", "Corrected")]
    assert doc_row(ctx, doc_id)["matter_id"] == "MT-1001"


def test_reject_and_escalate_require_a_note(ctx, sessions, upload):
    doc_id = upload("05_low_confidence_fax_cover.txt")
    for action in ("reject", "escalate"):
        with pytest.raises(ValidationError, match="note"):
            review.submit_matter_decision(ctx, sessions["pat"], doc_id, action)
    assert review.submit_matter_decision(ctx, sessions["pat"], doc_id, "reject", note="Not enough information") == "Rejected"
    assert doc_row(ctx, doc_id)["matter_id"] is None


def test_escalated_item_can_only_be_resolved_by_attorney(ctx, sessions, upload):
    doc_id = upload("04_ambiguous_two_clients.txt")
    review.submit_matter_decision(ctx, sessions["pat"], doc_id, "escalate", note="Two clients in one fax")
    cand = top_candidate(ctx, doc_id)
    with pytest.raises(AuthorizationError):
        review.submit_matter_decision(ctx, sessions["pat"], doc_id, "confirm", candidate_id=cand["candidate_id"])
    assert audit_rows(ctx, action="review_confirm", actor_id="U-PAT", outcome="denied")
    assert review.submit_matter_decision(ctx, sessions["avery"], doc_id, "confirm",
                                         candidate_id=cand["candidate_id"]) == "Confirmed"


def test_intake_clerk_cannot_confirm_even_by_calling_the_service(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt", user="casey")
    cand = top_candidate(ctx, doc_id)
    assert review.get_review_bundle(ctx, sessions["casey"], doc_id)["allowed_actions"] == []
    with pytest.raises(AuthorizationError):
        review.submit_matter_decision(ctx, sessions["casey"], doc_id, "confirm", candidate_id=cand["candidate_id"])
    assert doc_row(ctx, doc_id)["status"] == "Candidate Ready"  # still unconfirmed
    assert audit_rows(ctx, actor_id="U-CASEY", action="review_confirm", outcome="denied")


def test_cross_matter_access_is_denied_and_logged(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    cand = top_candidate(ctx, doc_id)
    review.submit_matter_decision(ctx, sessions["pat"], doc_id, "confirm", candidate_id=cand["candidate_id"])
    # Riley has no access to MT-1001: view, download, and review are all refused.
    with pytest.raises(AuthorizationError):
        review.get_review_bundle(ctx, sessions["riley"], doc_id)
    from mattertrace import intake
    with pytest.raises(AuthorizationError):
        intake.read_original(ctx, sessions["riley"], doc_id)
    with pytest.raises(AuthorizationError):
        review.submit_matter_decision(ctx, sessions["riley"], doc_id, "correct", corrected_matter_id="MT-1003")
    denied = audit_rows(ctx, actor_id="U-RILEY", outcome="denied")
    assert {e["action"] for e in denied} >= {"view_document", "download_original", "review_correct"}
    assert doc_id not in [d["document_id"] for d in review.list_documents(ctx, sessions["riley"])]


def test_cannot_correct_to_a_matter_the_reviewer_cannot_access(ctx, sessions, upload):
    doc_id = upload("05_low_confidence_fax_cover.txt")
    with pytest.raises(AuthorizationError):
        review.submit_matter_decision(ctx, sessions["pat"], doc_id, "correct", corrected_matter_id="MT-1003")
    assert doc_row(ctx, doc_id)["matter_id"] is None


def test_invalid_requests_are_rejected(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    with pytest.raises(ValidationError):
        review.submit_matter_decision(ctx, sessions["pat"], doc_id, "approve")
    with pytest.raises(ValidationError):
        review.submit_matter_decision(ctx, sessions["pat"], doc_id, "confirm", candidate_id="CAND-DOESNOTEXIST")
    with pytest.raises(ValidationError):
        review.submit_matter_decision(ctx, sessions["pat"], doc_id, "correct", corrected_matter_id="MT-9999")
    assert doc_row(ctx, doc_id)["status"] == "Candidate Ready"


def test_failed_document_cannot_be_confirmed_only_manually_assigned(ctx, sessions, upload):
    doc_id = upload("06_scanned_image_only.pdf")
    assert review.allowed_matter_actions(auth.load_user(ctx.conn, sessions["pat"]), doc_row(ctx, doc_id)) == \
        ["correct", "escalate"]
    with pytest.raises(ValidationError):
        review.submit_matter_decision(ctx, sessions["pat"], doc_id, "confirm", candidate_id="anything")
    assert review.submit_matter_decision(ctx, sessions["pat"], doc_id, "correct", corrected_matter_id="MT-1001") == "Corrected"


def test_flag_dismiss_requires_note_and_cannot_be_reviewed_twice(ctx, sessions, upload):
    doc_id = upload("02_duplicate_reyes_er_bill.pdf")
    flag_id = ctx.conn.execute("SELECT flag_id FROM duplicate_candidates WHERE document_id = ?", (doc_id,)).fetchone()[0]
    with pytest.raises(ValidationError):
        review.submit_flag_decision(ctx, sessions["pat"], flag_id, "reject")
    with pytest.raises(AuthorizationError):
        review.submit_flag_decision(ctx, sessions["casey"], flag_id, "confirm")
    assert review.submit_flag_decision(ctx, sessions["pat"], flag_id, "reject", note="Different visit") == "Rejected"
    with pytest.raises(ValidationError, match="already reviewed"):
        review.submit_flag_decision(ctx, sessions["pat"], flag_id, "confirm")
    d = decisions(ctx, doc_id)[-1]
    assert (d["target_type"], d["target_id"], d["reviewer_id"], d["note"]) == ("duplicate_flag", flag_id, "U-PAT", "Different visit")


def test_audit_and_decision_history_are_append_only(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    review.submit_matter_decision(ctx, sessions["pat"], doc_id, "escalate", note="check")
    for table in ("audit_events", "review_decisions"):
        with pytest.raises(Exception, match="append-only"):
            ctx.conn.execute(f"UPDATE {table} SET timestamp = 'x'")
        with pytest.raises(Exception, match="append-only"):
            ctx.conn.execute(f"DELETE FROM {table}")


def test_full_audit_log_is_attorney_only(ctx, sessions):
    assert review.full_audit_log(ctx, sessions["avery"])
    with pytest.raises(AuthorizationError):
        review.full_audit_log(ctx, sessions["pat"])
