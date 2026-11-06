# Claims data onboarding: user stories

These stories were first drafted with an AI assistant from a short brief, then reviewed.
Record any changes you make in the review log at the end, so the difference between the
AI draft and the final version stays visible.

**Brief given to the AI:** "A health insurer is onboarding a new client's claims file.
Write user stories with acceptance criteria for an analyst tool that suggests column
mappings with AI, lets the analyst approve them, checks business rules in code, and
produces a go-live readiness report. Synthetic data only."

---

### US-1 Upload a client claims file

As an implementation analyst, I want to upload the client's claims CSV so that I can start
onboarding without preparing the file by hand.

Acceptance criteria:
- A UTF-8 CSV with a header row up to 20 MB is accepted.
- A file with missing or duplicate headers is rejected with a clear message.
- Nothing is analyzed until a file is uploaded.

### US-2 Get suggested column mappings

As an implementation analyst, I want the tool to suggest which client column matches each
target field so that I don't have to map 12 fields from scratch.

Acceptance criteria:
- Every target field shows a suggested client column, or "not mapped" if there is no match.
- Each suggestion shows where it came from (name matching or AI) and a short reason.
- The AI receives column headings and target field descriptions only, never cell values.
- If the AI is unavailable or returns an invalid answer, name-matching suggestions remain.

### US-3 Approve or correct each mapping

As an implementation analyst, I want to approve or change each suggested mapping so that I
stay in control of the final decision.

Acceptance criteria:
- I can change the client column for any target field.
- One client column cannot be mapped to two target fields.
- Every change from the suggestion is recorded in a correction log with the field, the
  suggested column and the chosen column.
- Validation cannot run while a required field is unmapped.

### US-4 Check the file against plain-language rules

As a business owner, I want onboarding rules written in plain language so that I can read
and change them without editing code.

Acceptance criteria:
- Rules are stored in a text file, one field per line, such as
  `provider_npi | ... | required, exactly 10 digits`.
- An unknown rule phrase is rejected with the line number, rather than silently ignored.
- A rule can be marked `(warning)` so that it does not block go-live.

### US-5 See every problem with its location

As a client data contact, I want each problem listed with its line, field and value so that
I can fix it in my source system.

Acceptance criteria:
- Every readable row is checked, not a sample.
- Each finding shows CSV line, target field, client column, entered value, the rule broken
  and its severity (blocker or warning).
- Findings can be downloaded as CSV.

### US-6 Get a go-live readiness decision

As an approver, I want a clear ready or not-ready decision with the reasons so that I can
sign off or send the file back.

Acceptance criteria:
- The decision is "Ready" only if all required fields are mapped, the scan is complete and
  there are zero blockers.
- The report shows counts of blockers and warnings by rule.
- The report can be downloaded as JSON and Markdown.

### US-7 Read a plain-English summary

As an approver who is not technical, I want a short written summary of the readiness report
so that I understand it without reading the full finding table.

Acceptance criteria:
- A summary written by code is always shown.
- An optional AI summary receives only the aggregate figures, never cell values.
- If the AI summary contains a number that is not in the verified figures, it is rejected
  and the code-written summary is shown instead.

### US-8 Measure how good the AI mapping is

As the analyst responsible for the tool, I want to compare AI mapping suggestions against a
known-correct answer key so that I know how far to trust them.

Acceptance criteria:
- A script compares suggestions to an answer key and reports correct, wrong and missed
  fields.
- It can run offline for name matching and with a Gemini key for AI suggestions.

---

## Review log

| Story | What changed after review | Why |
| --- | --- | --- |
| | | |
