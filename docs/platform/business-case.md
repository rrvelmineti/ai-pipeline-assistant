# Business case and KPI method

## The case in one paragraph

Client onboarding is where a claims platform's relationship with a new client starts, and where it
most often slips: go-live dates move because each round of "send file, find problems, resend" is
slow, untracked and argued from memory. The pilot makes every round exact, documented and measured,
and it enforces the controls (four-eyes, no go-live with blockers, no duplicate loads) that an audit
or a client escalation will ask about. It does this with deterministic checks; AI is used only
where a person reviews the result.

## What the pilot does and does not claim

**It claims** what the tests show: every row is checked; the 52 planted errors in the sample are all
found with no false alarms; a client cannot be approved with a blocker open; no claim is loaded
twice; every decision is in a verifiable audit trail.

**It does not claim** any time, cost or effort saving. No manual baseline has been measured, so any
percentage would be invented. The platform records the data needed to measure the effect honestly
once a baseline exists.

## Industry context

Electronic claim submission is close to universal, but the surrounding documentation is not. The
2025 CAQH Index reports that medical plans saw 98% fully electronic adoption for claim submission
but 24% for claim attachments, over 2023–2025 data
([CAQH](https://index.caqh.org/hubfs/2025-26_Index_Dashboard/AskTheIndex_KnowledgeBase/2025%20CAQH%20Index%20Report%20Executive%20Report.pdf);
[AJMC](https://www.ajmc.com/view/caqh-index-finds-20-billion-in-cost-savings-opportunities)).
In March 2026 CMS finalised standards for electronic health care claims attachments, with
compliance required by May 2028 ([CMS fact sheet](https://www.cms.gov/files/document/nsg-attachments-final-rule-fact-sheet.pdf)).
These figures describe the industry, not this pilot's effect; they explain why the
[roadmap](roadmap.md) moves towards X12 and attachments.

## KPIs and how each is measured

All are computed by the platform from its own records (`GET /api/reports/portfolio` and each
client's scorecard) and shown with the number of clients or files they are based on.

| KPI | Definition | Why it matters |
| --- | --- | --- |
| Rounds to acceptance | Submissions up to and including the first Ready file | The main driver of onboarding duration |
| First-pass acceptance rate | Clients whose first validated file was Ready ÷ clients with a validated file | Shows how well the data request and rules are explained up front |
| Rework rate | Validated files that were Not ready ÷ all validated files | Each Not ready file is a round of work for both sides |
| Median time to resolve an exception | From the run that opened a rule group to the run that no longer contained it | How quickly problems close |
| Exceptions that came back | Rule groups reopened after being resolved | Signals fixes that did not hold at the source |
| Validation accuracy | Planted errors found, missed and false alarms on labelled synthetic files | Trust in the checks; measured offline (`evaluation.platform_scenarios`) |
| Processing reliability | Runs completed on first attempt; exports completed; batch retries | Operational stability |
| Days in onboarding | Client creation to the completed export (or today) | The outcome the sponsor cares about |

The pilot's own figures come from synthetic scenarios built to exercise failures, so they say
nothing about real clients. For example, the 54.5% rework rate in the pilot run is high because the
scenarios deliberately send bad files.

## Measuring the manual baseline

Do this **before** claiming any improvement, with the same team and comparable clients.

1. **Choose 3 to 5 recent onboardings** done the manual way, of similar size and complexity to the
   ones planned for the platform.
2. **Reconstruct per client** from e-mail, tickets and the shared folder: the number of files the client
   sent until acceptance (rounds); the date of the first file and of go-live; the problems reported
   in each round, grouped by rule; any duplicate or failed loads.
3. **Time-and-motion for current work:** for the next manual round, the analyst logs the minutes spent
   on mapping, checking, writing to the client and comparing with the previous file. Two rounds per
   analyst is enough to see the order of magnitude.
4. **Record the baseline** in a table with the same definitions as the KPIs above, plus analyst
   minutes per round. Note where reconstruction was uncertain.
5. **Compare like with like.** After 3 to 5 platform onboardings, compare rounds to acceptance, rework
   rate, days in onboarding and analyst minutes per round. Report the numbers, the sample sizes and
   the differences between the client groups. With samples this small, describe the results; do not
   claim statistical significance.

## Costs to run the pilot

| Item | Pilot | Production estimate needed |
| --- | --- | --- |
| Hosting | One small VM or container and a PostgreSQL instance | Sized after a load test with real volumes |
| Gemini | Optional; only on request, headings and counts only | Usage-based; can be left off |
| People | An analyst and an approver per client; an administrator part-time | Same roles, more clients |
| Before real data | Compliance assessment, penetration test, identity provider integration | Required, not optional |

## Recommendation

Run a supervised pilot with synthetic files that mirror two or three real client layouts, measure
the manual baseline in parallel, and decide on a real-data pilot only after the compliance work in
the [security assessment](security-and-risk.md#known-gaps-accepted-for-the-pilot).
