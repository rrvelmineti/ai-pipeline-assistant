# Configuration

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAIMS_DATABASE_URL` | `sqlite:///local_data/claims_platform.db` | SQLAlchemy URL. Use PostgreSQL outside a laptop: `postgresql+psycopg://user:pass@host:5432/claims` |
| `CLAIMS_ENCRYPTION_KEY` | none | Fernet key for files and sensitive values. **Required** unless `CLAIMS_ENV=development` |
| `CLAIMS_ENV` | `development` | Anything else turns off the development key file and requires `CLAIMS_ENCRYPTION_KEY` |
| `CLAIMS_STORAGE_DIR` | `local_data/platform_files` | Where encrypted uploads are kept |
| `CLAIMS_SESSION_HOURS` | `8` | Session lifetime |
| `CLAIMS_LOCKOUT_ATTEMPTS` | `5` | Failed sign-ins before a lock |
| `CLAIMS_LOCKOUT_MINUTES` | `15` | Lock duration |
| `CLAIMS_EXPORT_BATCH_SIZE` | `500` | Claims per downstream batch |
| `CLAIMS_EXPORT_BATCH_ATTEMPTS` | `3` | Tries per batch before an export is marked failed |
| `CLAIMS_SIMULATION` | `1` | Enables the fault-injection endpoint used by scenario E. **Set to `0` in any shared environment** (the Docker image does) |
| `CLAIMS_WEB_DIST` | `claims_platform_web/dist` | Built interface to serve |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | none | Optional. Without them, AI mapping suggestions and AI rewording are unavailable and everything else works |
| `CLAIMS_ADMIN_PASSWORD` | none | Used by `cli create-admin` when not run interactively |
| `CLAIMS_DEMO_PASSWORD` | random | Password for every demo user created by `cli seed-demo` |

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep it in a secret store. Losing it makes every stored file and finding value unreadable; see
[key rotation](runbooks.md#rotate-the-encryption-key).

## First start

```bash
python -m claims_platform.cli init                # create tables
python -m claims_platform.cli create-admin admin  # asks for a password (12+ characters, not only letters or digits)
python -m claims_platform.cli serve --host 0.0.0.0 --port 8000
```

Then, signed in as the administrator, create users (`POST /api/users`), and give each user access to
their clients (`POST /api/clients/{id}/access`). Analysts who create a client get access
automatically. The API reference is at `/api/docs`.

## Docker with PostgreSQL

`docker-compose.yml` runs the platform and PostgreSQL 16. Put `CLAIMS_ENCRYPTION_KEY` and
`POSTGRES_PASSWORD` in a `.env` file next to it, then `docker compose up --build`. The image runs one
worker as a non-root user, with fault injection off. The port is bound to 127.0.0.1; put a TLS
proxy in front for anything beyond a laptop.

> The image definition was written for this pilot but not built in the development environment,
> because Docker Hub was not reachable from it. The steps it runs (npm build, pip install,
> uvicorn) were each tested directly. Build it once before relying on it.

## Onboarding rules

Each client starts with the platform baseline, [`claims_onboarding/rules.txt`](../../claims_onboarding/rules.txt),
as version 1. An analyst proposes a change under **Data mapping > Onboarding rules**; an approver
other than the author accepts it. Only the latest approved version is used, and a change makes
earlier validations stale until the file is validated again.

One field per line: `field | what it means | rules separated by commas`.

| Rule | Meaning |
| --- | --- |
| `required` | Must be mapped, and every row needs a value |
| `unique` | No two rows share a value |
| `number`, `whole number`, `not negative` | Numeric checks |
| `exactly N digits`, `exactly N characters` | Length checks |
| `date YYYY-MM-DD` | Also `DD/MM/YYYY`, `MM/DD/YYYY`, `DD-MM-YYYY`, `MM-DD-YYYY`, `YYYY/MM/DD` |
| `not in the future` | Not after the run date |
| `not before OTHER_FIELD` | Cross-field date check |
| `not greater than OTHER_FIELD` | Cross-field amount check |
| `ICD-10 format` | Shape of an ICD-10-CM code |
| `one of A / B / C` | Allowed values |
| `(warning)` after a rule | Report without blocking; a warning must still be fixed or accepted with a note before go-live |

An unrecognised phrase is refused with its line number, never ignored.

## Mapping confidence levels

| Level | When | Needs a person to confirm |
| --- | --- | --- |
| Clear match | Heading matches the field closely and nothing else comes close, or the file has the same layout as a saved template | No |
| Likely match | Good match, or suggested by Gemini where name matching had none | Yes |
| Weak match | Partial word overlap | Yes |
| Ambiguous | Another heading scores within 0.15 of the chosen one, or Gemini and name matching disagree | Yes |
| No match | Nothing scored 0.5 or more: the platform abstains rather than guess | Yes (choose a column or confirm "not provided") |

A field the analyst changes counts as an explicit decision. Approval then needs someone other
than the analyst who sent it.

## Roles

| Action | Admin | Analyst | Approver | Client contact |
| --- | --- | --- | --- | --- |
| Manage users and access, recovery, audit check | Yes | | | |
| Create clients, upload, prepare mappings, propose rules, validate, export | Yes | Yes | | Upload only |
| Approve mappings and rules, accept warnings, approve go-live | Yes* | | Yes* | |
| Assign and update exceptions | Yes | Yes | Yes | Notes only |
| Draft letters | Yes | Yes | | |
| Release letters | Yes | Yes | Yes | |
| Read released letters, own client's exceptions and findings | Yes | Yes | Yes | Yes |
| Evidence, audit trail, scorecards, KPIs | Yes | Yes | Yes | |

\* Never for work they prepared themselves.
