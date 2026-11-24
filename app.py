"""MatterTrace Streamlit interface: login, intake, review workbench, audit history.

Run with:  streamlit run app.py
The UI only calls service functions; every authorization and status rule is
enforced inside those functions (mattertrace/review.py, pipeline.py, auth.py).
"""
import streamlit as st

from mattertrace import auth, intake, pipeline, review
from mattertrace.config import SOURCE_TYPES
from mattertrace.context import open_context
from mattertrace.errors import AuthorizationError, ValidationError
from mattertrace.extraction import location_label
from mattertrace.seed import SAMPLE_DIR, write_sample_uploads

st.set_page_config(page_title="MatterTrace", layout="wide")

STATUS_COLORS = {
    "Received": "gray", "Processing": "gray", "Candidate Ready": "blue", "Needs Review": "orange",
    "Confirmed": "green", "Corrected": "green", "Rejected": "gray", "Escalated": "violet",
    "Processing Failed": "red", "Candidate": "blue", "Superseded": "gray",
}
MATTER_ACTION_LABELS = {
    "confirm": "Confirm the suggested matter",
    "correct": "Correct: assign a different matter",
    "reject": "Reject the suggestion(s)",
    "escalate": "Escalate to a supervising attorney",
}
FLAG_ACTION_LABELS = {"confirm": "Confirm warning", "reject": "Dismiss warning", "escalate": "Escalate"}


@st.cache_resource
def _initialize() -> bool:
    """Create and seed the database and sample files once per server process."""
    ctx = open_context()
    ctx.conn.close()
    if not SAMPLE_DIR.exists():
        write_sample_uploads()
    return True


def get_ctx():
    _initialize()
    return open_context(seed_if_empty=False)  # one connection per script run


def badge(status: str) -> str:
    return f":{STATUS_COLORS.get(status, 'gray')}[**{status}**]"


def user_names(ctx) -> dict:
    return {r["user_id"]: r["display_name"] for r in ctx.conn.execute("SELECT user_id, display_name FROM users")}


# ---------------------------------------------------------------- login
def login_view(ctx):
    st.title("MatterTrace")
    st.caption("Source-traceable document intake and matter association (prototype, synthetic data only)")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            session = auth.login(ctx.conn, username, password)
            if session:
                st.session_state.auth = session
                st.rerun()
            st.error("Invalid username or password.")
    with st.expander("Demo accounts (synthetic)"):
        st.markdown(
            "| Username | Role | Matters |\n|---|---|---|\n"
            "| pat | Paralegal | MT-1001, MT-1002, MT-1004 |\n"
            "| riley | Paralegal | MT-1003 |\n"
            "| avery | Supervising attorney | all; resolves escalations; full audit log |\n"
            "| casey | Intake clerk | all; can upload but cannot review |\n\n"
            "Password for all demo accounts: `demo123`"
        )


# ---------------------------------------------------------------- intake
def intake_view(ctx, session):
    st.header("Document intake")
    st.write(f"Upload a PDF or TXT file. Sample files are in `{SAMPLE_DIR.name}/`.")
    with st.form("upload", clear_on_submit=True):
        uploaded = st.file_uploader("Document (PDF or TXT)")
        source_type = st.selectbox("Source type (required)", SOURCE_TYPES, index=None,
                                   placeholder="Where did this document come from?")
        source_description = st.text_input("Source description (optional)",
                                           placeholder="e.g. emailed by Gulf Coast Medical Center billing")
        submitted = st.form_submit_button("Register and analyze")
    if submitted:
        if uploaded is None:
            st.error("Choose a file to upload.")
            return
        try:
            doc_id = pipeline.intake_and_process(ctx, session, uploaded.name, uploaded.getvalue(),
                                                 source_type or "", source_description)
        except (ValidationError, AuthorizationError) as exc:
            st.error(f"Upload rejected: {exc}")
            return
        doc = ctx.conn.execute("SELECT * FROM documents WHERE document_id = ?", (doc_id,)).fetchone()
        st.success(f"Registered **{doc_id}** ({doc['filename']}). The original file is preserved.")
        st.markdown(f"Status: {badge(doc['status'])} - {doc['status_reason']}")
        st.session_state.selected_doc = doc_id
        st.info("Open **Review queue** in the sidebar to review this document.")


