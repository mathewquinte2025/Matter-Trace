"""Document intake and original-file preservation (components 1 and 3)."""
import hashlib
import re
import uuid
from pathlib import Path

from . import audit, auth
from .config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, RECEIVED, SOURCE_TYPES
from .db import utc_now
from .errors import ValidationError


def new_document_id() -> str:
    return f"DOC-{uuid.uuid4().hex[:12].upper()}"


def safe_filename(name: str) -> str:
    name = Path(name or "").name  # strip any directory components
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip()
    return name[:200]


def validate_upload(filename: str, data: bytes, source_type: str) -> list[str]:
    errors = []
    ext = Path(filename or "").suffix.lower()
    if not filename:
        errors.append("A file name is required.")
    elif ext not in ALLOWED_EXTENSIONS:
        errors.append(f"Unsupported file type '{ext or '(none)'}'. Only PDF and TXT files are accepted.")
    if not data:
        errors.append("The file is empty.")
    elif len(data) > MAX_UPLOAD_BYTES:
        errors.append(f"The file is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    if not source_type:
        errors.append("Source type is required (where did this document come from?).")
    elif source_type not in SOURCE_TYPES:
        errors.append(f"Unknown source type '{source_type}'.")
    return errors


def register_document(ctx, session, filename: str, data: bytes, source_type: str,
                      source_description: str = "", received_at: str | None = None) -> str:
    """Validate, store the original file, and create the DocumentRecord.

    Returns the new stable document_id. Rejected uploads raise ValidationError
    with a clear message and are logged; nothing is silently discarded.
    """
    conn = ctx.conn
    user = auth.require_permission(conn, session, "upload", "upload_document", "document")

    clean_name = safe_filename(filename)
    errors = validate_upload(clean_name, data, source_type)
    if errors:
        audit.record(conn, user["user_id"], "upload_document", "document", None, "rejected",
                     f"file '{clean_name}': " + " ".join(errors))
        conn.commit()
        raise ValidationError(" ".join(errors))

    ext = Path(clean_name).suffix.lower()
    document_id = new_document_id()
    stored_path = ctx.settings.originals_dir / f"{document_id}{ext}"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    # Original is written once ("x" mode never overwrites an existing file).
    with open(stored_path, "xb") as fh:
        fh.write(data)

    conn.execute(
        """INSERT INTO documents
           (document_id, original_file_ref, filename, file_type, size_bytes, checksum_sha256,
            received_at, source_type, source_description, submitting_user_id, status, status_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            document_id, stored_path.name, clean_name, ALLOWED_EXTENSIONS[ext], len(data),
            hashlib.sha256(data).hexdigest(), received_at or utc_now(), source_type,
            (source_description or "").strip(), user["user_id"], RECEIVED,
            "Registered; waiting for analysis.",
        ),
    )
    audit.record(conn, user["user_id"], "upload_document", "document", document_id, "success",
                 f"{clean_name} ({len(data)} bytes) from {source_type}", document_id)
    conn.commit()
    return document_id


def original_path(ctx, doc) -> Path:
    return ctx.settings.originals_dir / doc["original_file_ref"]


def read_original(ctx, session, document_id: str) -> bytes:
    """Authorized read of the preserved original file."""
    user, doc = auth.require_document_access(ctx.conn, session, document_id, "download_original")
    audit.record(ctx.conn, user["user_id"], "download_original", "document", document_id, "success",
                 "", document_id)
    ctx.conn.commit()
    return original_path(ctx, doc).read_bytes()
