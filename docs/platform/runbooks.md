# Runbooks

Each runbook says how to recognise the problem, what to do, and how to confirm it is fixed.
Commands run from the repository root with the same environment variables as the server.

## A validation run failed

**You see:** a red "Failed" status on **Validation and exceptions**, with the reason; audit entry `run.failed`.

1. Read the reason on the run. "Stored data could not be decrypted" means the encryption key changed: see
   [rotate the encryption key](#rotate-the-encryption-key). Anything else is usually temporary
   (database unavailable, disk full).
2. Fix the cause, then press **Retry run** (or `POST /api/runs/{id}/retry`).
3. **Confirm:** the run shows Completed with the expected row count; the attempts count went up by one.

Nothing from a failed attempt is saved, so a retry cannot double-count findings or exceptions.

## A run or export was interrupted (server restart, crash, deploy)

**You see:** a run marked "Interrupted", or an export marked "Failed" with "the service restarted".

1. Nothing to clean up: recovery runs automatically when the server starts. To run it by hand:
   `python -m claims_platform.cli recover` (prints how many runs and exports it marked).
2. Press **Retry run**, or **Resume from batch N** for an export.
3. **Confirm:** the run completes with the full row count; the export completes with
   `records loaded` equal to the file's claim count and the downstream count not above it.

Only one server process may run at a time in the pilot; a second process would mark the first's
work as interrupted. See [architecture](architecture.md#limits-of-the-pilot-design).

## The downstream claims system is unavailable

**You see:** export Failed: "Batch N of M failed after 3 attempts"; audit entry `export.failed`.

1. Confirm the downstream system is back. In the pilot it is simulated; an administrator may have
   left a simulated outage on: clear it with `PUT /api/admin/simulation` and body `{}`.
2. Press **Resume from batch N**. Batches already delivered are not sent again; a batch that was
   delivered but not acknowledged is recognised by its key and not loaded twice.
3. **Confirm:** status Completed; on the administrator's downstream summary
   (`GET /api/admin/downstream/{client_id}`) `records` equals `distinct_claim_ids`.

## The client sent the same file twice

Nothing to do. If the bytes match the latest submission, the upload is ignored and the person is
told which submission it matches (`submission.duplicate_ignored` in the audit trail). A file that
matches an older submission, sent after a newer one, is accepted as a real resubmission.

## The file is incomplete or unreadable

**You see:** "File not read to the end" on the run, an exception "file must be read completely", or
a "correct number of fields" blocker on one row.

1. Download the findings, or write the issue letter: it names the problem and the line.
2. Ask the client to resend the whole file. Do not edit the client's file yourself.
3. **Confirm:** after the resend validates, the file-level exception shows Resolved. Exceptions are
   never resolved by a scan that stopped early.

## A user is locked out

**You see:** "Too many failed sign-ins" for a user; audit entries `login.failed` then `user.locked`.

1. Confirm with the user that the attempts were theirs. If not, treat it as a security incident:
   disable the account (`PATCH /api/users/{id}` with `{"active": false}`) and review the audit trail.
2. Otherwise unlock: `PATCH /api/users/{id}` with `{"unlock": true}`, or wait 15 minutes.
3. **Confirm:** the user signs in; `login.succeeded` appears in the audit trail.

## The audit chain check fails

**You see:** `python -m claims_platform.cli verify-audit` exits with an error, or `GET /api/audit/verify`
returns `ok: false` with `first_bad_id`.

1. Treat as a security incident. Stop the service and take a copy of the database and file store.
2. The entry at `first_bad_id` (or the end of the log, if entries were removed) was edited after it
   was written. Compare with backups to find what changed.
3. Do not "repair" the chain: record the incident, its scope and the restore decision.

## Rotate the encryption key

1. Generate a new key. Set `CLAIMS_ENCRYPTION_KEY=NEW,OLD` (new first, comma, old) and restart.
   New data uses the new key; old data stays readable.
2. Run `python -m claims_platform.cli rotate-key`. It re-encrypts every stored file, finding value,
   letter and downstream payload under the new key and prints the counts. It is safe to run twice.
3. Set `CLAIMS_ENCRYPTION_KEY=NEW` and restart.
4. **Confirm:** open a client's findings and a letter; download an evidence package. If anything says
   "could not be decrypted", put `OLD` back in the list and run step 2 again.

## Back up and restore

- **Back up together:** the database, the file store (`CLAIMS_STORAGE_DIR`) and the encryption key,
  each to a different place. Files without the key cannot be read; the key without the files is useless.
- **Restore:** stop the service, restore database and files from the same point in time, set the key,
  start the service, run `verify-audit`, then open one client of each stage to check.

## A client says a letter or exception is wrong

1. Open the exception: its history shows each file it was seen in and every change.
2. Download the findings for that run: each line, value and rule is there.
3. If the rule itself is wrong for this client, propose a rule change with the reason; an approver
   accepts it; validate the file again. The old result stays in the history.
