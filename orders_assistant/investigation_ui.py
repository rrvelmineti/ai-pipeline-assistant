"""Upload-only, validation-only Query Desk."""
import csv
import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from .csv_check import ColumnRule, DATE_FORMATS, KINDS, MAX_FILE_BYTES, check, suggest
from .query_desk import questions


def clear_review():
    for key in ("csv_report", "csv_answer"):
        st.session_state.pop(key, None)


def show_investigation(upload):
    if upload is None:
        clear_review()
        st.session_state.pop("csv_identity", None)
        st.info("Upload a CSV to begin. No sample data is selected.")
        return
    raw = upload.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    if st.session_state.get("csv_source") != digest:
        clear_review()
        # Remove old per-column choices, including when the user replaces the file.
        for key in list(st.session_state):
            if key.startswith("csv_rule_"):
                del st.session_state[key]
        st.session_state.csv_source = digest
    if len(raw) > MAX_FILE_BYTES:
        clear_review()
        st.error("The upload exceeds 20 MB. Split it into smaller CSV files.")
        return
    try:
        headers, proposed = suggest(raw)
    except (ValueError, UnicodeError, csv.Error):
        clear_review()
        st.error("Cannot read the CSV headers or sample. Check UTF-8 encoding, CSV quoting, and nonempty unique headers (up to 200).")
        return
    st.subheader("Confirm what each column should contain")
    st.caption("Suggestions use headings and up to 500 records. Change any incorrect guess. The review scans every readable record, up to 100,000.")
    rules = {}
    with st.expander("Column types and date formats", expanded=True):
        for i, name in enumerate(headers):
            rule = proposed[name]
            st.text(name)
            left, right = st.columns([2, 1])
            kind = left.selectbox("Expected type", KINDS, index=KINDS.index(rule.kind), key=f"csv_rule_{i}_type")
            allow_blank = right.checkbox("Allow blanks", key=f"csv_rule_{i}_blank")
            fmt = None
            if kind == "Date":
                formats = [None, *DATE_FORMATS]
                fmt = st.selectbox("Date format", formats,
                                   index=formats.index(rule.date_format),
                                   format_func=lambda f: f or "Choose the intended format",
                                   key=f"csv_rule_{i}_date")
            st.caption(rule.reason)
            rules[name] = ColumnRule(kind=kind, date_format=fmt, allow_blank=allow_blank)
    unresolved = any(r.kind == "Date" and r.date_format is None for r in rules.values())
    if unresolved:
        st.warning("Choose a single intended format for each date column before reviewing.")
    skipped = [h for h, r in rules.items() if r.kind == "Not checked"]
    if skipped:
        st.text("Columns left unchecked: " + ", ".join(skipped))
    identity = (digest, json.dumps({h: asdict(r) for h, r in rules.items()}, sort_keys=True))
    if st.session_state.get("csv_identity") != identity:
        clear_review()
        st.session_state.csv_identity = identity
    if st.button("Confirm types and review CSV", type="primary", disabled=unresolved):
        st.session_state.csv_report = check(raw, rules)
        st.session_state.pop("csv_answer", None)
    report = st.session_state.get("csv_report")
    if report is None:
        return
    st.subheader("Your file review")
    a, b = st.columns(2)
    a.metric("Records reviewed", report.rows_checked)
    b.metric("Issues found", report.issue_count)
    if not report.complete:
        st.error("Review incomplete. " + report.file_error)
    elif report.issue_count:
        st.warning(f"{report.issue_count} issues found under the confirmed rules.")
    elif report.unchecked_columns:
        st.warning("No issues found in checked columns. Some columns were not checked.")
    else:
        st.success("No data type or format issues found under the confirmed rules.")
    st.caption("This checks formats and missing values, not factual accuracy or business logic. No totals are calculated, no rows are loaded, and no values are changed.")
    if report.unchecked_columns:
        st.text("Unchecked columns: " + ", ".join(report.unchecked_columns))
    if report.findings:
        st.dataframe(report.findings, hide_index=True, width="stretch")
        st.caption("Line numbers refer to the starting physical CSV line, including the header. Suggestions require review against the source.")
    if report.issue_count > len(report.findings):
        st.warning("All scanned issues are counted, but only the first 5,000 details are retained. Split the file to inspect the rest. Values longer than 500 characters are marked as truncated.")
    questions([
        ("What was checked?", "Each readable row was checked against the types, date formats and blank-value choices you confirmed. An unchecked column has no validation rule."),
        ("Can I trust every value now?", "A value can match a format and still be factually wrong. This review does not certify that the entire dataset is clean."),
        ("What should I do next?", "Review the flagged values against your source, make any verified changes in your original file, then upload it again." if report.issue_count else "Review the coverage and confirmed rules before using the data."),
    ])
    st.download_button("Download review (JSON)", json.dumps(report.to_dict(), indent=2),
                       file_name="csv-review.json", mime="application/json")
    if report.findings:
        show_guidance(report)


def show_guidance(report):
    with st.expander("Optional AI guidance"):
        st.caption("AI can retrieve relevant guidance for one selected issue; it cannot change your file.")
        selected = st.selectbox("Issue to explain", range(len(report.findings)),
                                format_func=lambda i: f"Issue {i + 1} · line {report.findings[i]['line']} · {report.findings[i]['column']}")
        mode = st.radio("Guidance mode", ["RAG", "Agent with read-only tools"])
        allow = st.checkbox("Allow Google to receive the issue category, line number and public guidance. Column headings and cell values are excluded.")
        signature = (selected, mode)
        if st.button("Explain selected issue", disabled=not allow):
            st.session_state.pop("csv_answer", None)
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
                from .csv_guidance import explain_issue
                from .explain import gemini_settings, ExplanationError
                from .investigate import Index, OUTPUT_TOKENS
                key, model = gemini_settings(st.secrets)
                try:
                    em = st.secrets.get("GEMINI_EMBEDDING_MODEL")
                except FileNotFoundError:
                    em = None
                em = em or os.getenv("GEMINI_EMBEDDING_MODEL")
                if not em:
                    raise ExplanationError("Set GEMINI_EMBEDDING_MODEL in Secrets to an available text embedding model.")
                if "csv_index_dir" not in st.session_state:
                    st.session_state.csv_index_dir = tempfile.TemporaryDirectory()
                with st.spinner("Retrieving guidance…"):
                    start = time.monotonic()
                    embeddings = GoogleGenerativeAIEmbeddings(model=em, google_api_key=key, vertexai=False)
                    index = Index(Path(st.session_state.csv_index_dir.name), em, embeddings)
                    llm = ChatGoogleGenerativeAI(model=model, google_api_key=key, vertexai=False,
                                                temperature=0, timeout=30, max_retries=0, max_output_tokens=OUTPUT_TOKENS)
                    answer = explain_issue(report.findings[selected], index, llm, agent=mode.startswith("Agent"))
                    answer["elapsed_seconds"] = round(time.monotonic() - start, 2)
                    st.session_state.csv_answer = (signature, answer)
            except Exception:
                st.warning("AI guidance is unavailable. Check the API key, chat and embedding model settings, and quota. Your file review is still available.")
        saved = st.session_state.get("csv_answer")
        if saved and saved[0] == signature:
            answer = saved[1]
            if answer["next_check"]:
                st.write(answer["next_check"])
                st.caption("Source: " + answer["citation"])
                if answer["model_explanation"]:
                    st.text(answer["model_explanation"])
            else:
                st.info("No supported cited guidance was returned. Verify the finding against the source.")
            st.json(answer, expanded=False)
