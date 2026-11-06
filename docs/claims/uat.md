# Claims data onboarding: UAT test cases

Each case links to the user story it proves. "Actual" records what happened when the case
was run. Every case also has an automated equivalent in `tests/test_claims.py`, so it is
re-checked on every push by GitHub Actions.

Run on 5 November 2026 against `examples/claims/client_claims.csv` (2,000 synthetic rows,
52 planted errors) using the automated tests. Before a demo, also walk through cases 1, 4,
7 and 12 by hand in the browser and add your initials.

| # | Story | Steps | Expected | Actual | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | US-1 | Open the page without uploading | No mapping controls or report shown | No controls shown | Pass |
| 2 | US-4 | Edit a rule to `required, sparkly` | Error naming the unrecognised rule; no check runs | Error shown naming "sparkly" | Pass |
| 3 | US-4 | Rules refer to a field that does not exist (`not greater than b`) | Rules rejected with a clear message | Rejected | Pass |
| 4 | US-2 | Upload the sample file | Suggestions shown for every target field, with source and reason | 9 fields suggested by name matching, 3 left blank | Pass |
| 5 | US-2 | Name matching with two NPI columns (billing and rendering) | Rendering NPI chosen, not billing NPI | Rendering NPI chosen | Pass |
| 6 | US-2 | Gemini response names a heading that is not in the file | Whole AI answer rejected, name-matching suggestions kept | Rejected with message | Pass |
| 7 | US-3 | Leave required fields unmapped | Check button disabled; warning lists the fields | Disabled; diagnosis_code, procedure_code, billed_amount listed | Pass |
| 8 | US-3 | Map one client column to two fields | Check blocked with a warning | Blocked | Pass |
| 9 | US-3 | Correct the 3 blank mappings | Correction log shows 3 entries with suggested and chosen columns | 3 entries logged | Pass |
| 10 | US-3 | Change a mapping after checking | Old report cleared so it cannot be mistaken for current | Report cleared | Pass |
| 11 | US-5 | Check the sample with the correct mapping | All 52 planted errors found, at the right lines, with no false alarms | 52 of 52 found, 0 false alarms | Pass |
| 12 | US-6 | Review the readiness decision for the sample | "Not ready", 42 blockers, 10 warnings | Not ready, 42 blockers, 10 warnings | Pass |
| 13 | US-6 | Check a clean file with one warning only | "Ready"; warning listed but not blocking | Ready, 1 warning | Pass |
| 14 | US-7 | AI summary states a figure not in the report (e.g. "95%") | Summary rejected; code-written summary shown | Rejected | Pass |
| 15 | US-7 | AI summary says "ready" when the decision is "Not ready" | Summary rejected | Rejected | Pass |
| 16 | US-2, US-7 | Inspect what is sent to Gemini | Headings and aggregate counts only; no claim IDs, NPIs, dates or amounts | No data values found in any request | Pass |
| 17 | US-8 | Run `python -m evaluation.claims_mapping` | Mapping score and rule-check recall printed | Name matching 9 of 12 correct, 0 wrong; rules 52 of 52 | Pass |

## Not yet tested

- Live Gemini mapping accuracy. Run `python -m evaluation.claims_mapping --gemini --save`
  with a key, then record the score here and in the README.
- Files larger than the 2,000-row sample, up to the 100,000-row limit.
