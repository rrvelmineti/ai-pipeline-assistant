# Current product contract

The browser app has one purpose: review a user-uploaded CSV for data-type, format, missing-value and row-structure issues under confirmed column rules. No examples are preloaded, no totals are calculated, no business records are loaded, and no user-defined numeric range box is shown.

Headings and sampled values propose types. A person confirms their meaning; every readable record is then validated deterministically. Date columns use one selected format and real calendar dates. An unclear format requires an explicit choice. Unknown columns can remain unchecked but must be identified in coverage.

Python finds issues independently of AI. Findings identify physical line, column, original value and expected format. Suggestions are proposals for review, never changes. A blank value is not zero; a valid-looking value is not necessarily true.

Success wording is limited to the checks actually performed. Incomplete parsing, unreviewed columns and retained-detail limits are visible. No UI message certifies an entire dataset as factually clean.

RAG follows validation, using versioned public CSV guidance. The optional agent can read sanitized evidence and retrieve documents; it cannot write data or perform business sums. No uploaded header or cell is sent to the embedding or chat provider. The report download may contain entered values.

This contract supersedes the browser portions of earlier orders/inventory and transactional-load plans. Legacy modules and offline scenario tests remain available as learning exercises.