# ---------------------------------------------------------------- review
def review_view(ctx, session):
    st.header("Review queue")
    docs = review.list_documents(ctx, session)
    names = user_names(ctx)
    show_all = st.toggle("Include completed documents", value=False)
    open_statuses = {"Candidate Ready", "Needs Review", "Escalated", "Processing Failed", "Received", "Processing"}
    shown = [d for d in docs if show_all or d["status"] in open_statuses]
    if shown:
        st.dataframe(
            [{"Document ID": d["document_id"], "File": d["filename"], "Status": d["status"],
              "Matter": d["matter_label"] or "(not associated)", "Source": d["source_type"],
              "Received (UTC)": d["received_at"], "Submitted by": names.get(d["submitting_user_id"], "")}
             for d in shown],
            hide_index=True, width="stretch",
        )
    else:
        st.info("No documents need review.")

    ids = [d["document_id"] for d in shown]
    labels = {d["document_id"]: f"{d['document_id']} | {d['filename']} | {d['status']}" for d in shown}
    col1, col2 = st.columns([3, 2])
    preselect = st.session_state.get("selected_doc")
    choice = col1.selectbox("Open document", ids, format_func=labels.get,
                            index=ids.index(preselect) if preselect in ids else None)
    typed = col2.text_input("...or open by document ID").strip().upper()
    doc_id = typed or choice
    if not doc_id:
        return
    st.session_state.selected_doc = doc_id
    first_view = st.session_state.get("last_viewed") != doc_id
    try:
        bundle = review.get_review_bundle(ctx, session, doc_id, log_view=first_view)
    except AuthorizationError as exc:
        st.error(f"Access denied: {exc}. This attempt was recorded in the audit log.")
        return
    st.session_state.last_viewed = doc_id
    st.divider()
    render_bundle(ctx, session, bundle, names)


def render_bundle(ctx, session, b, names):
    doc = b["document"]
    st.subheader(f"{doc['filename']}  ({doc['document_id']})")
    st.markdown(f"Status: {badge(doc['status'])}")
    st.write(doc["status_reason"])
    if doc["status"] in ("Candidate Ready", "Needs Review"):
        st.info("The suggestions below were generated automatically. They are **candidates only**; "
                "nothing is associated with a matter until an authorized reviewer acts.")

    with st.expander("Source and intake metadata", expanded=False):
        st.markdown(
            f"- **Source:** {doc['source_type']}" + (f" - {doc['source_description']}" if doc['source_description'] else "")
            + f"\n- **Received (UTC):** {doc['received_at']}"
            + f"\n- **Submitted by:** {names.get(doc['submitting_user_id'], doc['submitting_user_id'])}"
            + f"\n- **File type / size:** {doc['file_type'].upper()} / {doc['size_bytes']:,} bytes"
            + f"\n- **SHA-256:** `{doc['checksum_sha256']}`"
            + f"\n- **Associated matter:** {doc['matter_label'] or '(not associated)'}"
            + (f"\n- **Processing time:** {doc['processing_ms']} ms" if doc["processing_ms"] is not None else "")
        )
        key = f"orig_{doc['document_id']}"
        if st.button("Load original file for download", key=f"load_{key}"):
            st.session_state[key] = intake.read_original(ctx, session, doc["document_id"])
        if key in st.session_state:
            st.download_button("Download original", st.session_state[key], file_name=doc["filename"])

    segments = {s["segment_id"]: s for s in b["segments"]}
    render_candidates(b, segments)
    render_flags(ctx, session, b)
    render_actions(ctx, session, b)

    with st.expander("Extracted text (source passages)"):
        if not b["segments"]:
            st.write("No text was extracted. Download the original to review it manually.")
        for s in b["segments"]:
            st.caption(f"Segment {s['segment_id']} - {location_label(s['page_number'], s['segment_index'])}")
            st.text(s["text"])

    with st.expander("Decision and audit history"):
        if b["decisions"]:
            st.markdown("**Review decisions**")
            st.dataframe([{"Time (UTC)": d["timestamp"], "Reviewer": names.get(d["reviewer_id"], d["reviewer_id"]),
                           "Target": d["target_type"], "Action": d["action"],
                           "Corrected matter": d["corrected_matter_id"] or "", "Note": d["note"],
                           "From": d["previous_status"], "To": d["resulting_status"]} for d in b["decisions"]],
                         hide_index=True, width="stretch")
        st.markdown("**Audit events**")
        st.dataframe([{"Time (UTC)": e["timestamp"], "Actor": names.get(e["actor_id"], e["actor_id"]),
                       "Action": e["action"], "Outcome": e["outcome"], "Details": e["safe_details"]}
                      for e in b["audit_events"]], hide_index=True, width="stretch")


def render_candidates(b, segments):
    st.markdown("#### Matter candidates")
    if not b["candidates"]:
        st.write("No candidate matter. Use **Correct** to assign a matter manually, or escalate.")
    for c in b["candidates"]:
        with st.container(border=True):
            st.markdown(f"**#{c['rank']} {c['matter_label']}** - score {c['score']:.2f} "
                        f"(**{c['uncertainty_label']}** confidence) - {badge(c['review_status'])}  \n"
                        f"Source: {'rule-based matcher' if c['matcher_name'] == 'rules' else c['matcher_name']} "
                        f"v{c['matcher_version']}")
            for r in c["reasons"]:
                st.markdown(f"- {r['label']}")
                st.caption(f"“{r['excerpt']}”")
                if r.get("segment_id") in segments:
                    with st.popover(f"Show {r['location']}"):
                        st.text(segments[r["segment_id"]]["text"])


