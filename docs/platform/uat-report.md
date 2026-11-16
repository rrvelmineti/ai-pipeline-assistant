# UAT report: pilot v1.0

**Date:** 15 November 2026. **Build:** branch `feature/claims-platform-pilot`. **Data:** synthetic only.

## Summary

| Area | Result |
| --- | --- |
| Scenario checks A–F (scripted UAT through the API) | **49 of 49 passed**, on SQLite and on PostgreSQL 16 |
| Acceptance criteria AC-1 to AC-7 | All met; see the [traceability matrix](traceability.md) |
| Python tests (platform) | 41 passed, on Python 3.10 and 3.13 |
| Python tests (existing tools) | 78 passed, unchanged |
| Interface tests | 8 passed (Vitest) |
| 100,000-row file | Validated in 5.1–5.6 s across runs; exported in about 4 s (SQLite) and 8 s (PostgreSQL); every claim loaded once |
| Browser walk-through | Every screen opened as approver and analyst, desktop and phone width, in headless Chromium; no console errors, no horizontal scrolling |

## How UAT was run

The plan's six scenarios are scripted in [`claims_platform/scenarios.py`](../../claims_platform/scenarios.py).
Each one drives the HTTP API as the named people would (analyst, approver, client contact,
administrator) and records, for every acceptance criterion, what was expected and what actually
happened. The same script:

- runs in CI through `tests/test_platform_scenarios.py`;
- produces the [traceability matrix](traceability.md) with `python -m evaluation.platform_scenarios --save`;
- loads the demo database with `python -m claims_platform.cli seed-demo`.

| Scenario | What it exercises | Checks |
| --- | --- | --- |
| A Clean file | Straight through: mapping, validation, readiness, four-eyes go-live, export, evidence | 6 |
| B Poor quality | The 2,000-row sample with 52 planted errors: recall, exceptions, blocked approval, accepted warning, client letter, explanations without AI | 9 |
| C Different schema | Another vendor's headings, ambiguous NPI columns, US dates; confirmation, correction log, versioned rule change, template reuse | 9 |
| D Multiple resubmissions | Four files: fixed, still open, new, regressed and reopened; scorecard | 5 |
| E Operational failure | Duplicate upload, failed run, crash mid-run, truncated and corrupt files, downstream outage and lost acknowledgement | 10 |
| F Security boundaries | Client separation, roles, sessions, lockout, four-eyes for administrators, weak passwords, audit chain | 10 |

## Findings during UAT and what changed

| # | Found | Change |
| --- | --- | --- |
| 1 | Re-sending an older file after a newer bad one was treated as a duplicate, so the client could not recover | Duplicates are now "the same bytes as the latest submission"; an older file sent again is a real resubmission (check E7) |
| 2 | An incomplete scan could have resolved exceptions it never reached | Exceptions are resolved only by a complete scan (check E6, `test_incomplete_scan_does_not_resolve_anything`) |
| 3 | Name matching chose the billing NPI for one vendor layout, with nothing to stop it | Ambiguity detection: another heading within 0.15 makes the field ambiguous and it must be confirmed (checks C1–C3) |
| 4 | SQLAlchemy 2.1 does not support Python 3.10, which CI runs | Pinned SQLAlchemy 2.0.55 and re-ran everything on 3.10 |
| 5 | On a phone, wide tables pushed the whole page sideways | Tables now scroll inside their panel |
| 6 | The "AI unavailable" message pointed at Streamlit settings | The platform now explains it in its own terms and shows it as information, not an error |
| 7 | A live client showed the "rules confirmed" step as not started | The go-live approval now confirms the rules in force for that client |

## Not yet tested

- Formal sign-off by a business user. Before a demo to a sponsor, walk through the
  [demo script](demo.md) by hand and add your initials here.
- Live Gemini behaviour in the platform. The checks around it (no values sent, invented figures
  rejected, fallback when unavailable) are tested offline; the original assistant's Gemini mapping
  score was 12 of 12 ([evaluation](../../evaluation/results/claims_mapping.json)).
- The Docker image build (the registry was not reachable from the build environment).
- Concurrency beyond one process, browsers other than Chromium, and screen readers.

| Sign-off | Name | Date |
| --- | --- | --- |
| Business user | | |
| Approver | | |
