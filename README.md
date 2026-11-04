# Query Desk · CSV data review

Upload a CSV, confirm suggested column types, and review the values that do not fit. This is a **validation-only** application: it does not calculate sales or product totals, load business rows into a database, or automatically change values. Both browser pages require an upload. No default dataset or sample selector is shown.

## Use the application

1. Upload a UTF-8 CSV with a header. The app supports up to **20 MB, 100,000 data records and 200 columns**.
2. Review the suggested type for each column. Suggestions use headings and up to 500 records; they can be wrong. Confirm or change them before running.
3. Choose one format for every date column. Ambiguous day/month formats require a choice. Decide whether blanks are allowed.
4. Select **Confirm types and review CSV**.
5. Review the issue table and download the JSON report. Verify suggestions against your source; then edit and re-upload the original file.

## What is checked

| Confirmed type | Accepted format |
| --- | --- |
| Whole number | Digits only; zero is allowed, decimals and negative numbers are not |
| Integer | Digits with an optional plus or minus sign; no decimal point |
| Number | A plain number with optional sign and decimal point; no currency symbols, grouping commas, scientific notation, NaN or infinity |
| Text | Contains at least one Unicode letter; digits alongside letters are allowed |
| Identifier | Any nonempty string; leading zeros and alphanumeric codes are preserved |
| Date | A valid calendar date matching one selected, zero-padded format across the column |
| Boolean | true or false, case insensitive |
| Not checked | Explicitly excluded and listed in coverage; the app cannot call all columns checked |

Blank cells and whitespace-only cells are flagged unless **Allow blanks** is selected. Surrounding whitespace is ignored when testing types; original values stay unchanged. Literal strings such as NA are not silently treated as blanks. Text checks cannot detect all irrelevant words, misspellings or factually incorrect names. Identifier validation is intentionally permissive.

Headings such as quantity, unit price, name, postal code and date suggest types. Unknown headings may receive a sample-based suggestion or remain unchecked. **No configurable minimum/maximum controls** are shown. New numeric validation has no business range limits or decimal-place caps; resource limits still apply.

For each finding the report gives the starting physical CSV line, column, entered value, expected format and suggestion. English number words zero through twelve can produce a reviewable number suggestion. Missing values are never guessed. Mixed date formats are flagged; ambiguous values are never silently swapped or converted.

Every readable record is scanned within the limits. Wrong field counts are reported and scanning continues. Malformed quotes, encoding errors or parser field-size limits can prevent scanning the rest, in which case the result is **incomplete**. Counts cover only scanned records. At most 5,000 issue details are retained while all scanned issues are counted. Displayed/exported values are capped at 500 characters and marked when truncated. Split larger files to inspect remaining details.

“No data type or format issues found” means the confirmed checks passed, not that every value is true or the dataset meets all business rules. Skipped columns prevent an all-columns success message.

## Optional RAG and agent guidance

After a finding is recorded, expand **Optional AI guidance**, select an issue and opt in. Configure these top-level entries in Streamlit Secrets using model IDs available in your project: GEMINI_API_KEY, GEMINI_MODEL and GEMINI_EMBEDDING_MODEL.

LangChain/Gemini generates guidance from retrieved public runbooks. Google embeddings and Chroma provide vector retrieval. A cited next check is accepted only when its ID, issue category and exact passage match a supplied source. Free-text explanations still require review and cannot establish the upstream cause.

Agent mode uses LangGraph to choose up to two read-only tools: recorded sanitized evidence and runbook search. It makes at most three model calls. There are no business-table tools, repairs, sums or database loads in this browser workflow. The context budget preserves evidence and reserves space for output; its conservative byte accounting is not provider-reported token usage.

Only the generic issue category, line number, fixed question, public passages and sanitized read results are sent externally. **CSV cells, headings and the original file are excluded.** The vector index contains public runbooks only. API quota or configuration failures leave the deterministic review available. Live provider behavior needs a separate test with configured models.

## Privacy and limitations

Use synthetic files on the public demo. Uploads are processed on the server. Reports and the temporary rebuildable vector index are scoped to the browser session; download the report before leaving. Reports contain the entered values shown in findings. No user accounts are created by this app.

The application does not infer organization-specific business policies, verify data truth, check cross-field totals or automatically fix data. Dates support YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, MM-DD-YYYY and YYYY/MM/DD. Timestamps, alternate encodings and locale-specific numeric formats need an explicit future extension.

## Run locally and test

Python 3.10–3.12:

    python -m pip install -r requirements.txt
    python -m streamlit run app.py
    python -m unittest discover -s tests -v
    python -m evaluation.scenarios

GitHub Actions checks Linux Python 3.10/3.12 and Windows Python 3.12. Offline tests cover type inference, every-cell scans, consistent calendar dates, ambiguous dates, identifiers, missing values, partial scans, capped findings, stale UI results, RAG redaction, citations and bounded read tools.

## Code and retained learning exercises

- orders_assistant/csv_check.py: type suggestions and deterministic scan.
- orders_assistant/investigation_ui.py: upload, rule confirmation and reports.
- orders_assistant/csv_guidance.py: generic CSV RAG and bounded agent.
- orders_assistant/query_desk.py: shared Query Desk styling.
- runbooks/csv_*.md: guidance for the new review.
- tests/test_csv_check.py and tests/test_app.py: current checker regressions.

The original orders CLI, transactional pipeline, fixtures and their tests remain for learning and regression coverage. They are not called by the new browser checker. Their numeric ranges, totals and SQLite loads are legacy behavior, not the current application's purpose. The older pipeline scenario evaluation applies to that retained exercise, not to claims about this new generic validator.

See [the current product contract](docs/csv-review.md). Earlier architecture and learning notes describe previous versions.
