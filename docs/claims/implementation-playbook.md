# Implementation playbook: onboarding a new client's claims data

How an implementation team would use this tool to take a new health insurance client from their
first claims extract to go-live. The client is a **hypothetical** example; the rules, sample file,
checks and results are the real ones in this repository.

## The engagement in one paragraph

A health plan has signed with the platform and must send its historical claims before go-live. Its
extract uses its own column names (`Clm_Nbr`, `DOS_From`, `Svc Code`) and has quality problems no one
has measured. Onboarding usually takes several rounds of "send file, find problems, resend", and each
round costs days. The goal is to make every round fast, exact and documented, so go-live happens on a
date both sides can trust.

## Stakeholders

| Who | Role | Responsible for |
| --- | --- | --- |
| Client data team | Data owner | Sending extracts, fixing problems at the source |
| Client project manager | Sponsor on the client side | Agreeing the rules and the go-live date |
| Implementation analyst | Day-to-day owner | Mapping approval, running checks, sending letters |
| Platform product team | Rule owner | Field definitions in `rules.txt` |
| Implementation consultant (me) | Delivery lead | Discovery, rules, rounds, go-live recommendation |

## 1. Discovery (week 1)

1. Which systems does the extract come from, and how many months of claims?
2. What does each client column mean? Get the data dictionary, not just the file.
3. Which fields can the client fix at the source, and which can't they?
4. Who on the client side signs off each resubmission?
5. Are any problems acceptable at go-live (warnings), and who decides?

Output: the rules agreed in plain language in [`rules.txt`](../../claims_onboarding/rules.txt),
with blockers and warnings marked. The client can read them, which avoids arguments later.

## 2. Each onboarding round (repeat until Ready)

```
client file ─> AI suggests mapping (headings only) ─> analyst approves ─> code checks every row
     ▲                                                                            │
     └──── client fixes at source <── client issue letter <── readiness decision ─┘
                                                  │
                             resubmission comparison: fixed / still open / new
```

1. **Map.** Name matching, plus Gemini if the client consents, suggests a mapping. The model sees
   headings only, never cell values. The analyst approves every field, and changes are logged.
2. **Check.** Code checks every row against the rules. The decision is Ready only with every
   required field mapped, the whole file scanned and zero blockers.
3. **Send back.** Download the **client issue letter**: problems grouped by rule, with the client's
   own column names, up to 5 example lines each and how to fix them. It goes out with the findings CSV.
   [Example from the sample file](sample-client-letter.md).
4. **Compare.** When the client resubmits, upload the previous JSON report. The comparison shows,
   rule by rule, what was **fixed**, **improved**, **unchanged**, **worse** or **new**. It flags a
   changed mapping or the same file sent twice, so the round count stays honest.

## 3. Go-live decision

| Condition | Source |
| --- | --- |
| Every required field mapped | Approved mapping |
| Every row scanned | Readiness report |
| Zero blockers | Readiness report |
| Warnings reviewed with the client | Client issue letter, "Please review" section |
| Mapping corrections understood | Correction log in the report |

The consultant recommends go-live; the client project manager signs off. The Markdown report and the
last comparison are the evidence.

## 4. Measuring the engagement

| Measure | Why it matters |
| --- | --- |
| Rounds to Ready | The main driver of onboarding time |
| Blockers per round | Shows whether the client is fixing at the source |
| New rule groups per round | Fixes that introduce new problems point to an export issue |
| Analyst mapping corrections | Tells the product team where name matching or AI suggestions fall short |

## 5. Handover

The client data team receives the agreed rules, the final readiness report and the last letter. For
monthly files after go-live, the same mapping and rules run as a recurring check, so problems are
caught before they reach production.
