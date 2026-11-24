import pytest

from mattertrace import auth, pipeline
from mattertrace.config import Settings
from mattertrace.context import open_context
from mattertrace.sample_data import DEMO_PASSWORD, sample_upload_files


@pytest.fixture
def ctx(tmp_path):
    context = open_context(Settings(data_dir=tmp_path / "data"))
    yield context
    context.conn.close()


@pytest.fixture
def sessions(ctx):
    return {name: auth.login(ctx.conn, name, DEMO_PASSWORD) for name in ("pat", "riley", "avery", "casey")}


@pytest.fixture
def samples():
    return sample_upload_files()


@pytest.fixture
def upload(ctx, sessions, samples):
    """upload("01_clear_match_reyes_records_request.txt", user="pat") -> document_id"""
    def _upload(name, user="pat", data=None, source_type="Email"):
        return pipeline.intake_and_process(ctx, sessions[user], name,
                                           samples[name] if data is None else data, source_type)
    return _upload


def doc_row(ctx, document_id):
    return ctx.conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()


def audit_rows(ctx, **filters):
    where = " AND ".join(f"{k} = ?" for k in filters) or "1=1"
    return ctx.conn.execute(f"SELECT * FROM audit_events WHERE {where}", tuple(filters.values())).fetchall()
