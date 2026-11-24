"""FR-01, FR-10 (input validation), NFR-11: intake, metadata, original preservation."""
import hashlib

import pytest

from conftest import audit_rows, doc_row
from mattertrace import auth, intake
from mattertrace.errors import AuthorizationError, ValidationError


def test_valid_upload_registers_metadata_and_preserves_original(ctx, sessions):
    data = b"Patient: Daniel Reyes\nDOB 03/14/1985\n"
    doc_id = intake.register_document(ctx, sessions["pat"], "note.txt", data, "Mail", "mailed by clinic")
    doc = doc_row(ctx, doc_id)
    assert doc_id.startswith("DOC-")
    assert doc["filename"] == "note.txt"
    assert doc["file_type"] == "txt"
    assert doc["source_type"] == "Mail"
    assert doc["source_description"] == "mailed by clinic"
    assert doc["submitting_user_id"] == "U-PAT"
    assert doc["received_at"]
    assert doc["status"] == "Received"
    assert doc["matter_id"] is None
    stored = intake.original_path(ctx, doc).read_bytes()
    assert stored == data
    assert doc["checksum_sha256"] == hashlib.sha256(data).hexdigest()
    assert audit_rows(ctx, action="upload_document", object_id=doc_id, outcome="success")


@pytest.mark.parametrize("filename,data,source,message", [
    ("report.docx", b"abc", "Email", "Unsupported file type"),
    ("empty.txt", b"", "Email", "empty"),
    ("note.txt", b"abc", "", "Source type is required"),
    ("note.txt", b"abc", "Carrier pigeon", "Unknown source type"),
])
def test_invalid_uploads_are_rejected_with_clear_message_and_logged(ctx, sessions, filename, data, source, message):
    with pytest.raises(ValidationError, match=message):
        intake.register_document(ctx, sessions["pat"], filename, data, source)
    assert ctx.conn.execute("SELECT COUNT(*) FROM documents WHERE filename = ?", (filename,)).fetchone()[0] == 0
    assert audit_rows(ctx, action="upload_document", outcome="rejected")


def test_filename_path_components_are_stripped(ctx, sessions):
    doc_id = intake.register_document(ctx, sessions["pat"], "../../etc/evil.txt", b"text", "Email")
    assert doc_row(ctx, doc_id)["filename"] == "evil.txt"


def test_document_identity_fields_cannot_be_changed_or_deleted(ctx, sessions):
    doc_id = intake.register_document(ctx, sessions["pat"], "a.txt", b"text", "Email")
    with pytest.raises(Exception, match="immutable"):
        ctx.conn.execute("UPDATE documents SET checksum_sha256 = 'x' WHERE document_id = ?", (doc_id,))
    with pytest.raises(Exception, match="cannot be deleted"):
        ctx.conn.execute("DELETE FROM documents WHERE document_id = ?", (doc_id,))


def test_login_rejects_bad_password_and_logs_it(ctx):
    assert auth.login(ctx.conn, "pat", "wrong") is None
    assert audit_rows(ctx, action="login", outcome="denied")


def test_unauthenticated_upload_is_refused(ctx):
    with pytest.raises(AuthorizationError):
        intake.register_document(ctx, None, "a.txt", b"text", "Email")
