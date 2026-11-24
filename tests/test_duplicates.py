"""FR-04, FR-08, NFR-11: duplicate/conflict warnings and preservation of both documents."""
import hashlib

from conftest import doc_row
from mattertrace import intake, review
from mattertrace.config import NEEDS_REVIEW


def seeded_bill(ctx):
    return ctx.conn.execute("SELECT * FROM documents WHERE filename = 'Reyes_ER_Bill_INV-44817.pdf'").fetchone()


def flags_for(ctx, doc_id):
    return ctx.conn.execute("SELECT * FROM duplicate_candidates WHERE document_id = ?", (doc_id,)).fetchall()


def test_exact_duplicate_is_flagged_and_both_files_preserved(ctx, sessions, upload):
    original = seeded_bill(ctx)
    before = intake.original_path(ctx, original).read_bytes()
    doc_id = upload("02_duplicate_reyes_er_bill.pdf")
    flags = flags_for(ctx, doc_id)
    assert [(f["flag_type"], f["compared_document_id"]) for f in flags] == [("exact_duplicate", original["document_id"])]
    assert doc_row(ctx, doc_id)["status"] == NEEDS_REVIEW
    # Both documents still exist, unchanged, and readable through the authorized path.
    assert intake.read_original(ctx, sessions["pat"], original["document_id"]) == before
    new = doc_row(ctx, doc_id)
    assert hashlib.sha256(intake.read_original(ctx, sessions["pat"], doc_id)).hexdigest() == new["checksum_sha256"]
    assert doc_row(ctx, original["document_id"])["status"] == "Confirmed"  # existing record untouched


def test_conflicting_version_is_flagged_with_reason(ctx, upload):
    doc_id = upload("03_conflicting_reyes_er_bill.txt")
    flags = flags_for(ctx, doc_id)
    assert len(flags) == 1 and flags[0]["flag_type"] == "possible_conflict"
    assert "INV-44817" in flags[0]["evidence_json"] and "2890.00" in flags[0]["evidence_json"]


def test_revised_letter_is_flagged_as_near_duplicate(ctx, upload):
    flags = flags_for(ctx, upload("08_okafor_insurer_letter_revised.txt"))
    assert [f["flag_type"] for f in flags] == ["near_duplicate"]


def test_unrelated_document_is_not_flagged(ctx, upload):
    assert flags_for(ctx, upload("01_clear_match_reyes_records_request.txt")) == []


def test_duplicate_check_does_not_compare_against_unauthorized_documents(ctx, upload, samples):
    # The seeded MT-1001 bill is invisible to Riley, so Riley's identical upload is not linked to it.
    doc_id = upload("02_duplicate_reyes_er_bill.pdf", user="riley")
    assert flags_for(ctx, doc_id) == []


def test_flag_review_never_deletes_documents(ctx, sessions, upload):
    doc_id = upload("02_duplicate_reyes_er_bill.pdf")
    flag = flags_for(ctx, doc_id)[0]
    count = ctx.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    assert review.submit_flag_decision(ctx, sessions["pat"], flag["flag_id"], "confirm") == "Confirmed"
    assert ctx.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == count
    assert intake.original_path(ctx, doc_row(ctx, doc_id)).exists()
    assert intake.original_path(ctx, doc_row(ctx, flag["compared_document_id"])).exists()
