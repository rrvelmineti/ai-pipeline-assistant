# Roadmap: Priority 3 and beyond

Pilot v1.0 covers CSV extracts from one source per client. These items were deliberately left out
and are listed in the order we would build them.

## 1. Production foundations (before any larger pilot)

| Item | Why |
| --- | --- |
| Job queue with leases (PostgreSQL `SKIP LOCKED` or Redis) | Run several workers safely; recovery by lease expiry instead of at start-up |
| Alembic migrations | Change the schema without rebuilding the database |
| Single sign-on and MFA through the organisation's identity provider; HttpOnly session cookies | Replace local passwords and browser-stored tokens |
| Object storage with a key management service | Replace local disk and an environment-variable key |
| Audit log shipped to write-once storage | Make the audit trail independent of database administrators |
| `pip-audit` and `npm audit` in CI | Catch vulnerable dependencies |

## 2. X12 inputs and acknowledgements

| Transaction | Use in onboarding |
| --- | --- |
| 837 (professional and institutional claims) | Accept the standard claim format as well as client CSV extracts; map loops and segments to target fields |
| 999 (implementation acknowledgement) | Report syntax problems back in the format trading partners expect |
| 277CA (claim acknowledgement) | Report claim-level acceptance and rejection |
| 275 with 277 request (claims attachments) | Prepare for the attachments standard below |

The parsing layer would produce the same target fields as the CSV mapping, so the rules,
exceptions, readiness and approvals stay unchanged.

## 3. Claims attachments

CMS published the final rule adopting standards for health care claims attachments in the Federal
Register on 24 March 2026 (FR Doc 2026-05676). It adopts the X12N 277 request for additional
information (006020X313) and the X12N 275 additional information to support a claim (006020X314),
the HL7 C-CDA implementation guide (volumes 1 and 2) and the HL7 Attachments implementation guide,
together with electronic signature standards. The rule took effect on 26 May 2026; covered entities
must comply by 26 May 2028. Standards for prior authorization attachments were not finalised in
this rule.

Sources: [Federal Register](https://www.govinfo.gov/content/pkg/FR-2026-03-24/html/2026-05676.htm),
[CMS fact sheet](https://www.cms.gov/files/document/nsg-attachments-final-rule-fact-sheet.pdf),
[HFMA summary](https://www.hfma.org/finance-and-business-strategy/cms-claims-attachments-rule-electronic-standards/).

The 2025 CAQH Index found medical plans at 98% fully electronic adoption for claim submission but 24%
for attachments, over 2023–2025 data
([CAQH executive report](https://index.caqh.org/hubfs/2025-26_Index_Dashboard/AskTheIndex_KnowledgeBase/2025%20CAQH%20Index%20Report%20Executive%20Report.pdf)).
Onboarding is a natural place to check that a client can send and receive attachments in the
adopted formats before the compliance date.

## 4. HL7 v2 and FHIR

Accept clinical and encounter data where clients send it (HL7 v2 messages, FHIR resources such as
`Claim`, `ExplanationOfBenefit` and `Coverage`), mapped to the same target fields with the same
confirmation and approval steps.

## 5. Several sources per client

Clients often send claims, eligibility and provider files from different systems. Each source would
get its own rules, mapping and exception register, with cross-source checks (every claim's member
in the eligibility file; every rendering NPI in the provider file) and one combined readiness view.

## 6. Configurable integrations

Replace the simulated downstream system with configurable connectors (SFTP, REST, message queue),
each with its own idempotency contract and a reconciliation report comparing what was sent with what
the receiving system holds.

## 7. Advanced analytics

Trends across clients once there are enough onboardings to compare: which rules fail most by
source system, how long each rule group takes to close, which kickoff choices predict first-pass
acceptance. Only after a measured baseline exists (see the [business case](business-case.md)).
