# AI Pipeline Troubleshooting Assistant

Upload an orders CSV, map its quantity and unit price columns and run the check. The app scans every readable record within the 2 MB and 10,000-row limits, lists cell errors with the starting CSV line, source column, entered value and expected rule, and identifies unmapped columns. Download the file check as JSON. File, mapping and parsing failures can prevent a complete scan. A batch with any error is never loaded. Checking the file requires no model or API key. Optional AI guidance uses sanitized evidence for the primary failure. The Investigate page also supports inventory. Repository fixtures are for development only.

## Repeat the portfolio demo

1. On **Investigate**, upload `examples/orders/Orders.csv`, choose the orders profile and confirm the mapping. Inspect the committed batch total. Run it again and look for `already_loaded: true`.
2. Replace the upload with `examples/orders/invalid_quantity.csv` and run the orders profile. Inspect the failure at physical line 3. Evidence-only mode works offline.
3. Select **RAG** and opt in. The app embeds the public runbooks, searches Chroma and asks Gemini for an explanation and a cited next check. Inspect the actual passages and token reserve. A missing or mismatched citation suppresses the model answer.
4. Select **Agent with read-only tools** and ask how many orders are stored. Inspect the tool trace. The session contains two orders after step 1. The model chooses whether to query. If it skips the query, no count has been verified by the agent.
5. Upload an orders export with renamed columns or upload an inventory CSV and select the inventory profile. Inventory validates SKU uniqueness, stock and an optional ISO date. Download the evidence or investigation JSON before closing the session.

For v2 AI, configure `GEMINI_API_KEY`, `GEMINI_MODEL`, and **`GEMINI_EMBEDDING_MODEL`** using model IDs available to your own Google project. Investigations call external APIs only after opt-in. Use synthetic uploads. The optional AI request includes a fixed question, approved runbook content, sanitized evidence and aggregate tool results. Source cell values and uploaded headers are excluded.

## Implementation and evaluation

| Capability | Implementation | How to inspect it |
| --- | --- | --- |
| Profile validation and transactional load | Pydantic, SQLite, parameterized SQL and integer cents | Run twice, compare batch totals, inspect rollback tests |
| Document search | Versioned Markdown sections, Google embeddings and a session-local Chroma index | Inspect ranked source IDs, passage text and distances |
| RAG and context window | LangChain prompts, Gemini structured output and reserved output budget | Review selected passages and oversize-context regression |
| Investigative agent | LangGraph model decisions, four approved read operations, up to three tool executions | Inspect the trace, model-call count and elapsed time |
| Evaluation | Streamlit AppTest, real SQLite and Chroma tests, mocked Google responses and labelled retrieval questions | Run the commands below |

```sh
python -m unittest discover -s tests -v
python -m evaluation.retrieval
python -m evaluation.scenarios
# Explicit live evaluation uses your Google embedding quota
python -m evaluation.retrieval --live
```

The offline keyword baseline retrieved the expected source in the top three for 15 of 20 questions. All 24 labelled pipeline scenarios produced their expected evidence. Use `python -m evaluation.scenarios --live` to generate a separate RAG and agent response for each scenario for manual factual review. This makes paid provider requests if billing applies. Live vector retrieval and generated-answer quality require separate evaluation with configured Google models. Citation checking validates source identity and the quoted next check. The free-text explanation still requires review. Context accounting uses a conservative UTF-8 byte allowance for the English prompt with a reserve for framing, structured output and the answer. It is not provider-reported token usage.

SQLite data and the rebuildable vector index are temporary and isolated by browser session. For rollback, revert the v2 merge on GitHub and redeploy the previous main revision. The following sections describe the classic entry points.

## Start the browser demo (Python 3.10–3.12)

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL printed in the terminal. Upload a synthetic CSV with the columns `quantity` and `unit_price`,
then confirm the mapping and run the pipeline to inspect and download its JSON report. No API key is needed. Linux/macOS: use `.venv/bin/python` instead.
The interface supports native light/dark themes. It clears old results when input changes.

## Command-line workflow (no external packages needed)

From the repository root:

```powershell
python -m orders_assistant run examples/orders/Orders.csv
python -m orders_assistant explain
python -m orders_assistant history
```

Expected sales for the current committed fixture: `222.50`. Run the broken fixture to inspect a failure:

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

## Classic orders CSV contract

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

Gemini may require quota/billing. The v1 classification was verified in the hosted demo. The v2 embedding and chat models require a separate live check. API references:
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
