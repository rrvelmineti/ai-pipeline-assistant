# Handover playbook: running a client onboarding on the platform

For the implementation team taking over day-to-day use. It follows the
[earlier playbook](../claims/implementation-playbook.md), now with the platform doing the tracking.

## Roles

| Platform role | Usually | Responsible for |
| --- | --- | --- |
| Implementation analyst | Onboarding analyst | Mapping, validation, exceptions, letters, export |
| Approver | Implementation lead or data governance | Approving mappings, rule changes, accepted warnings and go-live |
| Client data contact | Client's data team | Sending files, fixing data at the source, answering on exceptions |
| Administrator | Platform operations | Users, access, recovery, audit checks |

**RACI for the key decisions**

| Decision | Analyst | Approver | Client contact | Admin |
| --- | --- | --- | --- | --- |
| Column mapping | R | A | C | |
| Rule change for a client | R | A | C | |
| Accept a warning | C | A, R | C | |
| Go-live | C | A, R | I | |
| User access | I | I | | A, R |

## The engagement, step by step

1. **Set up (day 1).** The administrator creates user accounts and gives the analyst, the approver
   and the client contact access to the client. The analyst creates the client with its go-live
   target. The timeline appears with seven steps.
2. **Kickoff.** Agree with the client: the extract layout, date formats, which fields they can and
   cannot fix, and who sends files. If their dates or codes differ from the baseline rules, the analyst
   proposes a rule change with the reason, and the approver accepts it.
3. **First file.** The client contact (or the analyst) uploads it. The analyst asks for mapping
   suggestions, confirms every field that is not a clear match, adds a note, and sends it for approval.
   The approver checks it against the client's data dictionary and approves or returns it.
4. **Validate.** The analyst validates the file. Exceptions open automatically, one per broken rule.
5. **Work the exceptions.** Assign owners. Move to "In progress" when the client is working on one.
   For warnings the client cannot fix, the approver may accept them with a written reason. Blockers
   can only be cleared by a corrected file.
6. **Write to the client.** Draft the issue letter, read it, release it. It uses the client's column
   names, gives example lines and says how to fix each problem.
7. **Resubmissions.** Each new file is validated the same way. The resubmission tracker shows what was
   fixed, what is still open and what is new; problems that come back reopen with their history.
   Send the resubmission summary with each round.
8. **Go-live.** When all eight readiness checks pass, the approver approves with a comment. They
   cannot be the person who prepared the mapping or ran the validation.
9. **Export.** The analyst starts the export. If it stops, resume it; nothing is loaded twice.
10. **Close.** Download the evidence package and store it with the client's contract records.

## Weekly cadence during onboarding

| When | Who | What |
| --- | --- | --- |
| Monday | Analyst | Review the dashboard: stage, open blockers, timeline dates |
| After each file | Analyst | Validate, update exceptions, release the letter the same day |
| Weekly call | Analyst, client contact, approver | Walk the open exceptions by owner; agree the next file date |
| Before go-live | Approver | Read the readiness checklist and the latest letter; approve or reject with a reason |

## Good practice

- Never edit a client's file to make it pass. Ask for a corrected file; the history depends on it.
- Write the reason in every note, return and approval. The audit trail keeps it forever.
- Use templates for clients on the same vendor layout, but still confirm the mapping each time.
- If Gemini is used, treat its suggestions as a colleague's guess: it sees headings only.
- Keep the pilot synthetic. If anyone uploads real data, stop, tell the administrator, and follow the
  incident process.

## Where to look when something goes wrong

The [runbooks](runbooks.md) cover failed or interrupted runs, downstream outages, duplicate and
incomplete files, lockouts, audit check failures, key rotation and backups.
