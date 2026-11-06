# Claims data onboarding

- Add a Claims Onboarding page: name-matching and optional Gemini column-mapping suggestions (headings only), analyst approval with a correction log, plain-language editable rules, every-row checks with blockers and warnings, and a go-live readiness report.
- Reject AI mappings that name unknown or reused headings, and AI summaries that state figures or decisions not in the verified report.
- Add a deterministic synthetic claims generator with 52 planted errors and an answer key, an evaluation script, offline tests, UAT cases and case-study documentation.

# Validation-only CSV review

- Replace orders/profile browser flows with upload-only generic column type review.
- Infer reviewable types, check all readable rows, enforce a consistent selected date format and show reviewable suggestions.
- Remove browser totals, database loads and numeric range controls.
- Add generic, opt-in RAG and bounded read-only guidance with raw headers/cells excluded.
- Keep previous CLI and pipeline exercises separate.

# Changelog

## 1.0.0 — Orders assistant

- Replace the earlier domain-specific foundation with an orders-focused application.
- Add CSV contract validation, decimal totals and structured run records.
- Add JSON snapshots, SQLite history, CLI, and a local Streamlit browser demo.
- Add optional evidence-checked Gemini classification with redacted requests.
- Add offline tests and update Linux/Windows CI and learning documentation.
- Preserve the original beginner orders exercise separately.
