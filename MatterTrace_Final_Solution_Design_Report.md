---
title: "MatterTrace — Final Solution Design Report"
author: "Mathew Quintero"
course: "CEN 4010 — Principles of Software Engineering"
date: "November 2026"
---

<div class="cover" markdown="1">

<p class="cover-course">CEN 4010 — Principles of Software Engineering</p>
<p class="cover-kind">Final Project</p>

# Final Solution Design Report

<p class="cover-title">MatterTrace</p>
<p class="cover-subtitle">Source-Traceable Document Intake &amp; Matter Association Assistant</p>

<p class="cover-meta">Author: Mathew Quintero<br>
Course: CEN 4010 — Principles of Software Engineering<br>
November 2026<br>
Repository: <a href="https://github.com/mathewquinte2025/Matter-Trace">github.com/mathewquinte2025/Matter-Trace</a></p>

<p class="cover-note">Local classroom prototype built with synthetic data only.<br>Not production-ready legal software.</p>

</div>

<div class="toc" markdown="1">

## Contents

1. Executive Summary
2. Problem Definition and Stakeholder Need
3. Project Scope, Goals, and Exclusions
4. Functional and Nonfunctional Requirements
5. System Models and Workflow
6. Solution Architecture and Technology Choices
7. Implementation Details and Actual Features
8. Testing and Validation
9. Security, Privacy, Source Traceability, and Human Oversight
10. Known Limitations and Future Improvements
11. Generative AI Usage Disclosure
12. Conclusion
13. References

Appendix A. Automated Test Inventory

</div>

## 1. Executive Summary

Personal-injury law offices receive documents through many channels, including client uploads, email, mail, provider portals, insurers and courts. For each one, staff must decide:

- which matter it belongs to
- where it came from
- whether it duplicates, replaces or conflicts with a record already on file

The course-provided Injure Law Office scenario identifies two related problems: documents that are hard to associate with the correct matter, and duplicate or superseded versions of documents.

**MatterTrace** is a bounded decision-support tool for litigation paralegals and supervising attorneys. This report describes the final prototype that was built from the requirements in Assignment 1 and the architecture in Assignment 2. The prototype does the following:

1. registers each uploaded PDF or TXT file and stores the original unchanged
2. extracts its text by page or paragraph
3. suggests up to three candidate matters, each with the exact source passages that support it
4. warns about exact duplicates, possible conflicts and possible other versions
5. sends every result to an authorized human for review
6. records every decision in an append-only audit history

**What the prototype is and is not.** Matter suggestions come from a deterministic, rule-based matcher. The AI part of the architecture is a replaceable interface with a stub implementation that returns no suggestions. No real AI provider is connected, so MatterTrace should not be described as an AI-powered system. The system never confirms a matter association by itself, and it never deletes, merges or replaces a document. All final decisions remain with authorized humans.

**Results.** The prototype is a working local Streamlit application written in Python with a SQLite database.

- All 10 functional requirements (FR-01 to FR-10) are implemented and covered by automated tests.
- Of the 11 nonfunctional requirements:
  - 8 are implemented and tested.
  - NFR-01 (privacy) is met by design: the data is synthetic and access is restricted by matter.
  - NFR-05 (readability) and NFR-10 (failure handling) are only partly met.
- The final automated suite has 52 tests, and all 52 pass.
- In the documented test environment, a 20-page synthetic PDF was ready for review in about 0.1 seconds. This is well within the 2-minute target, but it reflects rule-based matching only.

The prototype uses only synthetic sample documents and runs locally. It is a classroom prototype, not production-ready legal software. Its main limitations are:

- no real AI provider
- no OCR
- no encryption at rest
- no usability walkthrough
- no validation by a real stakeholder

## 2. Problem Definition and Stakeholder Need

### 2.1 Operating context

The operating context is a personal-injury law office. Once a matter is accepted, paralegals and attorneys coordinate client communication, incident evidence, medical records and bills, insurance correspondence and court documents.

When a new document arrives, a staff member currently has to:

- identify the document and its source
- decide which matter it belongs to
- record its metadata
- compare it with records already on file to see whether it is a duplicate, a newer version or a conflicting record

Inconsistent naming, incomplete metadata, similar client names and poor scans all make this harder.

### 2.2 Problem trigger and impact

**Trigger.** A new document arrives that must be associated with an existing matter and checked against relevant records.

**Impact.** The course scenario describes three consequences:

- information can be filed under the wrong matter
- duplicate or superseded versions can be used by mistake
- missing source details can make later review difficult

How often these problems occur, how much time they cost and how serious they are in a real office has **not** been independently established.

### 2.3 Stakeholders

| Stakeholder | Goal | Role in the prototype |
|---|---|---|
| Litigation paralegal (primary user) | Route incoming documents to the right matter, catch duplicates, and keep the source of each document | Demo users `pat` and `riley`: upload and review documents for their own matters |
| Supervising attorney | Keep authority over consequential decisions and handle escalations | Demo user `avery`: reviews all matters, resolves escalations, reads the full audit log |
| Office records custodian / manager | Make sure documents are stored correctly and seen only by authorized staff | Not a separate role. Matter access is seeded in the database. |
| Intake staff | Register incoming documents | Demo user `casey`: can upload but cannot review. This role was added during implementation to test role-based limits. |
| Client (indirect) | Benefits from accurate handling | No direct access |
| MatterTrace system | Produces suggestions and warnings | Has no authority to confirm, delete, merge or make legal decisions |

