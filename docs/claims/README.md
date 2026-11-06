# Claims Data Onboarding Assistant: case study

A health insurer is onboarding a new client's claims file. This tool takes the client's raw
extract to a go-live decision: AI suggests how the client's columns map to the platform's
fields, the analyst approves or corrects each one, code checks every row against
plain-language rules, and a readiness report says **Ready** or **Not ready** with reasons.

All data is synthetic. See the [implementation playbook](implementation-playbook.md),
[problem statement](problem-statement.md),
[user stories](user-stories.md), [process map](process-map.md) and [UAT results](uat.md).

## Try it

```
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open **Claims Onboarding** in the sidebar, download the synthetic sample file from the page,
and upload it. Three fields are left blank by name matching; map them yourself or ask Gemini,
then approve the mapping.

## How it works

| Step | What happens | AI or code |
| --- | --- | --- |
| Rules | `claims_onboarding/rules.txt`, written in plain language, one field per line. Editable in the page. Unknown phrases are rejected with the line number. | Code |
| Mapping | Name matching expands abbreviations (Clm, Dx, DOS, Svc) and scores word overlap. Gemini can be asked to suggest mappings from the headings and field descriptions. | Both |
| Approval | The analyst picks the final column for every field. Every change from the suggestion is logged. | Human |
| Checks | Every row is checked: required, unique, number formats, 10-digit NPI, ICD-10 shape, dates not in the future, service not before birth, paid not above billed, allowed status values. | Code |
| Decision | Ready only if required fields are mapped, the scan finished, and there are zero blockers. | Code |
| Summary | A code-written summary always. An optional Gemini summary is rejected if it states any figure or decision not in the report. | Both |
| Client letter | Problems grouped by rule in the client's own column names, with up to 5 example lines and how to fix each. [Sample](sample-client-letter.md). | Code |
| Resubmission | Upload the previous JSON report: each rule group is marked fixed, improved, unchanged, worse or new. A changed mapping or the same file sent twice is flagged. | Code |

## Results

Measured with `python -m evaluation.claims_mapping` on the 2,000-row sample:

| What | Result |
| --- | --- |
| Name-matching mappings | 9 of 12 correct, 0 wrong, 3 left blank for the analyst |
| Gemini mappings | Not yet measured. Run with `--gemini --save` and record the score here |
| Planted errors found by the rule checks | 52 of 52, with 0 false alarms |
| Readiness decision for the sample | Not ready: 42 blockers, 10 warnings |

Name matching is deliberately cautious: it leaves a field blank rather than guess, so the
analyst sees exactly where judgment is needed.

## Where AI is and is not used, and why

- **Mapping suggestions: AI helps.** Matching messy headings like "Svc Code" or
  "Total Charges" to target fields is a language problem, which is what a model is good at.
  The model sees only headings and field descriptions, **never cell values**, so no member
  data leaves the environment. Its answer is rejected outright if it names a heading that is
  not in the file, reuses a heading, or skips a field.
- **Rule checks: no AI.** Whether an NPI has 10 digits or paid exceeds billed must be exact
  and repeatable, so code decides.
- **The decision: no AI.** Ready or not ready is computed from counts, never generated.
- **Summary: AI may rephrase, not invent.** Every number in an AI summary must already be in
  the verified report, and it must state the same decision, or it is discarded.

## How I used AI to build this

- **Requirements.** I gave an AI assistant a short brief and had it draft the problem
  statement and user stories, then reviewed them. Changes are recorded in the review log in
  [user-stories.md](user-stories.md).
- **Build.** I wrote a finish line first (six deliverables, what "done" means, what is out
  of scope) and used an AI coding assistant to build against it in small steps, checking
  each step by running it rather than trusting the generated code.
- **What the AI got wrong, and how it was caught.**
  - A privacy test flagged the word "paid" as leaked data; it was a field description, not
    data. The test was narrowed to real data values (IDs, NPIs, dates, amounts) and now
    checks over 500 of them.
  - A hand-written test row accidentally had paid greater than billed. The validator flagged
    it correctly; the test expectation was wrong, not the code.
  - Generated files were first written to the wrong folder and the package could not be
    imported. Running the code immediately exposed it.
- **Verification.** The synthetic file has 52 errors planted at known lines, and an
  answer key with the correct mapping. Tests compare the tool's output against both, so the
  results above are measured, not estimated.

## Limits

- Format and business-rule checks only. It does not judge whether a diagnosis fits a
  procedure or whether values are true.
- Synthetic data only on the public demo. Real PHI would need an approved environment.
- Live Gemini behavior depends on the configured model and is not covered by offline tests.
