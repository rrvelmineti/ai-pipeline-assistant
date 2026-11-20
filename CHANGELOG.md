# A dark, cinematic interface for the claims platform

- Restyle every screen with a dark theme: black stage, one bold red for the brand and main actions, a condensed display face (Bebas Neue, bundled) for titles and figures. Status colours keep their meaning: red-orange blockers, amber warnings, green passed; the current stage is white, so red still means a problem.
- Home: a billboard features the client that most needs a person (most open blockers, then waiting for approval), above a number strip and rows of client cards (Needs attention, In progress, Ready for go-live, Live) with arrow scrolling. The full client table stays below as "All clients".
- Client pages open with a full-width header in the client's poster art; the sign-in page shows the card over a wall of poster art.
- Poster art is drawn with CSS gradients from the client code, so there are no image files and the content security policy is unchanged.
- Add `src/components/Poster.tsx` and `src/__tests__/dashboard.test.tsx` (featured-client choice and poster art). No API or behaviour changes.

# Fix the demo load on Render

- The container image now includes `examples/claims/` (the synthetic sample the demo loader reads); without it the first demo load on Render failed.
- On start-up, a demo load that stopped part-way is cleared and run again, but only when the database holds nothing but demo users and clients.
- CI loads the demo from only the files the image contains, so a missing file is caught before deployment.

# Deploy the claims platform on Render's free tier

- Add `render.yaml`: a free Docker web service and a free PostgreSQL 16 database, with generated secrets.
- Add `CLAIMS_FILE_STORE=database` so uploads survive hosts whose disk is wiped on restart; `rotate-key` covers it.
- Load the synthetic demo (or create the first administrator) automatically on the first start, for hosts without a shell; `/api/health` reports the demo's status.
- Accept host-style `postgres://` URLs and any 32+ character secret as the encryption key; the container listens on `$PORT`.
- Add `tests/test_platform_deploy.py` and `docs/platform/deploy-render.md`.

# Claims Onboarding and Exception Management Platform, pilot v1.0

- Add `claims_platform`: a FastAPI service with sign-in, four roles, client separation, encryption at rest and a hash-chained audit trail, on PostgreSQL or SQLite.
- Add versioned per-client rules with four-eyes approval; mapping suggestions with confidence levels, abstention, required confirmation, approval and reusable templates.
- Add validation runs with retry and crash recovery, an exception register tracked across resubmissions (resolve, reopen, accept warnings with a reason), readiness checks that block go-live while blockers remain, and go-live approval.
- Add export to a simulated downstream system with idempotent, resumable batches; scorecards, portfolio KPIs, processing metrics, the evidence package, client letters, AI explanations with a rule-based fallback, and an implementation timeline.
- Add `claims_platform_web`: React + TypeScript interface with the five screens.
- Add scenarios A–F and a 100,000-row performance run (`evaluation/platform_scenarios.py`), 41 platform tests, 8 interface tests, and the platform documentation set in `docs/platform/`.
- Add a Dockerfile and a compose file with PostgreSQL. CI now also tests on PostgreSQL and builds and tests the interface.
- Refactor `claims_onboarding.mapping` to expose `score_heading`; behaviour unchanged.

# Claims onboarding: client handoff

- Add a client issue letter: findings grouped by rule in the client's own column names, with up to 5 example lines and how to fix each. Written by code from the verified report.
- Add a resubmission comparison: upload the previous JSON report to see each rule group fixed, improved, unchanged, worse or new; flags a changed mapping or the same file sent twice.
- Add an implementation playbook, a sample client letter, UAT cases 18 to 21 and 9 offline tests.

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