### 2.4 Proof of demand

The target users and their workflow come from the course-provided Injure Law Office scenario. **No interview, email, letter or other evidence from a practicing paralegal or attorney has been collected.** Both earlier reports stated this, and it is still true for the final project.

A real discovery conversation would still be needed to answer several questions:

- how staff actually identify the correct matter
- how often errors and duplicates occur
- what evidence would make staff trust a suggestion
- what response time and confidence threshold would be acceptable

## 3. Project Scope, Goals, and Exclusions

### 3.1 Goals

1. Reduce repetitive manual matter sorting and duplicate checking.
2. Make every suggestion traceable to a specific page, paragraph or metadata field.
3. Keep human authority: nothing becomes a confirmed matter record without an explicit, authorized human action.
4. Keep a complete, append-only history of suggestions, decisions and access attempts.
5. Handle failures (unreadable files, low confidence, service errors) visibly and never report them as success.

### 3.2 In scope

The bounded workflow from Assignments 1 and 2 is:

**incoming document → registration → text extraction → candidate matter suggestion → duplicate/conflict check → human review → recorded decision and audit history**

### 3.3 Exclusions

These items were out of scope in the original reports and remain out of scope:

- legal analysis and legal strategy
- chronology generation
- case valuation and negotiation
- task management
- full document management
- integration with a real case-management system

The prototype also deliberately excludes:

- any real AI provider or cloud service
- file types other than PDF and TXT
- OCR
- production deployment
- real client data

## 4. Functional and Nonfunctional Requirements

The requirements baseline is the Assignment 2 version. Assignment 2 carried forward Assignment 1's FR-01 to FR-09 and NFR-01 to NFR-09, and added FR-10, NFR-10 and NFR-11.

The status column uses three values:

- **Implemented and tested:** the behavior exists in the code, and at least one automated test checks it.
- **Partial:** only part of the requirement is met; the evidence column says what is missing.
- **Met by design:** the requirement is satisfied by how the project is built, and no automated test checks it.

### 4.1 Functional requirements

| ID | Requirement (summary) | Status | Evidence |
|---|---|---|---|
| FR-01 | Register each document with a unique ID, source, timestamp, file type and initial status | Implemented and tested | `test_valid_upload_registers_metadata_and_preserves_original`; invalid uploads rejected with a clear message (4 cases) |
| FR-02 | Propose a candidate matter from the extracted content and permitted matter metadata | Implemented and tested | `test_clear_match_produces_traceable_candidate`, similar-name and ambiguous tests. Uses the rule-based matcher; the AI service is a stub. |
| FR-03 | Give source references for each candidate | Implemented and tested | `test_every_candidate_has_a_source_reference`, `test_metadata_evidence_is_used_and_referenced` |
| FR-04 | Flag likely duplicates, other versions and conflicts | Implemented and tested | Exact-duplicate, conflict, near-duplicate and unrelated-document tests |
| FR-05 | Let an authorized reviewer confirm, correct or reject | Implemented and tested | Review tests; scripted UI check of the confirm action. Escalate was also implemented. |
| FR-06 | Record the candidate, action, reviewer, timestamp and resulting status | Implemented and tested | `test_confirm_records_reviewer_from_session`, `test_correct_keeps_original_candidate_in_history` |
| FR-07 | Prevent an unreviewed candidate from being treated as confirmed | Implemented and tested | Statuses stay unconfirmed until a reviewer acts; a clerk calling the service directly is refused |
| FR-08 | Preserve originals and possible duplicates; never auto-delete or merge | Implemented and tested | `test_exact_duplicate_is_flagged_and_both_files_preserved`, `test_flag_review_never_deletes_documents`, database triggers |
| FR-09 | Restrict access to users authorized for the matter | Implemented and tested | `test_cross_matter_access_is_denied_and_logged`; scripted UI check |
| FR-10 | Handle missing metadata, unreadable files, errors and low confidence without silent confirmation | Implemented and tested | Unreadable PDF, binary TXT, faulty AI output, unexpected error and low-confidence tests |

### 4.2 Nonfunctional requirements

