# Business requirements document

**Product:** Claims Onboarding and Exception Management Platform, pilot v1.0
**Status:** Built and tested on synthetic data. Ready for a supervised pilot with synthetic files.
**Date:** 15 November 2026

## 1. Background

A health plan administration platform takes on new clients (health plans, TPAs, self-funded
employers) several times a year. Before go-live each client sends historical and current claims
from its own systems. The extract uses the client's column names, its quality is unknown, and the
work is done today with spreadsheets, e-mail and a shared folder.

The existing [claims onboarding assistant](../claims/README.md) proved the core checks on one file
for one user. It does not track clients, people, decisions, exceptions or resubmissions over time,
and nothing it produces is approved or auditable. This pilot adds that.

## 2. Problem statement

- **Rounds are slow and unmeasured.** Each "send, find problems, resend" round is handled by hand
  and nobody knows how many rounds a client needed or why.
- **Decisions are not traceable.** Which mapping was used, who approved it, which rules were in
  force and who signed off go-live are in e-mails, if anywhere.
- **Problems are tracked per file, not per client.** When a resubmission arrives, the team checks
  by hand which problems were fixed and which are new.
- **Go-live can be approved with known blockers** because nothing enforces the rule.
- **Loads can duplicate claims** when an export is retried after a failure.

## 3. Objectives

| # | Objective | How we will know |
| --- | --- | --- |
| O1 | Every go-live decision is backed by evidence anyone can check | Evidence package with SHA-256 manifest; audit chain verifies |
| O2 | No client goes live with an open blocker | Enforced by the readiness checks; tested (AC-2) |
| O3 | Each claim reaches the claims system exactly once | Idempotent batches and per-claim dedupe; tested (AC-3) |
| O4 | Rounds to acceptance and rework are measured, not guessed | Scorecards and portfolio KPIs from records |
| O5 | AI helps without being trusted blindly | AI only suggests or rewords; every check is deterministic; tested (AC-7) |

## 4. Scope

**In scope (pilot v1.0):** the 12 Priority 1 features and the Priority 2 items listed in the
[README](README.md), for CSV extracts up to 20 MB and 100,000 rows, with synthetic data.

**Out of scope:** real patient data; HIPAA compliance; X12 837/999/277CA/275, HL7 v2 and FHIR inputs;
several source files per client; configurable outbound integrations; e-mail delivery of letters;
single sign-on; multi-region deployment. See the [roadmap](roadmap.md).

## 5. Stakeholders and roles

| Role in the platform | Who | Can |
| --- | --- | --- |
| Administrator | Platform operations | Manage users and client access, run recovery, verify the audit chain, run failure simulations |
| Implementation analyst | Day-to-day owner of a client | Create clients, upload files, prepare mappings, propose rule changes, run validation, manage exceptions, write letters, export |
| Approver | Implementation lead or data governance | Approve mappings and rule changes, accept warnings with a note, approve or reject go-live |
| Client data contact | The client's data team | See only their client; upload files; see exceptions and findings; add notes; read released letters |

## 6. Functional requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| P1-01 | Keep each client's files, mapping, rules, exceptions and decisions in its own workspace; show all clients on one dashboard | Must |
| P1-02 | Store onboarding rules per client in plain language; changes create a new version that a second person approves before use | Must |
| P1-03 | Suggest mappings, let the analyst confirm or change them, send for approval, approve or return, and save approved mappings as reusable templates | Must |
| P1-04 | Check every row: required values, duplicates, formats, code lists, and cross-field rules (dates and amounts) | Must |
| P1-05 | Track each broken rule as an exception with severity, owner, status, notes and history; blockers cannot be waived | Must |
| P1-06 | Compare each file with the previous one: fixed, still open, new; reopen problems that come back | Must |
| P1-07 | Show a readiness checklist and stage for each client; never show ready while a blocker remains | Must |
| P1-08 | Require a human approval for mappings, rule changes and go-live, by someone other than the preparer | Must |
| P1-09 | Record every significant action in a tamper-evident audit trail | Must |
| P1-10 | Sign-in, role-based access, client separation and encryption of stored files and values | Must |
| P1-11 | Survive duplicate uploads, failed and interrupted runs and incomplete files without losing or duplicating data | Must |
| P1-12 | Export approved claims to a simulated downstream system in batches, resumable, never duplicating a claim | Must |
| P2-01 | Client scorecards from recorded data | Should |
| P2-02 | Plain-English issue explanations; optional AI rewording, checked, with a rule-based fallback | Should |
| P2-03 | Mapping confidence levels; abstain rather than guess; anything uncertain needs explicit confirmation | Should |
| P2-04 | Downloadable go-live evidence package | Should |
| P2-05 | Requirements and UAT traceability | Should |
| P2-06 | Runbooks for operational problems | Should |
| P2-07 | Implementation timeline per client | Should |
| P2-08 | Client communication centre: letters drafted by code, released by a person | Should |
| P2-09 | Processing performance dashboard | Should |

## 7. Acceptance criteria

| ID | Criterion | Evidence |
| --- | --- | --- |
| AC-1 | Ambiguous or missing mappings cannot be silently accepted | Checks C1, C2 |
| AC-2 | A client is never ready while blockers remain | Checks B4, B5, D4, E6 |
| AC-3 | No duplicate downstream records | Checks A4, E9, E10 |
| AC-4 | Approvals and configuration changes are traceable | Checks C8, F10 |
| AC-5 | Recovery from failures without data loss | Checks E3, E4, E7, E9 |
| AC-6 | No cross-client access | Checks F1, F2, F3 |
| AC-7 | AI failures do not bypass deterministic validation | Checks B9, E2 |

All 49 checks pass; see the [traceability matrix](traceability.md).

## 8. Non-functional requirements

| Area | Requirement | Pilot result |
| --- | --- | --- |
| Volume | 100,000 rows, 20 MB per file | Met: 100,000 rows validated in about 5 s |
| Data | Synthetic only | Enforced by policy and banners; not technically detectable |
| Availability | Single instance, restart-safe | Interrupted work recovered at start-up |
| Accessibility | Keyboard use, visible focus, status not by colour alone | Built in; not formally audited against WCAG |
| Browsers | Current Chrome, Edge, Firefox, Safari | Checked in headless Chromium only |

## 9. Assumptions and constraints

- One application process; background work runs in that process. Several workers need a job queue
  (see [architecture](architecture.md#limits-of-the-pilot-design)).
- The downstream claims system is simulated inside the platform's database.
- Letters are "released" inside the platform; no e-mail is sent.
- Gemini is optional. Without it every feature works; only AI rewording and AI mapping suggestions
  are unavailable.

## 10. Open decisions for the sponsor

1. Who holds the approver role for go-live, and does it need two approvers for large clients?
2. Retention period for files, findings and audit entries.
3. Whether a pilot with a real client's data is ever in scope; if so, a compliance assessment comes first.
