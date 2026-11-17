# Claims Onboarding and Exception Management Platform (pilot v1.0)

A web platform an implementation team uses to take a new health plan client's claims extract from
first upload to an approved go-live and a clean load into the claims system. It grows the
[claims onboarding assistant](../claims/README.md) from a single-user page into a multi-client
service with logins, roles, an exception register, resubmission tracking, approvals, an audit
trail and a downstream export.

> **Synthetic data only.** This pilot is not HIPAA-compliant and has not been assessed against
> HIPAA or any other regulation. Never upload real patient records or confidential client files.

## What it does

| Plan requirement | How the pilot meets it |
| --- | --- |
| Client onboarding workspace | One workspace per client, a portfolio dashboard and a go-live stage track for each client |
| Configurable, versioned rules | Plain-language rules per client; every change is a new version that a second person approves |
| Mapping management | Suggestions with confidence levels, analyst confirmation, approver sign-off, reusable templates |
| Advanced validation | Every row checked by code: required values, duplicates, formats, code lists, cross-field dates and amounts |
| Exception management | One exception per broken rule, with severity, owner, status, notes and full history |
| Resubmission tracking | Each file compared with the previous one: fixed, still open, new; problems that come back reopen |
| Readiness dashboard | Eight checks; never ready while a blocker remains |
| Human approval | Four-eyes on mappings, rule changes and go-live; nobody approves their own work |
| Audit trail | Append-only, hash-chained, verifiable end to end |
| Basic security | Sign-in with lockout, four roles, client separation (404 for other clients), encryption at rest |
| Reliable processing | Duplicate uploads ignored, failed and interrupted runs retried without loss, incomplete files never ready |
| Downstream export | Batches with idempotency keys; each claim loaded once, even across retries and resubmissions |

Priority 2 items included: client scorecards, AI issue explanations (checked, with a rule-based
fallback), mapping confidence and abstention, the go-live evidence package, the traceability
matrix, runbooks, the implementation timeline, the client communication centre and the processing
dashboard. Priority 3 is in the [roadmap](roadmap.md).

## Results (measured, 15 November 2026)

| Measure | Result | Source |
| --- | --- | --- |
| Scenario checks A–F | 49 of 49 passed on SQLite and on PostgreSQL 16 | [traceability.md](traceability.md) |
| Planted-error recall, 2,000-row file | 52 of 52 found at the right line, 0 false alarms | Scenario B, check B2 |
| 100,000-row file | Validated in 5.1–5.6 s; exported in about 4 s (SQLite) and 8 s (PostgreSQL), every claim once | [traceability.md](traceability.md#performance-the-largest-accepted-file) |
| Automated tests | 41 platform tests (Python) and 8 interface tests, plus the existing 78 | `tests/test_platform_*.py`, `claims_platform_web/src/__tests__` |

Timings are from one run in a cloud container, single process. They show the order of magnitude,
not a capacity guarantee. No time saving against the manual process is claimed: no manual
baseline has been measured yet ([how to measure one](business-case.md#measuring-the-manual-baseline)).

## Run it

On Render's free tier: [deploy-render.md](deploy-render.md) (one click with `render.yaml`).

Locally:

Python 3.10+ and Node 20+.

```bash
python -m pip install -r requirements.txt
cd claims_platform_web && npm ci && npm run build && cd ..

export CLAIMS_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export CLAIMS_DEMO_PASSWORD='Choose-A-Demo-Pass-1'
python -m claims_platform.cli seed-demo      # loads scenarios A–F into a new local database
python -m claims_platform.cli serve          # http://127.0.0.1:8000
```

Sign in as `ana` (analyst), `priya` (approver), `birch.contact` (client contact) or `admin`, all with
the demo password. Or run the whole stack with PostgreSQL: `docker compose up` (see
[configuration](configuration.md)). API reference: `/api/docs` on a running server.

Check everything:

```bash
python -m unittest discover -s tests -v
python -m evaluation.platform_scenarios --performance      # add --save to refresh the results and traceability
cd claims_platform_web && npm test
```

## Documents

| Document | For |
| --- | --- |
| [Business requirements](brd.md) | Sponsor, product owner |
| [Process maps: current and future state](process-maps.md) | Implementation lead, operations |
| [Architecture](architecture.md) | Engineering, security review |
| [Configuration](configuration.md) | Administrators, deployment |
| [Deploy to Render](deploy-render.md) | Hosting the demo on Render's free tier |
| [Security and risk assessment](security-and-risk.md) | Security, compliance |
| [Runbooks](runbooks.md) | Support and operations |
| [UAT report](uat-report.md) and [traceability matrix](traceability.md) | Testers, approvers |
| [Business case and KPI method](business-case.md) | Sponsor, finance |
| [Handover playbook](handover-playbook.md) | The team that runs onboarding |
| [Demo script](demo.md) | Anyone presenting the pilot |
| [Roadmap](roadmap.md) | Priority 3: X12, HL7 FHIR, attachments |