| ID | Category | Status | Evidence and notes |
|---|---|---|---|
| NFR-01 | Privacy | Met by design | All data is synthetic. Matter-scoped access is tested under NFR-02. |
| NFR-02 | Security | Implemented and tested | Login is required. Role and matter checks run in the service layer. Denied attempts are logged with user and time. |
| NFR-03 | Source traceability | Implemented and tested | Every candidate and warning carries evidence that points to a segment, a metadata field or a linked document |
| NFR-04 | Review status | Implemented and tested | All six required statuses exist, plus Received, Processing and Escalated. Status rules are tested; the coloured badges were checked visually only. |
| NFR-05 | Readability | Partial | One review screen shows the candidate, evidence, warnings, status and actions, with no raw model output. **No usability walkthrough was done.** |
| NFR-06 | Response time | Implemented and tested | 20-page synthetic PDF ready in about 0.10–0.13 s in the development runs (see 8.3). Rules and stub only. |
| NFR-07 | AI operating conditions | Implemented and tested | Candidates are labelled. Low, ambiguous and unsupported results go to Needs Review. The threshold is configurable (0.60). |
| NFR-08 | Retained human authority | Implemented and tested | No code path confirms, deletes or merges automatically. The database blocks document deletion. |
| NFR-09 | Auditability | Implemented and tested | `test_history_survives_multiple_decisions`, `test_audit_and_decision_history_are_append_only` |
| NFR-10 | Reliability / failure handling | Partial | Failures in extraction, the AI service, validation and unexpected errors are tested. **A seeded storage failure is not tested.** |
| NFR-11 | Data integrity | Implemented and tested | Stable `DOC-` IDs. The database blocks changes to identity fields. Decisions reference the document ID. |

### 4.3 Representative scenarios

| Scenario | Sample file | Observed result |
|---|---|---|
| Clear match | `01_clear_match_reyes_records_request.txt` | Candidate Ready, matter MT-1001, score 1.00 |
| A: Likely duplicate | `02_duplicate_reyes_er_bill.pdf` | Needs Review with an "Exact duplicate" warning; both files kept |
| B: Possible wrong matter | any candidate | The reviewer uses **Correct**; the original candidate stays in the history |
| C: Low confidence | `05_low_confidence_fax_cover.txt` | Needs Review: best score 0.10 is below the 0.60 threshold |
| D: Conflicting documents | `03_conflicting_reyes_er_bill.txt` | Needs Review with "Possible conflict": same invoice number, different total |
| E: Unreadable file | `06_scanned_image_only.pdf`, `07_corrupted_file.pdf` | Processing Failed, with a reason and a retry or manual-assignment path |
| Similar client names | `04_ambiguous_two_clients.txt` | Needs Review: MT-1002 and MT-1004 tie at 0.60 |
| Other version | `08_okafor_insurer_letter_revised.txt` | Needs Review with "Possible duplicate / other version" |
| Matter scoping | `09_lindqvist_pt_note_followup.txt` | No candidate for Pat, who cannot access MT-1003; Candidate Ready for Riley |

These results come from running the sample files through the application's services on a fresh test database (section 8.2).

## 5. System Models and Workflow

### 5.1 End-to-end workflow

```
 Upload (PDF/TXT + source type)
        │  validate type, size and source; refuse if not logged in
        ▼
 Register document ──► store original once (SHA-256)  ──► status: Received
        │
        ▼
 Extract text (per PDF page / per TXT paragraph) ──► failure? ──► Processing Failed
        │                                                        (reason + retry / manual)
        ▼
 Rule-based matcher over PERMITTED matters only  ┐
 AI interface (stub) — output validated          ├─► candidates + evidence
        │                                        ┘
        ▼
 Duplicate / conflict check vs. documents the user may see ──► warnings (never actions)
        │
        ▼
 Status decision ──► Candidate Ready  (clear, unambiguous, no warnings)
                 └─► Needs Review     (low score, tie, warning, AI problem)
        │
        ▼
 Human review: Confirm │ Correct │ Reject (note) │ Escalate (note)
        │
        ▼
 Review decision + audit event (append-only) ──► Confirmed / Corrected / Rejected / Escalated
```

### 5.2 Document status model (as implemented)

| Status | Meaning | Allowed next steps |
|---|---|---|
| Received | File and source metadata registered | Processing |
| Processing | Extraction and matching in progress | Candidate Ready, Needs Review, Processing Failed |
| Candidate Ready | A clear suggestion exists; **not confirmed** | Confirm, Correct, Reject, Escalate |
| Needs Review | Low score, tie, warning or AI problem | Confirm, Correct, Reject, Escalate, Retry |
| Confirmed | A reviewer accepted the suggested matter | Correct (creates new history; old entries kept) |
| Corrected | A reviewer assigned a different matter | Correct again |
| Rejected | A reviewer rejected the suggestions (note required) | Correct (manual assignment), Escalate, Retry |
| Escalated | Sent to a supervising attorney (note required) | Attorney only: Confirm, Correct, Reject |
| Processing Failed | The file could not be processed | Retry, Correct (manual assignment), Escalate. **Cannot be confirmed.** |

Compared with the Assignment 2 status model:

- **Escalated** was added as a real status. Assignment 2 listed escalation only as a next step.
- "Needs Manual Review" is covered by Needs Review or Processing Failed.
- Each candidate and warning also has its own status. **Superseded** marks older candidates and warnings replaced by a retry; they are kept, not deleted.

### 5.3 Data model (implemented tables)

