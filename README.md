# MatterTrace

**Source-traceable document intake and matter association prototype**: CEN 4010 Principles of Software Engineering, Final Project.

Repository: <https://github.com/mathewquinte2025/Matter-Trace>

MatterTrace is a local prototype that runs on your own machine through Streamlit. It is not deployed online. All data in this repository is synthetic.

---

## 1. Purpose and stakeholder problem

Personal-injury law offices receive documents through many channels: client uploads, email, mail, provider portals, insurers, experts and courts. For each document, a paralegal currently has to:

- work out which client matter it belongs to
- record where it came from
- check whether it duplicates, replaces or conflicts with a record already on file

This sorting is repetitive. Errors such as misfiled records, missed duplicates and conflicting bills are costly and hard to trace afterwards.

MatterTrace is a bounded **decision-support** tool for litigation paralegals and supervising attorneys. It:

- registers each incoming document
- extracts its text
- **suggests** a matter, with the exact source passages that support the suggestion
- warns about possible duplicates or conflicts

An authorized human always makes the final decision.

> MatterTrace never automatically confirms an association, and never deletes, merges or replaces a document. Duplicate and conflict results are warnings only.

The scope follows the Assignment 1 (requirements) and Assignment 2 (solution architecture and design) reports, which are based on the course-provided Injury Law Office scenario. The following are out of scope:

- legal analysis
- chronology generation
- case valuation
- full document management

## 2. Main features and workflow

```
Upload ──► Preserve original + register metadata ──► Extract text ──► Suggest matter with evidence
   ──► Check duplicates / conflicts ──► Human review ──► Save decision + append-only audit history
```

| Feature | What it does |
|---|---|
| **Intake** | Accepts PDF and TXT files up to 10 MB, together with the source type and an optional description. Each file gets a stable document ID (`DOC-…`) and a SHA-256 checksum, and the original is written once and never overwritten. |
| **Text extraction** | Extracts PDF text page by page and TXT text paragraph by paragraph. Every passage keeps its location, so evidence can be cited. |
| **Matter suggestion** | A deterministic rule-based matcher suggests up to 3 candidate matters. It scores matter numbers, claim numbers, client names, dates of birth and incident dates, and shows every evidence passage with its page or paragraph. |
| **Confidence threshold** | Configurable (default `0.60`). Results below the threshold, close calls between two matters, and any warning send the document to **Needs Review**. |
| **Duplicate / conflict check** | Flags three kinds of result: <br>• **exact duplicates**, which have the same checksum <br>• **possible conflicts**, which share a reference number but have a different amount or date of service <br>• **near-duplicates or other versions**, based on text similarity. <br>Documents the user is not allowed to see are never compared. |
| **Human review** | An authorized reviewer can **confirm**, **correct**, **reject** or **escalate**. Reject and escalate require a note. Only attorneys can resolve escalations. |
| **Failure handling** | Unreadable files, scanned PDFs with no text, AI-service problems and unexpected errors get a clear status and reason, plus a retry or manual-assignment path. |
| **Audit history** | Every upload, view, decision, access denial and retry is recorded. The database rejects edits to or deletion of audit events and decisions. |
| **AI interface** | A replaceable interface with a stub implementation. Any AI output is validated, and raw model text is never stored or shown. |

**Document statuses:** Received, Processing, Candidate Ready, Needs Review, Confirmed, Corrected, Rejected, Escalated, Processing Failed.

**Candidate Ready** means "ready for a human to review". It is never a confirmation.

## 3. Architecture

This is a single local application: a Streamlit user interface over a set of plain Python service modules, with a SQLite database and a local folder of original files.

Authorization is enforced in the service layer, not only by hiding buttons. The reviewer's identity always comes from the authenticated session.

```
app.py (Streamlit UI)
   │  calls services with an authenticated session
   ▼
mattertrace/  intake ─ extraction ─ matching ─ ai_service ─ duplicates
                 └──────────── pipeline (orchestration, status, retry) ───────────┘
              review (decisions, transition rules)   auth (roles, matter scoping)   audit
   │
   ▼
data/mattertrace.db (SQLite)      data/originals/ (stored original files)
```