def render_flags(ctx, session, b):
    st.markdown("#### Duplicate / conflict warnings")
    if not b["flags"]:
        st.write("No duplicate or conflict warnings.")
        return
    st.caption("Warnings never delete, merge, or replace a document. Both documents stay on file.")
    for f in b["flags"]:
        with st.container(border=True):
            st.markdown(f"**{f['flag_label']}** ({f['direction']}) - {badge(f['review_status'])}  \n"
                        f"Related document: **{f['other_document_id']}** {f['other_filename']} "
                        f"({f['other_status']}{', ' + f['other_matter'] if f['other_matter'] else ''})")
            for line in f["evidence"]:
                st.markdown(f"- {line}")
            if f["allowed_actions"]:
                note = st.text_input("Note (required to dismiss or escalate)", key=f"note_{f['flag_id']}")
                cols = st.columns(len(f["allowed_actions"]))
                for col, action in zip(cols, f["allowed_actions"]):
                    if col.button(FLAG_ACTION_LABELS[action], key=f"{action}_{f['flag_id']}"):
                        try:
                            review.submit_flag_decision(ctx, session, f["flag_id"], action, note)
                            st.rerun()
                        except (ValidationError, AuthorizationError) as exc:
                            st.error(str(exc))


def render_actions(ctx, session, b):
    doc = b["document"]
    st.markdown("#### Review decision")
    if b["can_retry"]:
        if st.button("Retry analysis", help="Re-run extraction and matching. The document keeps its ID."):
            try:
                pipeline.retry_processing(ctx, session, doc["document_id"])
                st.rerun()
            except (ValidationError, AuthorizationError) as exc:
                st.error(str(exc))
    actions = b["allowed_actions"]
    if not actions:
        if doc["status"] == "Escalated":
            st.write("This item is escalated. Only a supervising attorney can resolve it.")
        elif doc["status"] in ("Confirmed", "Corrected") or doc["status"] in ("Received", "Processing"):
            st.write("No review actions are available to you for this document.")
        else:
            st.write("Your role cannot make review decisions.")
        return
    with st.form(f"decide_{doc['document_id']}"):
        action = st.radio("Action", actions, format_func=MATTER_ACTION_LABELS.get)
        active = b["active_candidates"]
        cand_id = st.selectbox("Candidate to confirm (used for Confirm)", [c["candidate_id"] for c in active],
                               format_func=lambda cid: next(f"{c['matter_label']} (score {c['score']:.2f})"
                                                            for c in active if c["candidate_id"] == cid),
                               index=0 if active else None)
        matters = review.permitted_matters(ctx, session)
        corrected = st.selectbox("Correct matter (used for Correct)", [m["matter_id"] for m in matters],
                                 format_func=lambda mid: next(f"{m['matter_id']} - {m['display_label']}"
                                                              for m in matters if m["matter_id"] == mid),
                                 index=None)
        note = st.text_area("Note (required for Reject and Escalate)")
        if st.form_submit_button("Submit decision"):
            try:
                result = review.submit_matter_decision(ctx, session, doc["document_id"], action,
                                                       candidate_id=cand_id, corrected_matter_id=corrected,
                                                       note=note)
                st.session_state.flash = f"Decision recorded. New status: {result}."
                st.rerun()
            except (ValidationError, AuthorizationError) as exc:
                st.error(str(exc))


# ---------------------------------------------------------------- audit
def audit_view(ctx, session):
    st.header("Audit log")
    try:
        events = review.full_audit_log(ctx, session)
    except AuthorizationError as exc:
        st.error(f"Access denied: {exc}. This attempt was recorded.")
        return
    names = user_names(ctx)
    st.caption("Append-only. Shows the latest 500 events, newest first.")
    st.dataframe([{"#": e["event_id"], "Time (UTC)": e["timestamp"], "Actor": names.get(e["actor_id"], e["actor_id"]),
                   "Action": e["action"], "Object": f"{e['object_type']} {e['object_id'] or ''}",
                   "Outcome": e["outcome"], "Details": e["safe_details"]} for e in events],
                 hide_index=True, width="stretch")


# ---------------------------------------------------------------- main
def main():
    ctx = get_ctx()
    session = st.session_state.get("auth")
    if session is None:
        login_view(ctx)
        return
    with st.sidebar:
        st.markdown(f"**{session.display_name}**  \nRole: {session.role}")
        st.caption("Matters: " + ", ".join(m["matter_id"] for m in review.permitted_matters(ctx, session)))
        pages = ["Upload", "Review queue"] + (["Audit log"] if session.role == "attorney" else [])
        page = st.radio("Page", pages)
        if st.button("Log out"):
            st.session_state.clear()
            st.rerun()
    if msg := st.session_state.pop("flash", None):
        st.success(msg)
    {"Upload": intake_view, "Review queue": review_view, "Audit log": audit_view}[page](ctx, session)


main()