| Table | Purpose | Key fields and rules |
|---|---|---|
| `users` | Demo accounts | username, role, PBKDF2 password hash and salt |
| `matters` | Synthetic matters | matter_id, client name, DOB, claim number, incident date |
| `matter_access` | Which user may see which matter | user, matter_id |
| `documents` | One row per upload | `DOC-` ID, filename, file type, source type and description, received time, submitter, SHA-256, status, reason, assigned matter, processing time. **Cannot be deleted; identity fields cannot change.** |
| `extracted_segments` | Text by page or paragraph | segment_id, document_id, page or paragraph number, text |
| `matter_candidates` | Suggestions | matter, rank, score, uncertainty label, reasons with evidence, matcher name and version, review status |
| `duplicate_candidates` | Duplicate and conflict warnings | both document IDs, flag type, similarity, evidence, review status |
| `review_decisions` | Human decisions | reviewer (from session), action, candidate or warning, corrected matter, note, resulting status, time. **Append-only.** |
| `audit_events` | Everything else | actor, action, object, outcome, safe details, time. **Append-only.** |

The database enforces the append-only and no-delete rules with SQLite triggers, so the rules hold even if application code tried to break them.

### 5.4 Review interaction (sequence)

1. The reviewer logs in. The session stores who they are and their role.
2. The reviewer opens a document from the Review queue. The service re-checks access, logs the view, and returns a review bundle. The bundle contains:
   - the status and reason
   - the candidates and their evidence
   - the warnings
   - the extracted text
   - the history
   - the actions this user is allowed to take
3. The reviewer chooses an action. Reject and Escalate require a note.
4. The service checks the user's permission and the allowed status transition again before saving. It then writes the decision and an audit event in one transaction.

## 6. Solution Architecture and Technology Choices

### 6.1 Architecture

Assignment 2 defined 11 logical components and allowed them to run as modules in one application. The prototype follows that approach: a Streamlit user interface sits on top of plain Python service modules, which use a SQLite database and a local folder of original files.

```
app.py  (Streamlit UI: login, Upload, Review queue, Audit log)
   │  every call passes the authenticated session
   ▼
mattertrace/  intake · extraction · matching · ai_service · duplicates
              pipeline (orchestration, status decision, retry)
              review (decisions, transition rules) · auth · audit
   ▼
data/mattertrace.db (SQLite)          data/originals/ (stored original files)
```

| Assignment 2 component | Implementation | Notes |
|---|---|---|
| 1. Intake UI / API | `app.py` Upload page, `intake.py` | Checks type, size, emptiness and source type; strips folder paths from filenames |
| 2. Access Control | `auth.py` | PBKDF2 login, three roles, matter-scoped visibility |
| 3. Document Store | `intake.py` | Original written once (exclusive create) and named by document ID |
| 4. Metadata / Matter Repository | `db.py` | SQLite schema and triggers |
| 5. Text Extraction | `extraction.py` | `pypdf` per page; TXT per paragraph |
| 6. Candidate Retrieval | `matching.py`, `pipeline.py` | Only matters the user may access are passed in |
| 7. AI Matching Service | `matching.py` (rules), `ai_service.py` (stub) | Rule-based matcher; replaceable AI interface with a stub and output validation |
| 8. Duplicate / Conflict Checker | `duplicates.py` | Checksum, reference/amount/date, text similarity |
| 9. Review Workbench | `app.py` | Evidence, warnings, actions, original download, extracted text, history |
| 10. Decision / Audit Service | `review.py`, `audit.py` | Re-checks permission and transition rules before saving |
| 11. Exception Queue | Review queue filter | **Not a separate component** (see section 10) |

### 6.2 Technology choices

| Technology | Version tested | Why it was chosen |
|---|---|---|
| Python | 3.13.7 | Simple, readable, good standard library (`sqlite3`, `hashlib`) |
| Streamlit | 1.67.0 | A working web interface from plain Python, with no separate front-end |
| SQLite | Python built-in | No server to install; triggers enforce the append-only rules |
| pypdf | 7.1.1 | Pure-Python PDF text extraction by page |
| pytest | 9.2.0 | Simple, widely used test framework |

The test environment was Windows 11 Home with Python 3.13.7. No cloud services, external APIs, API keys or extra frameworks are used, following the project rule against unnecessary complexity.

### 6.3 Key design decisions

**Matching score.** Each matter is checked for five signals, and each signal has a fixed weight:

| Signal | Weight |
|---|---|
| Matter number | 0.50 |
| Claim number | 0.50 |
| Client name | 0.35 |
| Client date of birth | 0.25 |
| Incident date | 0.10 |

- The score is the sum of the weights of the signals found, capped at 1.0. Up to three candidates are kept.
- Uncertainty labels: High at 0.85 or above; Medium from the threshold up to 0.85; Low below the threshold.

**Status rule.** A result is **Candidate Ready** only if the best rule-based score is at or above the threshold (default 0.60) and none of the following applies:

- another matter scores within 0.15 of the best
- there is a duplicate or conflict warning
- there is an AI-service problem
- the AI and the rules disagree on the best matter

Otherwise the result is **Needs Review**, with the reasons listed. Neither status is a confirmation.

**Duplicate scope.** Assignment 1 left open whether duplicates should be checked only within one matter. The prototype compares a new document with every document the uploading user is allowed to see, across matters. Documents the user cannot see are never compared or revealed.

**AI output contract.** The interface expects this JSON structure:

```
{"candidates": [{"matter_id", "confidence", "evidence_segment_ids"}]}
```

Suggestions are kept only if all of the following hold:

- the structure is valid
- the matter ID is one the user is allowed to see
- the suggestion cites at least one real text segment of the document

