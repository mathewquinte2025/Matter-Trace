"""Load synthetic demo data and write sample upload files.

    python -m mattertrace.seed            # create data if the database is empty
    python -m mattertrace.seed --reset    # delete local demo data and start fresh
"""
import argparse
import secrets
import shutil

from . import audit, auth, intake, pipeline
from .config import CONFIRMED, PROJECT_ROOT, load_settings
from .sample_data import (DEMO_PASSWORD, EXISTING_DOCUMENTS, MATTERS, USERS, make_text_pdf,
                          sample_upload_files)

SAMPLE_DIR = PROJECT_ROOT / "sample_docs"


def seed(ctx) -> None:
    conn = ctx.conn
    for user_id, username, display_name, role, matter_ids in USERS:
        salt = secrets.token_hex(16)
        conn.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                     (user_id, username, display_name, role, salt, auth.hash_password(DEMO_PASSWORD, salt)))
    conn.executemany(
        "INSERT INTO matters (matter_id, display_label, client_name, client_dob, incident_date, claim_number, insurer) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", MATTERS)
    for user_id, _, _, _, matter_ids in USERS:
        conn.executemany("INSERT INTO matter_access VALUES (?, ?)", [(user_id, m) for m in matter_ids])
    conn.commit()

    # Baseline records "already on file". They are inserted as confirmed seed data
    # (not through a fake human review) and the audit log says so.
    sessions = {u[0]: auth.AuthSession(u[0], u[1], u[2], u[3]) for u in USERS}
    for filename, matter_id, kind, content, user_id, source_type in EXISTING_DOCUMENTS:
        data = make_text_pdf(content) if kind == "pdf" else content.encode("utf-8")
        doc_id = intake.register_document(ctx, sessions[user_id], filename, data, source_type,
                                          "Seeded synthetic baseline record")
        doc = conn.execute("SELECT * FROM documents WHERE document_id = ?", (doc_id,)).fetchone()
        pipeline.load_or_extract(ctx, doc)
        conn.execute("UPDATE documents SET matter_id = ?, status = ?, status_reason = ? WHERE document_id = ?",
                     (matter_id, CONFIRMED, "Seeded baseline record (synthetic test data).", doc_id))
        audit.record(conn, "system", "seed_baseline_record", "document", doc_id, "success",
                     f"seeded as existing record for {matter_id}", doc_id)
        conn.commit()


def write_sample_uploads(directory=SAMPLE_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in sample_upload_files().items():
        (directory / name).write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the local demo database and stored files first")
    args = parser.parse_args()
    settings = load_settings()
    if args.reset:
        if settings.db_path.exists():
            settings.db_path.unlink()
        if settings.originals_dir.exists():
            shutil.rmtree(settings.originals_dir)
        print(f"Removed demo data in {settings.data_dir}")
    from .context import open_context
    ctx = open_context(settings)
    write_sample_uploads()
    users = ctx.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    docs = ctx.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    print(f"Database: {settings.db_path} ({users} users, {docs} documents)")
    print(f"Sample upload files: {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
