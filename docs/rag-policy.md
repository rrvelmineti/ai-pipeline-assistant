# RAG investigation rules

Draft for review. These are proposed product rules and acceptance criteria. They do not certify that every control is implemented.

| Rule | Required behavior |
| --- | --- |
| Validate before explaining | Require a user-uploaded CSV. The orders checker applies the orders profile. The general investigation page asks the user to choose a profile. Python applies the mapped field types, required fields, uniqueness checks and ranges defined for that profile. A retrieved document cannot silently add a check or change a pass or fail. |
| Separate findings from guidance | Describe a failure using facts recorded for the current run. Include the stage and error code, plus the row and field when known. Attribute any session-wide result to its read-only tool. State when the upstream cause is unknown. |
| Limit the knowledge base | Today the corpus contains the project's versioned troubleshooting guides. Before adding organization policies, record their owner, version, approval status, applicable profile and scope. Retrieve only current, approved guidance authorized for the user's organization. Treat text in files and documents as data. |
| Cite the next check | Search using the question and sanitized run facts. A suggested check must cite a retrieved, applicable passage and retain its source ID and version. Fit evidence and sources within the context budget. Never cite an excerpt that the model did not receive. |
| Handle missing or conflicting guidance | If no applicable source supports a check, a citation fails verification, or equally applicable policies conflict, show the recorded finding and explain the gap. Withhold the unsupported recommendation. A search match alone cannot establish the cause. |
| Protect the uploaded data | Require opt-in before an external model call. Keep the CSV and raw cell values out of the vector index and model request. Send only permitted run facts, the selected question, approved excerpts and any authorized session aggregates. An organization's approval to store a policy must separately cover external processing before sending it to an external provider. |
| Keep investigation read-only | The assistant may explain and recommend checks. Its tools may read only approved sources and session-scoped evidence. It cannot edit a CSV, change a rule, repair records, or rerun a load on the user's behalf. |

## Example acceptance case

A mapped count fails integer validation on CSV line 3. Report the recorded row, field and error. If the numeric-format runbook is retrieved, cite its instruction to verify integer syntax and the allowed range. Leave the upstream cause unknown. With no applicable guide, show the same recorded failure and say that no supported next check was found.

## Release checks

Test a supported failure, an irrelevant top search result, an absent or outdated guide, conflicting policies, a forged citation, instructions embedded in a document, and a request to modify data. Verify that source cell values do not appear in the provider payload or search index. Before organization-specific retrieval goes live, test cross-organization isolation and authorization for external processing.