Model free text is never stored or shown.

**Retry.** Retry is allowed from Processing Failed, Needs Review and Rejected. It keeps the same document ID and reuses the extracted text. Earlier unreviewed candidates and warnings are marked Superseded instead of being deleted.

## 7. Implementation Details and Actual Features

### 7.1 Planned versus implemented

| Planned feature (Assignments 1–2) | Final prototype |
|---|---|
| Upload with source metadata | **Implemented.** PDF and TXT, up to 10 MB, seven source types, optional description |
| Preserve originals with a stable ID | **Implemented.** `DOC-` + 12 hex characters, SHA-256 checksum, written once |
| Text extraction with page references | **Implemented.** PDF per page; TXT per paragraph |
| AI-assisted matter matching | **Partly implemented.** A deterministic rule-based matcher does the matching. The AI interface, its validation and its error handling exist, but the only AI implementation is a **stub that returns no suggestions**. No real provider is connected. |
| Model name and version recorded | **Implemented.** Stored with each candidate, e.g. `rules` 1.0 or `ai:stub` |
| Duplicate / conflict detection | **Implemented.** Exact, conflict and near-duplicate warnings with evidence |
| Review: confirm, correct, reject, escalate | **Implemented.** Warnings can also be confirmed, dismissed or escalated |
| Escalated item returns to the paralegal | **Not implemented.** The attorney resolves escalations directly. |
| Separate Exception Queue | **Not implemented as a component.** Shown through the Review queue filter |
| Source preview | **Partly implemented.** Two-step download of the original and the full extracted text; no inline PDF viewer |
| Encryption at rest | **Not implemented** |
| OCR for scanned documents | **Not implemented.** Scanned PDFs fail clearly and go to manual assignment. |
| Records custodian role | **Not implemented.** Matter access is seeded in the database. |
| Append-only audit history | **Implemented,** and enforced in both the application and the database |

### 7.2 User interface

The Streamlit app has four pages.

1. **Login.** Takes a username and password. A demo-accounts panel lists the synthetic users.
2. **Upload.** Takes the file, source type and description, then shows the resulting status. Files are not filtered by type in the browser, so the server-side rejection message is visible.
3. **Review queue.** A table of the documents the user may see, with an "include completed documents" option and an "open by document ID" box. Opening a document shows:
   - a status badge, and a banner stating that results are candidates only
   - the document metadata
   - a two-step download of the original
   - candidate matters with their score, uncertainty label and every evidence passage (page or paragraph, matched text, excerpt)
   - duplicate and conflict warnings, with a link to the related document and their own actions
   - the decision form, offering only the actions this user is allowed to take
   - a retry button where retry is allowed
   - the extracted text
   - the decision and audit history for the document
4. **Audit log.** Attorney only. The service refuses this page for other users.

### 7.3 Synthetic data and demo accounts

The seed script creates four synthetic matters:

| Matter | Client |
|---|---|
| MT-1001 | Daniel Reyes |
| MT-1002 | Grace Okafor |
| MT-1003 | Erik Lindqvist |
| MT-1004 | Daniela Reyes (deliberately similar to MT-1001) |

It also creates four existing records for the duplicate checks to compare against, and the nine sample files listed in section 4.3. All names, dates, claim numbers and amounts are invented.

| User | Role | Matters | Permissions |
|---|---|---|---|
| `pat` | Paralegal | MT-1001, MT-1002, MT-1004 | Upload, review |
| `riley` | Paralegal | MT-1003 | Upload, review |
| `avery` | Supervising attorney | All | Upload, review, resolve escalations, full audit log |
| `casey` | Intake clerk | All | Upload only |

All demo accounts share the password `demo123`. These credentials exist only for synthetic demonstration data.

## 8. Testing and Validation

### 8.1 Automated tests

The automated suite has **52 pytest tests in five files**. Each test uses its own temporary database and folder. The final run in the documented environment ended with **`52 passed in 32.20s`**.

| File | Tests | What it checks |
|---|---|---|
| `test_intake.py` | 9 | Valid upload and metadata; four invalid uploads (wrong type, empty file, missing source, unknown source) rejected and logged; filename path stripping; identity fields cannot be changed or deleted; bad login logged; unauthenticated upload refused |
| `test_matching.py` | 10 | Clear match with evidence; every candidate has a source reference; metadata evidence; similar names; ambiguous and low-confidence documents; threshold boundary; configurable threshold; matter scoping; document text containing instructions does not change behavior |
| `test_duplicates.py` | 6 | Exact duplicate with both files kept; conflict with reason; revised letter flagged; unrelated document not flagged; no comparison with unauthorized documents; flag review deletes nothing |
| `test_review.py` | 13 | Reviewer identity taken from the session; correction keeps history; multiple decisions; notes required; escalation reserved for attorneys; intake clerk refused even when calling the service directly; cross-matter denial logged; correction to an unpermitted matter refused; invalid requests; failed document can only be assigned manually; warning review rules; append-only history; audit log for attorneys only |
| `test_failures.py` | 14 | Scanned and corrupted PDFs; binary TXT; failed document routed to attorney; AI timeout, malformed output, invented ID, unauthorized matter and untraceable evidence (all sent to review, nothing stored); valid AI suggestion stored with traceable evidence; retry keeps the same document and its history; no retry after confirmation; unexpected error rolled back without leaking internals; 20-page PDF timing |