| File | Component (Assignment 2, section 7.2) |
|---|---|
| `app.py` | 9. Review Workbench, plus the login, upload and audit-log pages |
| `mattertrace/intake.py` | 1. Intake and 3. Document Store (original written once, SHA-256 checksum) |
| `mattertrace/auth.py` | 2. Access Control (PBKDF2 password hashes, roles, matter-scoped visibility) |
| `mattertrace/db.py` | 4. Metadata repository: the SQLite schema. Triggers make audit events and decisions append-only and documents undeletable. |
| `mattertrace/extraction.py` | 5. Text Extraction (PDF per page via `pypdf`; TXT per paragraph) |
| `mattertrace/matching.py` | 6/7. Candidate retrieval and the deterministic rule-based matcher |
| `mattertrace/ai_service.py` | 7. Replaceable AI interface, stub implementation and strict output validation |
| `mattertrace/duplicates.py` | 8. Duplicate / Conflict Checker |
| `mattertrace/pipeline.py` | Orchestration, status decision, retry and failure handling (11. Exception path) |
| `mattertrace/review.py` | 10. Decision / Audit Service: review bundle, actions and transition rules |
| `mattertrace/audit.py` | Append-only audit log |
| `mattertrace/config.py`, `context.py`, `errors.py` | Settings, shared application context and error types |
| `mattertrace/seed.py`, `sample_data.py` | Synthetic matters, users, existing records and sample uploads |
| `tests/` | Automated pytest suite (52 tests) |

### Key design decisions

- **Matching score:** the sum of the weights of the signals found, capped at 1.0.
  - Weights: matter number 0.50, claim number 0.50, client name 0.35, DOB 0.25, incident date 0.10.
  - Labels: **High** at 0.85 or above; **Medium** from the threshold up to 0.85; **Low** below the threshold.
- **When a result is Candidate Ready:** the best score is at or above the threshold, and none of these apply:
  - another matter scores within 0.15 of the best
  - there is a duplicate or conflict warning
  - there is an AI-service problem
  - the AI and the rules disagree on the best matter

  Otherwise the result is **Needs Review**, with the reasons listed.
- **Document visibility:**
  - A document with an associated matter is visible only to users with access to that matter.
  - An unassociated document is visible to the person who submitted it and to users with access to one of its candidate matters.
  - Unassociated documents with no candidates are also visible to attorneys.
- **AI output:** AI suggestions are kept only if all of these hold:
  - the output is well-formed
  - the matter ID is one the user is permitted to see
  - the suggestion cites at least one real segment of the document
- **Retry:**
  - Allowed from Processing Failed, Needs Review or Rejected.
  - It keeps the same document ID.
  - Earlier unreviewed candidates and warnings are marked *Superseded* rather than deleted.

## 4. Technologies and prerequisites

