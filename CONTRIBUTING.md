# Contributing to MatterTrace

MatterTrace is a student portfolio project for CEN 4010 (Principles of Software Engineering). Suggestions and bug reports are welcome, but the scope is intentionally small.

## Reporting an issue

Open a GitHub issue at <https://github.com/mathewquinte2025/Matter-Trace/issues>. Include:

- what you did
- what you expected
- what happened
- your Python version

**Never attach real client, medical, legal or personal documents.** Use the files in `sample_docs/` or other synthetic data.

## Proposing a change

1. Fork the repository and create a branch from `main`.
2. Set up the environment as described in the [README](README.md#5-installation-windows--powershell).
3. Keep the change focused, and match the existing style: plain Python modules, no new frameworks.
4. Add or update tests in `tests/` for any behavior change.
5. Run the full suite and make sure it passes:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -v
   ```
6. Open a pull request that explains what changed and why.

## Project rules that changes must keep

- MatterTrace only **suggests**. It must never automatically confirm, delete, merge or replace a document.
- Duplicate and conflict results are **warnings only**.
- Authorization is enforced in the service layer (`mattertrace/`), not only by hiding buttons in the UI.
- Audit events and review decisions are append-only.
- Raw AI output is never stored or shown to reviewers.
- Data must be synthetic. Do not commit `data/`, `.env` files or credentials.

Changes outside the documented scope are unlikely to be accepted. Out of scope means legal analysis, chronology generation, cloud services, new file types or a real AI provider without validation.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