The AI-related tests use **fake AI services written for the tests**. They show that the validation and error handling work. They do not show how accurate any real AI model would be.

Appendix A lists every test by name.

### 8.2 Manual and scripted checks

The author ran three manual tests in the browser as user `pat`, between 21 and 23 November 2026. The app's own database and audit log confirm each result below.

| Check | Who / how | Result (confirmed in the audit log) |
|---|---|---|
| File 01: clear-match intake (`01_clear_match_reyes_records_request.txt`) | Author, in the browser | The document produced candidate MT-1001 (score 1.00, High) with status Candidate Ready. The author then **confirmed** it manually, and the status became Confirmed. |
| File 02: duplicate Reyes ER bill (`02_duplicate_reyes_er_bill.pdf`) | Author, in the browser | The system raised an **Exact duplicate** warning against the seeded bill (same SHA-256 checksum), and the status became Needs Review. Both files are still stored. |
| File 03: conflicting Reyes ER bill (`03_conflicting_reyes_er_bill.txt`) | Author, in the browser | The system raised a **Possible conflict** warning: same invoice number (INV-44817), but $2,890.00 against $2,340.00 in the existing bill. The status became Needs Review, and all files are still stored. |
| All nine sample files through the application services | Development script on a fresh temporary database | Results matched the expected outcomes in section 4.3 |
| Scripted UI checks with Streamlit's `AppTest` | Development script | A confirm action stored Confirmed and MT-1001; Pat opening Riley's document showed "Access denied"; the attorney audit log displayed |
| Server start | `streamlit run app.py` and its health check | The server started and the health check returned "ok" |

For files 02 and 03, the author used **Escalate** on the matter association, with a note asking a supervising attorney to review. No attorney has resolved either escalation, and no one has confirmed or dismissed the duplicate and conflict warnings themselves. Their final disposition is therefore **not** part of the manual test results.

In both the manual test and the nine-sample run, file 03 also raised a second "possible conflict" warning, against file 02, because file 02 had been uploaded earlier. This is expected, because duplicate checks include the user's own earlier uploads.

**Not tested.** Streamlit's test harness cannot drive the browser file-upload widget, so that widget is not covered by automated tests. Upload logic is tested at the service level and was exercised manually in the browser.

### 8.3 Performance (NFR-06)

The test `test_twenty_page_pdf_is_ready_for_review_within_two_minutes` builds a 20-page synthetic PDF, runs the full pipeline and checks that the document reaches Candidate Ready.

| Run | Elapsed (test) | Pipeline time recorded |
|---|---|---|
| Earlier development run | 0.13 s | 117 ms |
| Final run | 0.10 s | 91 ms |

Both runs are far below the 2-minute target. The pipeline used only the rule-based matcher and the stub. A real AI provider or OCR would add time, and that has not been measured.

### 8.4 What the tests do not prove

The tests use synthetic documents written to exercise specific rules. They show that the prototype behaves as designed. They do **not** show:

- how accurate the matcher would be on real legal documents
- how often it would produce false matches or miss duplicates in practice
- whether real paralegals would find the review screen clear

## 9. Security, Privacy, Source Traceability, and Human Oversight

### 9.1 Security

- **Authentication.** Every service function requires an authenticated session issued by `login()`. Passwords are stored as PBKDF2 hashes with a salt.
- **Authorization in the service layer.** Role permissions and matter access are checked inside the services, not just by hiding buttons. The tests call the services directly as an unauthorized user to prove this.
- **No existence leaks.** A missing document and a forbidden document return the same "not found or not authorized" message.
- **Logged denials.** Denied access attempts and failed logins are recorded with user and time.
- **Safe uploads.** Uploads are checked for type, size and content. Filenames are stripped of folder paths, and originals are stored under generated IDs.
- **Safe error messages.** Error messages shown to users give only the error type, never internal details or stack traces.

### 9.2 Privacy

- Only synthetic data is used.
- Users see only documents and candidates for matters they are allowed to access.
- Duplicate checks never compare against, or reveal, documents the user cannot see.
- The AI interface receives only the text segments and the permitted matter context it needs.
- `data/`, which holds the database and stored uploads, is excluded from Git by `.gitignore`.

### 9.3 Source traceability

Every candidate shows each signal it found, together with:

- where it was found: the page, the paragraph, or a metadata field such as the filename or source description
- the matched text
- a short excerpt

Every duplicate or conflict warning links to the other document and explains why it was raised, for example the shared reference number, the different amounts, or the percentage of text overlap. AI suggestions are kept only if they cite real segments of the document.

### 9.4 Human oversight

- No code path confirms a matter association, or deletes, merges or replaces a document.
- Candidate Ready means "ready for human review". The interface says plainly that results are candidates only.
- Duplicate and conflict results are warnings only, and both documents always remain available.
- Only paralegals and attorneys can confirm, correct, reject or escalate. Only attorneys can resolve escalated items.
- Every decision records the reviewer's identity from the session, never from the request.
- **All final matter-association decisions remain with authorized humans.**

