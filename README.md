# Orders Pipeline Assistant

Understand a failed orders export, inspect the evidence, and know what to check next.
A runnable first version of an applied AI engineering learning project. Python
validates and calculates; optional Gemini classifies a known failure under strict
checks. Neither the model nor the application guesses missing values or repairs data.

## Start the browser demo (Python 3.10–3.12)

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL printed in the terminal. Choose the successful or broken demo,
then **Run pipeline**. You can also upload a synthetic CSV and download its JSON
report. No API key is needed. Linux/macOS: use `.venv/bin/python` instead.
The interface supports native light/dark themes. It clears old results when input changes.

## Command-line workflow (no external packages needed)

From the repository root:

```powershell
python -m orders_assistant run examples/orders/Orders.csv
python -m orders_assistant explain
python -m orders_assistant history
```

Expected sales: `250.00`. Run the broken fixture to inspect a failure:

```powershell
python -m orders_assistant run examples/orders/invalid_quantity.csv
python -m orders_assistant explain
```

The run exits with code 1 for a recorded input failure, 0 for success, and 2 for
configuration/storage problems. `explain` reads the saved record; it never reruns
the CSV. Run again after correcting your input.

CLI outputs: `local_data/latest.json` and SQLite history in
`local_data/runs.sqlite3`, both ignored by Git. Use `--output` and `--database` to
choose other paths. The history is committed before replacing the latest snapshot;
if snapshot saving fails, the command exits 2 and the historical record remains.
A snapshot is replaced atomically. Keep one CLI writer per output path.

## CSV contract

```csv
quantity,unit_price
2,30
3,30
4,25
```

- UTF-8 (optional BOM), exactly these two headers in either order.
- Quantity: integer from 1 to 1,000,000. Price: 0 to 1,000,000, at most 2 decimal places.
- Whitespace around numeric cells is accepted. Currency symbols, exponent notation,
  negative values, missing fields, duplicate headers, and malformed CSV are rejected.
- Maximum 2 MB and 10,000 orders. Physical CSV line numbers include the header.
- Exact decimal arithmetic; totals are JSON strings such as `"250.00"`.
- All values must use one currency. No tax, discount, currency conversion, or refunds.
- Stop at the first error; failed totals remain `null`, even after earlier valid rows.

## Optional Gemini

Configure `GEMINI_API_KEY` and `GEMINI_MODEL` in your environment for the CLI using your own
currently available model ID. Do not commit keys. The application does not load
`.env` automatically. No key is needed for normal operation or CI.

```powershell
python -m orders_assistant explain --provider gemini
```

For the browser app, add `GEMINI_API_KEY` and `GEMINI_MODEL` as quoted,
top-level entries in Streamlit Settings > Secrets, outside any `[section]`.
The UI reads `st.secrets` directly, with environment variables as a fallback.
Leading/trailing whitespace is trimmed, and model IDs with or without the
`models/` prefix are accepted. Use the exact API model ID from AI Studio's
Get code; display names with spaces are not valid model IDs. Save and reboot
after changing secrets. Never commit `.streamlit/secrets.toml`.

In the UI, explicitly allow the request and click the Gemini button. Only the
static error description and stage are sent, never uploaded cells or file paths.
The returned code, stage and null underlying cause must match recorded evidence.
Unsupported claims, malformed responses, network errors, and incomplete responses
are rejected; the original record remains unchanged. Wording is rendered from
trusted templates. This is constrained classification, not a general root-cause
agent. An upstream cause cannot be established from a bad cell alone.

Gemini may require quota/billing. Live requests are optional and have **not** been
verified with a real key in this implementation. API references:
[authentication](https://ai.google.dev/api) and
[generateContent](https://ai.google.dev/api/generate-content).

## Tests

```powershell
python -m pip install -r requirements.txt
python -m compileall -q orders_assistant app.py examples/orders tests
python -m unittest discover -s tests -v
```

Tests cover money arithmetic, invalid inputs, file/row limits, error evidence,
CLI exit codes, history, snapshot replacement, Gemini response rejection/redaction,
timeouts, and the UI demo flow. All AI responses are mocked. GitHub Actions runs
on Linux (Python 3.10/3.12) and Windows (3.12).

## Files and learning route

| File | Responsibility |
| --- | --- |
| `orders_assistant/core.py` | CSV validation and evidence |
| `orders_assistant/storage.py` | JSON snapshot and SQLite history |
| `orders_assistant/explain.py` | Deterministic explanation and optional Gemini verification |
| `orders_assistant/__main__.py` | CLI commands and exit codes |
| `app.py` | Browser demo |
| `examples/orders/` | Original beginner exercise and synthetic fixtures |
| `tests/` | Offline regression checks |

Start with [the learning guide](docs/learning.md), then [architecture](docs/architecture.md).
The original beginner exercise stays separate and intentionally simpler; the new
application uses the package above. [Git workflow](docs/git-workflow.md).

## Boundaries

This is a local learning/demo application, not a production deployment. The UI
keeps results in session memory, not in the CLI database. Temporary upload copies
are removed after analysis. Closing a session can discard its result. CLI evidence
is retained until you remove your own `local_data` files. No customer profiles or
raw order cells are stored in evidence. Do not upload sensitive business data to
a shared demo. Public hosting, authentication, monitoring, automatic repairs,
and arbitrary pipeline integrations are outside this first version.