- **Python 3.11 or later.** Developed and tested with Python 3.13 on Windows 11.
- **[Streamlit](https://streamlit.io/)** for the user interface.
- **SQLite**, through Python's built-in `sqlite3` module. No database server is needed.
- **[pypdf](https://pypi.org/project/pypdf/)** for PDF text extraction.
- **[pytest](https://pytest.org/)** for automated tests.
- **Git**, to clone the repository.

Exact versions are pinned in [`requirements.txt`](requirements.txt). No cloud services, external APIs or API keys are required.

## 5. Installation (Windows / PowerShell)

```powershell
git clone https://github.com/mathewquinte2025/Matter-Trace.git
cd Matter-Trace
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The commands call the virtual environment's Python directly, so you do not need to activate it. If you prefer to activate it, run `.\.venv\Scripts\Activate.ps1`. PowerShell may first require `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 6. Running the application

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit opens the app at <http://localhost:8501>. Stop it with `Ctrl+C`.

On first run, the app:

- creates `data/mattertrace.db` and `data/originals/`
- seeds the synthetic demo users, matters and existing records
- writes the sample upload files if the `sample_docs/` folder is missing

To reset the demo data to a clean state, stop the app first and then run:

```powershell
.\.venv\Scripts\python.exe -m mattertrace.seed --reset
```

### Settings (optional environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MATTERTRACE_CONFIDENCE_THRESHOLD` | `0.60` | Minimum score for a "Candidate Ready" result |
| `MATTERTRACE_DATA_DIR` | `./data` | Where the database and original files are stored |
| `MATTERTRACE_AI_SERVICE` | `stub` | `stub` or `none`. No real AI provider is connected. |

Example: `$env:MATTERTRACE_CONFIDENCE_THRESHOLD = "0.75"` before starting the app.

## 7. Running the automated tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

The suite has 52 tests, which run in under a minute. Each test uses its own temporary database and folder, so tests never touch `data/`.

| Test file | Covers |
|---|---|
| `tests/test_intake.py` | Valid and invalid uploads, filename sanitizing, immutable originals, login |
| `tests/test_matching.py` | Evidence, ambiguity, low confidence, threshold, matter scoping, prompt-injection text |
| `tests/test_duplicates.py` | Exact duplicates, conflicts, near-duplicates, no comparison with unauthorized documents |
| `tests/test_review.py` | Confirm, correct, reject, escalate, permissions, append-only history, audit-log access |
| `tests/test_failures.py` | Unreadable files, faulty AI output, retry, rollback on errors, 20-page PDF response time |

## 8. Demo login accounts

All accounts use the password **`demo123`**. These are demo credentials for synthetic data only.

| Username | Role | Matter access | Can do |
|---|---|---|---|
| `pat` | Paralegal | MT-1001, MT-1002, MT-1004 | upload, review |
| `riley` | Paralegal | MT-1003 | upload, review |
| `avery` | Supervising attorney | all | upload, review, resolve escalations, view full audit log |
| `casey` | Intake clerk | all | upload only (cannot review) |

## 9. Synthetic sample documents

Every name, date, claim number and amount in this repository is invented. The seed data contains:

- **Four synthetic matters:**
  - MT-1001 Daniel Reyes
  - MT-1002 Grace Okafor
  - MT-1003 Erik Lindqvist
  - MT-1004 Daniela Reyes, whose name is deliberately similar to MT-1001
- **Four existing records** that the duplicate checks compare against.

The files in [`sample_docs/`](sample_docs/) each demonstrate one scenario. Log in as `pat` and upload them on the **Upload** page:

| File | Scenario | Expected result |
|---|---|---|
| `01_clear_match_reyes_records_request.txt` | Clear match | Candidate Ready, MT-1001, High, 4 evidence passages |
| `02_duplicate_reyes_er_bill.pdf` | Exact duplicate | Needs Review + "Exact duplicate" warning linked to the seeded bill |
| `03_conflicting_reyes_er_bill.txt` | Conflict | Needs Review + "Possible conflict" (same invoice, different total) |
| `04_ambiguous_two_clients.txt` | Ambiguous | Needs Review: MT-1002 and MT-1004 tie |
| `05_low_confidence_fax_cover.txt` | Low confidence | Needs Review: score 0.10 is below 0.60 |
| `06_scanned_image_only.pdf` | No text layer | Processing Failed, with retry and manual-assignment path |
| `07_corrupted_file.pdf` | Damaged file | Processing Failed, with retry and manual-assignment path |
| `08_okafor_insurer_letter_revised.txt` | Revised version | Needs Review + "Possible duplicate / other version" |
| `09_lindqvist_pt_note_followup.txt` | Matter scoping | No candidate for Pat (MT-1003 is Riley's); Riley gets MT-1003 |

You can also try the following:

- **Wrong matter:** open a candidate and choose **Correct**. The original suggestion stays in the history.
- **Unauthorized access:** as `riley`, use "open by document ID" on one of Pat's documents. Access is denied and the attempt is logged.
- **Escalation:** escalate a document as `pat`, then resolve it as `avery`.
- **No reviewer rights:** log in as `casey`. Casey can upload, but no review actions are offered, and the service refuses them if called directly.

**Only upload synthetic or explicitly authorized documents.** Never upload real client, medical or legal records.

## 10. Privacy and security boundaries

**What the prototype does:**

- uses synthetic data only
- stores password hashes (PBKDF2), never plain passwords
- checks every action against the user's role and matter access in the service layer
- shows the same "not found or no access" message for missing and forbidden documents, so it does not reveal which documents exist
- logs denied access attempts
- stores originals under generated document IDs, and the database prevents documents from being deleted
- sends the AI interface only the minimum permitted context
- discards AI output that fails validation, and never shows raw model text

**What it does not do, so it is not suitable for real client data:**

- **No encryption at rest:** the database and original files in `data/` are stored unencrypted.
- **No account protection:** there is no session timeout or account lockout, and the demo accounts share one known password.
- **No production authentication or hardening:** there is no single sign-on, HTTPS setup or network hardening. It is intended for `localhost` only.
- **Local runtime data is excluded from Git:** `data/` holds the database and stored uploads, and is excluded by [`.gitignore`](.gitignore).

## 11. Known limitations

- **Rule-based matcher only.** Matching uses fixed weights and regular-expression patterns for identifiers, names and dates. These patterns ignore case and separators. The matcher does not understand context, does not do fuzzy matching of misspelled names, and cannot match documents that contain no identifiers. Its weights have not been tuned against real data.
- **No real AI provider is connected.**
  - The AI interface uses a stub that returns no suggestions.
  - The validation path is tested only with fake services that time out, return malformed output, invent a matter ID, suggest an unauthorized matter, give untraceable evidence, or return valid output.
- **No OCR.** Scanned or image-only PDFs fail with a clear reason and a manual-assignment path.
- **Only PDF and TXT files** up to 10 MB are accepted.
- **No separate Exception Queue component.** Failed, Needs Review and Escalated items appear through a filter in the Review queue.
- **No return-to-paralegal step for escalations.** Attorneys resolve escalated items directly.
- **The browser upload widget is not covered by automated UI tests.** Streamlit's test harness does not support it. Intake is tested at the service level.
- **No usability walkthrough and no stakeholder validation.** No real stakeholder has validated the problem or the matching rules (see Assignment 1, section 2.1).
- **Local prototype only.** It is not designed or hardened as a shared multi-user server.

## 12. License and contributing

Released under the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for how to report issues or propose changes.