## 10. Known Limitations and Future Improvements

| Limitation | Effect | Possible improvement |
|---|---|---|
| Rule-based matcher only | Matches only exact identifiers, names and dates (case and separators ignored). Misspellings, nicknames and documents without identifiers are not matched. The weights are not tuned on real data. | Tune the weights with real stakeholder data. Add fuzzy name matching. |
| No real AI provider | The AI interface is a stub; no AI suggestions are produced. | Connect a provider behind the existing interface and validation, with approved data only, and measure its accuracy and response time. |
| No OCR | Scanned PDFs fail and must be assigned manually. | Add an OCR step, with clear quality warnings. |
| PDF and TXT only | Other formats (DOCX, images, email files) are rejected. | Add formats one at a time, with tests. |
| No encryption at rest | The database and originals in `data/` are readable on disk. | Encrypt the database and stored files. |
| No session timeout or lockout; shared demo password | Not suitable for real users. | Add individual accounts, timeouts, lockout and HTTPS. |
| No separate Exception Queue | Failures and reviews appear in the Review queue filter. | Add a dedicated queue with assignment and ageing. |
| No return-to-paralegal escalation step | Attorneys resolve escalations directly. | Add an "Escalation answered" step back to the paralegal. |
| Browser upload widget not covered by automated UI tests | Only manual coverage for that one widget. | Add a browser-based end-to-end test. |
| Storage failure not tested (NFR-10) | Disk-write failures are not demonstrated. | Add a test that simulates a write failure. |
| No usability walkthrough (NFR-05) | Readability is not validated with users. | Run a walkthrough with classmates or real paralegals. |
| No stakeholder validation | The problem and matching rules are unverified. | Interview practicing paralegals and attorneys. |
| Local, single-machine prototype | Not deployed, and not built as a shared multi-user server. | Use a server database and proper hosting before any real use. |

## 11. Generative AI Usage Disclosure

Two generative AI tools were used in this project, for different purposes.

- **ChatGPT (OpenAI).** Used by the author to:
  - plan the project
  - understand the requirements
  - prepare the prompts given to Claude
  - review results

  ChatGPT also helped draft and organize the Assignment 1 and Assignment 2 reports, as disclosed in those reports.
- **Claude (Anthropic), through Claude Code.** Used to generate and modify:
  - the application code
  - the automated tests and the synthetic sample documents
  - the documentation (README, `CONTRIBUTING.md`)
  - this report

  Claude also ran the automated tests and fixed the errors they revealed.
- **Author's role.** The author ran the application personally, reviewed its behavior, and performed the manual tests described in section 8.2.
- **Inputs.** The project requirements, design decisions and constraints came from the Assignment 1 and 2 reports and from the author's instructions.
- **Data.** Only synthetic data was used in prompts, code and test fixtures. No confidential client, patient or firm information was given to any AI tool.
- **Controls.** The prototype's safety controls are written as explicit application and database logic, not delegated to an AI model. These controls cover authentication, authorization, status transitions, deletion restrictions and audit recording.
- **Evidence.** Claims in this report are based on the code and on the test output produced during development. The author is responsible for reviewing the code and this report before submission, and for disclosing AI assistance according to the instructor's policy.

## 12. Conclusion

MatterTrace delivers the complete review loop planned in Assignments 1 and 2:

**incoming document → candidate matter with evidence → duplicate/conflict check → human review → confirmed, corrected, rejected or escalated result → append-only audit history**

All ten functional requirements and most nonfunctional requirements are implemented and covered by a suite of 52 passing automated tests.

The prototype deliberately keeps the system in a supporting role:

- Matching is deterministic and explainable.
- The AI interface exists but is only a stub.
- Duplicates and conflicts are warnings, never actions.
- Every final matter-association decision is made by an authorized human and recorded.

The prototype is a local classroom prototype using synthetic data, not production-ready legal software. The most important next steps are:

1. validate the problem and the matching rules with real paralegals and attorneys
2. carry out a usability walkthrough
3. only then consider connecting a real AI provider, adding OCR and adding the security controls (encryption, session management) that real client data would require

## 13. References

1. Quintero, M. *MatterTrace: Source-Traceable Document Intake for Personal-Injury Practice — Assignment 1 Solution Design Report.* CEN 4010, 2026.
2. Quintero, M. *MatterTrace — Assignment 2: Solution Architecture and Design.* CEN 4010, 2026.
3. CEN 4010 course materials. *Scenario: Injure Law Office* (course-provided scenario).
4. MatterTrace source code repository. https://github.com/mathewquinte2025/Matter-Trace
5. Streamlit documentation. https://docs.streamlit.io
6. pypdf documentation. https://pypdf.readthedocs.io
7. SQLite documentation (`CREATE TRIGGER`). https://www.sqlite.org/lang_createtrigger.html
8. pytest documentation. https://docs.pytest.org
9. Python Software Foundation. `hashlib`, including `pbkdf2_hmac`. https://docs.python.org/3/library/hashlib.html

<div class="appendix" markdown="1">

## Appendix A. Automated Test Inventory

Final run: Windows 11 Home, Python 3.13.7, pytest 9.2.0. Result: **52 passed in 32.20s**.

