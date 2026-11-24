"""FR-10, NFR-07, NFR-10: failures, AI output safety, retry, and response time (NFR-06)."""
import time

import pytest

from conftest import doc_row
from mattertrace import intake, pipeline, review
from mattertrace.config import CANDIDATE_READY, NEEDS_REVIEW, PROCESSING_FAILED
from mattertrace.errors import ValidationError
from mattertrace.sample_data import make_text_pdf


@pytest.mark.parametrize("name", ["06_scanned_image_only.pdf", "07_corrupted_file.pdf"])
def test_unreadable_pdf_fails_visibly_and_keeps_original(ctx, sessions, upload, samples, name):
    doc_id = upload(name)
    doc = doc_row(ctx, doc_id)
    assert doc["status"] == PROCESSING_FAILED
    assert doc["status_reason"]  # explains what went wrong
    assert intake.read_original(ctx, sessions["pat"], doc_id) == samples[name]
    assert review.get_review_bundle(ctx, sessions["pat"], doc_id)["can_retry"]


def test_binary_data_in_txt_fails_visibly(ctx, upload):
    doc = doc_row(ctx, upload("weird.txt", data=b"\x00\x01\x02binary"))
    assert doc["status"] == PROCESSING_FAILED and "binary" in doc["status_reason"]


def test_failed_document_without_candidates_is_routed_to_attorney(ctx, sessions, upload):
    doc_id = upload("06_scanned_image_only.pdf", user="casey")
    assert doc_id in [d["document_id"] for d in review.list_documents(ctx, sessions["avery"])]
    assert doc_id not in [d["document_id"] for d in review.list_documents(ctx, sessions["pat"])]


class BrokenAI:
    name, version = "broken", "test"

    def __init__(self, behavior):
        self.behavior = behavior

    def suggest(self, segments, matter_context):
        if self.behavior == "timeout":
            raise TimeoutError("model timed out")
        if self.behavior == "malformed":
            return "Sure! The matter is MT-1001."
        if self.behavior == "hallucinated":
            return {"candidates": [{"matter_id": "MT-9999", "confidence": 0.99, "evidence_segment_ids": [1]}]}
        if self.behavior == "unauthorized":
            return {"candidates": [{"matter_id": "MT-1003", "confidence": 0.9,
                                    "evidence_segment_ids": [segments[0]["segment_id"]]}]}
        if self.behavior == "untraceable":
            return {"candidates": [{"matter_id": "MT-1001", "confidence": 0.9, "evidence_segment_ids": [123456]}]}
        if self.behavior == "valid":
            return {"candidates": [{"matter_id": "MT-1001", "confidence": 0.8,
                                    "evidence_segment_ids": [segments[0]["segment_id"]]}]}


@pytest.mark.parametrize("behavior,expected_text", [
    ("timeout", "AI service unavailable"),
    ("malformed", "malformed output"),
    ("hallucinated", "ignored"),
    ("unauthorized", "ignored"),
    ("untraceable", "ignored"),
])
def test_bad_ai_output_goes_to_review_never_confirmed(ctx, upload, behavior, expected_text):
    ctx.ai_service = BrokenAI(behavior)
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    doc = doc_row(ctx, doc_id)
    assert doc["status"] == NEEDS_REVIEW and doc["matter_id"] is None
    assert expected_text in doc["status_reason"]
    ai_rows = ctx.conn.execute("SELECT * FROM matter_candidates WHERE document_id = ? AND matcher_name LIKE 'ai:%'",
                               (doc_id,)).fetchall()
    assert ai_rows == []  # nothing invalid was stored
    # No raw model text is stored anywhere.
    assert "Sure!" not in str([dict(r) for r in ctx.conn.execute("SELECT * FROM matter_candidates")])


