# Process maps: current and future state

## Current state (manual)

How onboarding typically runs without the platform: spreadsheets, e-mail and a shared folder.
This is a description of the common pattern, not a measurement of any specific team.

```mermaid
flowchart TD
    A[Client e-mails or uploads an extract] --> B[Analyst opens it in a spreadsheet]
    B --> C[Analyst maps columns by eye<br/>in a mapping spreadsheet]
    C --> D[Analyst spot-checks rows<br/>and filters for obvious problems]
    D --> E[Analyst writes an e-mail<br/>listing the problems found]
    E --> F[Client fixes some problems<br/>and sends a new file]
    F --> B
    D --> G{Lead satisfied?}
    G -- Yes --> H[Go-live agreed by e-mail]
    H --> I[Load script run by hand]
    I --> J{Load failed part-way?}
    J -- Yes --> K[Re-run the script<br/>and clean up duplicates]
    J -- No --> L[Live]
```

### Pain points

| # | Where | Problem |
| --- | --- | --- |
| 1 | Mapping | Mapped by eye; nothing records who decided, or whether an ambiguous column (two NPI columns) was checked |
| 2 | Checking | Rows are sampled, not all checked; results depend on the analyst |
| 3 | Rules | Rules live in people's heads or an old document; changes are not versioned |
| 4 | Resubmission | Which problems were fixed, which are new, which came back: worked out by hand each round |
| 5 | Exceptions | Tracked in e-mail threads; no owner, status or history |
| 6 | Go-live | Agreed by e-mail; nothing stops approval while known blockers remain |
| 7 | Load | A failure part-way can duplicate claims on re-run |
| 8 | Evidence | Assembling proof of the decision afterwards takes days, if possible at all |
| 9 | Measurement | Rounds, rework and time to resolve are not recorded, so they cannot be improved |

## Future state (with the platform)

```mermaid
flowchart TD
    A[Client contact or analyst<br/>uploads the extract] --> B{Same as the<br/>latest file?}
    B -- Yes --> B1[Ignored: no duplicate submission]
    B -- No --> C[Stored encrypted, fingerprinted]
    C --> D{Approved mapping<br/>fits this layout?}
    D -- No --> E[Suggestions with confidence:<br/>name matching, saved templates,<br/>optional Gemini on headings only]
    E --> F[Analyst confirms every uncertain field]
    F --> G[Approver approves the mapping<br/>four-eyes]
    G --> H
    D -- Yes --> H[Code checks every row<br/>against the approved rule version]
    H --> I[Exception register updated:<br/>new, still open, resolved, reopened]
    I --> J{Readiness:<br/>all 8 checks pass?}
    J -- No --> K[Letter drafted by code<br/>in the client's column names]
    K --> L[Analyst releases it to the client]
    L --> A
    J -- Yes --> M[Approver approves go-live<br/>four-eyes, comment recorded]
    M --> N[Export in batches<br/>with idempotency keys]
    N --> O{Batch failed?}
    O -- Yes --> P[Retry resumes from the failed batch;<br/>replays never duplicate a claim]
    P --> N
    O -- No --> Q[Live: evidence package available]
```

### What changes

| Pain point | Future state | Control |
| --- | --- | --- |
| 1 Mapping by eye | Suggestions with confidence; uncertain fields must be ticked; a second person approves | AC-1, P1-03 |
| 2 Sampling | Every row checked by code | P1-04 |
| 3 Unversioned rules | Plain-language rules per client, versioned, approved by a second person | P1-02 |
| 4 Manual comparison | Automatic comparison per rule group: fixed, still open, new | P1-06 |
| 5 E-mail exceptions | Exception register with owner, status, notes and history | P1-05 |
| 6 Approval with blockers | Approval is blocked by the readiness checks | AC-2 |
| 7 Duplicate loads | Idempotent batches and per-claim dedupe | AC-3 |
| 8 Evidence after the fact | Evidence package generated on demand, with a hash manifest | P2-04 |
| 9 No measurement | Scorecards and portfolio KPIs from the records | P2-01 |

## Swimlane: who does what

| Step | Client contact | Analyst | Approver | Platform (code) | AI (optional) |
| --- | --- | --- | --- | --- | --- |
| Upload | Uploads | Uploads | | Dedupes, encrypts, fingerprints | |
| Mapping | | Confirms or changes | Approves or returns | Suggests with confidence; enforces confirmation | Suggests from headings only |
| Rules | | Proposes a change | Approves or rejects | Parses; refuses unclear rules | |
| Validation | | Starts the run | | Checks every row; updates exceptions | Never |
| Exceptions | Adds notes | Assigns, sets status | Accepts warnings with a note | Resolves automatically when absent from a full scan | Rewords explanations on request |
| Letters | Reads released letters | Drafts and releases | May release | Writes the letter from findings | |
| Go-live | | | Approves or rejects | Blocks approval unless all checks pass | |
| Export | | Starts, resumes | | Batches, dedupes, records | |
