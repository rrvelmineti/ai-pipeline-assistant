# Architecture and evidence

The CSV passes ingestion, structural validation, and numeric validation before
its total is published. `Decimal` keeps cents exact. Every analyzed run includes
schema version, UUID, UTC timestamp, SHA-256 of the source bytes (when available),
status, stage, processed count, total, and an error or null.

The error has a stable code, CSV line, field, problem, next check and null underlying
cause. Raw cell text is deliberately absent. Invalid input is evidence of a contract
violation, not proof of an upstream outage or human mistake.

CLI: analyze -> commit SQLite history -> atomically replace latest JSON -> print.
JSON and SQLite are not a distributed transaction. A failed snapshot write is reported
with exit 2, and history still contains the run. Existing latest JSON must not be
assumed current after an exit 2. Each new record has a run ID and timestamp.

Browser: input -> temporary file -> analyze -> session result -> optional download.
The UI never reads other users' CLI history. A changed input clears the old result.

Gemini sees only static error metadata. It returns a constrained classification;
exact comparison with known evidence blocks invented causes. No returned code is
executed. If a provider fails, offline evidence still works. No automatic repair
capability is exposed. Correct a source only after confirming the business value,
then rerun and compare new records.

A future deployment needs authentication, upload controls at the proxy, per-user
storage, retention policy, monitoring and dependency maintenance. A GitHub push
alone does not deploy a Python service.