def test_valid_ai_suggestion_is_stored_as_traceable_candidate(ctx, sessions, upload):
    ctx.ai_service = BrokenAI("valid")
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    cands = review.get_review_bundle(ctx, sessions["pat"], doc_id)["active_candidates"]
    ai = [c for c in cands if c["matcher_name"] == "ai:broken"]
    assert len(ai) == 1 and ai[0]["review_status"] == "Candidate"
    assert ai[0]["reasons"][0]["segment_id"] in {s["segment_id"] for s in review.get_review_bundle(
        ctx, sessions["pat"], doc_id)["segments"]}
    assert doc_row(ctx, doc_id)["status"] == CANDIDATE_READY  # agrees with the rules; still needs a human


def test_retry_after_ai_recovers_keeps_same_document_and_history(ctx, sessions, upload):
    ctx.ai_service = BrokenAI("timeout")
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    assert doc_row(ctx, doc_id)["status"] == NEEDS_REVIEW
    docs_before = ctx.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    ctx.ai_service = BrokenAI("valid")
    assert pipeline.retry_processing(ctx, sessions["pat"], doc_id) == CANDIDATE_READY
    assert ctx.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == docs_before  # no duplicate record
    statuses = [r["review_status"] for r in ctx.conn.execute(
        "SELECT review_status FROM matter_candidates WHERE document_id = ? ORDER BY created_at", (doc_id,))]
    assert "Superseded" in statuses and "Candidate" in statuses  # old candidates kept for history
    assert ctx.conn.execute("SELECT COUNT(*) FROM extracted_segments WHERE document_id = ?", (doc_id,)).fetchone()[0] \
        == 4  # segments not duplicated
    events = [e["action"] for e in ctx.conn.execute(
        "SELECT action FROM audit_events WHERE document_id = ? ORDER BY event_id", (doc_id,))]
    assert events.count("analyze_document") == 2 and "retry_processing" in events


def test_retry_not_allowed_on_confirmed_document(ctx, sessions, upload):
    doc_id = upload("01_clear_match_reyes_records_request.txt")
    cand = ctx.conn.execute("SELECT candidate_id FROM matter_candidates WHERE document_id = ?", (doc_id,)).fetchone()[0]
    review.submit_matter_decision(ctx, sessions["pat"], doc_id, "confirm", candidate_id=cand)
    with pytest.raises(ValidationError):
        pipeline.retry_processing(ctx, sessions["pat"], doc_id)


def test_unexpected_error_becomes_processing_failed(ctx, upload, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(pipeline.matching, "match_document", explode)
    doc = doc_row(ctx, upload("01_clear_match_reyes_records_request.txt"))
    assert doc["status"] == PROCESSING_FAILED
    assert "RuntimeError" in doc["status_reason"] and "boom" not in doc["status_reason"]  # no internals leaked
    assert ctx.conn.execute("SELECT COUNT(*) FROM matter_candidates WHERE document_id = ?",
                            (doc["document_id"],)).fetchone()[0] == 0  # partial work rolled back


def test_twenty_page_pdf_is_ready_for_review_within_two_minutes(ctx, sessions):
    filler = "\n".join(f"Line {i}: routine treatment note for the synthetic patient." for i in range(40))
    pages = [f"Patient: Grace Okafor\nDOB: 11/02/1990\nClaim Number: SG-55107\nPage {p}\n{filler}"
             for p in range(1, 21)]
    start = time.perf_counter()
    doc_id = pipeline.intake_and_process(ctx, sessions["pat"], "twenty_pages.pdf", make_text_pdf(pages), "Insurer")
    elapsed = time.perf_counter() - start
    doc = doc_row(ctx, doc_id)
    print(f"\nNFR-06: 20-page PDF ready for review in {elapsed:.2f}s (pipeline recorded {doc['processing_ms']} ms)")
    assert doc["status"] == CANDIDATE_READY
    assert ctx.conn.execute("SELECT COUNT(*) FROM extracted_segments WHERE document_id = ?", (doc_id,)).fetchone()[0] == 20
    assert elapsed < 120