| # | Test | Result |
|---|---|---|
| 1 | test_duplicates.py::test_exact_duplicate_is_flagged_and_both_files_preserved | Passed |
| 2 | test_duplicates.py::test_conflicting_version_is_flagged_with_reason | Passed |
| 3 | test_duplicates.py::test_revised_letter_is_flagged_as_near_duplicate | Passed |
| 4 | test_duplicates.py::test_unrelated_document_is_not_flagged | Passed |
| 5 | test_duplicates.py::test_duplicate_check_does_not_compare_against_unauthorized_documents | Passed |
| 6 | test_duplicates.py::test_flag_review_never_deletes_documents | Passed |
| 7 | test_failures.py::test_unreadable_pdf_fails_visibly_and_keeps_original[06_scanned_image_only.pdf] | Passed |
| 8 | test_failures.py::test_unreadable_pdf_fails_visibly_and_keeps_original[07_corrupted_file.pdf] | Passed |
| 9 | test_failures.py::test_binary_data_in_txt_fails_visibly | Passed |
| 10 | test_failures.py::test_failed_document_without_candidates_is_routed_to_attorney | Passed |
| 11 | test_failures.py::test_bad_ai_output_goes_to_review_never_confirmed[timeout] | Passed |
| 12 | test_failures.py::test_bad_ai_output_goes_to_review_never_confirmed[malformed] | Passed |
| 13 | test_failures.py::test_bad_ai_output_goes_to_review_never_confirmed[hallucinated] | Passed |
| 14 | test_failures.py::test_bad_ai_output_goes_to_review_never_confirmed[unauthorized] | Passed |
| 15 | test_failures.py::test_bad_ai_output_goes_to_review_never_confirmed[untraceable] | Passed |
| 16 | test_failures.py::test_valid_ai_suggestion_is_stored_as_traceable_candidate | Passed |
| 17 | test_failures.py::test_retry_after_ai_recovers_keeps_same_document_and_history | Passed |
| 18 | test_failures.py::test_retry_not_allowed_on_confirmed_document | Passed |
| 19 | test_failures.py::test_unexpected_error_becomes_processing_failed | Passed |
| 20 | test_failures.py::test_twenty_page_pdf_is_ready_for_review_within_two_minutes | Passed |
| 21 | test_intake.py::test_valid_upload_registers_metadata_and_preserves_original | Passed |
| 22 | test_intake.py::test_invalid_uploads_…[report.docx — unsupported file type] | Passed |
| 23 | test_intake.py::test_invalid_uploads_…[empty.txt — empty file] | Passed |
| 24 | test_intake.py::test_invalid_uploads_…[note.txt — source type required] | Passed |
| 25 | test_intake.py::test_invalid_uploads_…[note.txt — unknown source type] | Passed |
| 26 | test_intake.py::test_filename_path_components_are_stripped | Passed |
| 27 | test_intake.py::test_document_identity_fields_cannot_be_changed_or_deleted | Passed |
| 28 | test_intake.py::test_login_rejects_bad_password_and_logs_it | Passed |
| 29 | test_intake.py::test_unauthenticated_upload_is_refused | Passed |
| 30 | test_matching.py::test_clear_match_produces_traceable_candidate | Passed |
| 31 | test_matching.py::test_every_candidate_has_a_source_reference | Passed |
| 32 | test_matching.py::test_metadata_evidence_is_used_and_referenced | Passed |
| 33 | test_matching.py::test_similar_client_names_do_not_cross_match | Passed |
| 34 | test_matching.py::test_ambiguous_document_requires_review | Passed |
| 35 | test_matching.py::test_low_confidence_requires_review | Passed |
| 36 | test_matching.py::test_threshold_boundary | Passed |
| 37 | test_matching.py::test_threshold_is_configurable | Passed |
| 38 | test_matching.py::test_candidates_only_include_matters_the_user_can_access | Passed |
| 39 | test_matching.py::test_document_instructions_do_not_change_behavior | Passed |
| 40 | test_review.py::test_confirm_records_reviewer_from_session | Passed |
| 41 | test_review.py::test_correct_keeps_original_candidate_in_history | Passed |
| 42 | test_review.py::test_history_survives_multiple_decisions | Passed |
| 43 | test_review.py::test_reject_and_escalate_require_a_note | Passed |
| 44 | test_review.py::test_escalated_item_can_only_be_resolved_by_attorney | Passed |
| 45 | test_review.py::test_intake_clerk_cannot_confirm_even_by_calling_the_service | Passed |
| 46 | test_review.py::test_cross_matter_access_is_denied_and_logged | Passed |
| 47 | test_review.py::test_cannot_correct_to_a_matter_the_reviewer_cannot_access | Passed |
| 48 | test_review.py::test_invalid_requests_are_rejected | Passed |
| 49 | test_review.py::test_failed_document_cannot_be_confirmed_only_manually_assigned | Passed |
| 50 | test_review.py::test_flag_dismiss_requires_note_and_cannot_be_reviewed_twice | Passed |
| 51 | test_review.py::test_audit_and_decision_history_are_append_only | Passed |
| 52 | test_review.py::test_full_audit_log_is_attorney_only | Passed |

</div>
