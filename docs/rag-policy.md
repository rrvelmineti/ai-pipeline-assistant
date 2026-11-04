# RAG policy for CSV review

- Python applies user-confirmed column rules and records findings before AI is offered. Retrieval never changes a rule or pass/fail.
- The user selects one finding. External requests contain only its allowlisted category and line number, a fixed question and public runbook excerpts. Raw cells and headers are excluded.
- The knowledge base consists of this repository's versioned public troubleshooting guides. Organization-specific document upload and authorization are not implemented.
- A next check must cite an included source for the selected category and match its full next-check passage. A forged, missing or irrelevant citation suppresses the answer.
- A grounded next check is not proof of the upstream cause. Free-form model explanations still require human review.
- Agent mode chooses between sanitized evidence and runbook search, at most once each, with at most three model calls. It cannot change data or query business orders.
- Opt-in is required. Model errors do not discard the file review.
- User-facing corrections are suggestions only. Never guess a missing value or automatically interpret an ambiguous date.

Tests exercise redaction, citation rejection and bounded reads. These checks do not certify general resistance to every possible malicious prompt or document. Live model quality requires separate evaluation.
