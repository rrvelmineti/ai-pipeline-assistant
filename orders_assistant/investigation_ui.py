"""Session-isolated v2 portfolio workflow."""
import csv
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import streamlit as st

from orders_assistant.query_desk import location, questions
from orders_assistant.core import MAX_BYTES
from orders_assistant.explain import gemini_settings
from orders_assistant.investigate import Index, OUTPUT_TOKENS, corpus, evidence, investigate, keyword_search
from orders_assistant.pipeline_v2 import PROFILES, process, reader_for


def show_investigation(upload):
    if "v2_dir" not in st.session_state:
        st.session_state.v2_dir = tempfile.TemporaryDirectory()
        st.session_state.v2_history = []
    folder = Path(st.session_state.v2_dir.name)
    db = folder / "orders.sqlite"
    if upload is None or upload.size > MAX_BYTES:
        for key in ("v2_identity", "v2_run", "v2_answer"):
            st.session_state.pop(key, None)
        if upload is not None:
            st.error("The file exceeds two million bytes.")
        st.stop()
    raw = upload.getvalue()
    profile = st.selectbox("Validation profile", list(PROFILES), index=None,
                           placeholder="Choose the rules for your file")
    if profile is None:
        st.session_state.pop("v2_run", None)
        st.session_state.pop("v2_answer", None)
        st.stop()
    try:
        headers = next(reader_for(raw), [])
    except (UnicodeError, csv.Error):
        headers = []
    with st.expander("Review column mapping", expanded=True):
        st.write("Source columns", headers)
        mapping = {}
        for name, rule in PROFILES[profile].items():
            choices = [None, *dict.fromkeys(headers)]
            selected = st.selectbox(f"{name} ({rule.kind}, {'required' if rule.required else 'optional'})",
                                    choices, index=choices.index(name) if name in choices else 0,
                                    format_func=lambda x: "Unmapped" if x is None else x)
            if selected is not None:
                mapping[name] = selected
    limits = {}
    with st.expander("Numeric validation ranges"):
        for field, rule in PROFILES[profile].items():
            if rule.kind in {"integer", "decimal"}:
                low = st.number_input(f"Minimum {field}", rule.minimum, rule.maximum, rule.minimum)
                high = st.number_input(f"Maximum {field}", rule.minimum, rule.maximum, rule.maximum)
                limits[field] = (low, high)
    identity = (hashlib.sha256(raw).hexdigest(), profile, tuple(mapping.items()), tuple(limits.items()))
    if st.session_state.get("v2_identity") != identity:
        st.session_state.v2_identity = identity
        st.session_state.pop("v2_run", None)
        st.session_state.pop("v2_answer", None)
    if st.button("Confirm mapping and run pipeline", type="primary"):
        run = process(raw, profile, mapping, db, limits=limits)
        st.session_state.v2_run = run
        st.session_state.v2_history.append(run)
        st.session_state.pop("v2_answer", None)
    run = st.session_state.get("v2_run")
    if not run:
        st.stop()
    if run.code == "ok":
        st.success(f"{run.rows_validated} rows validated.")
        if run.total_cents is not None:
            st.metric("Committed batch total", f"{run.total_cents // 100}.{run.total_cents % 100:02d}")
        outcome = ("Inventory was validated only; no orders were stored." if profile == "inventory" else
                   "This batch was already loaded; no duplicate orders were added." if run.already_loaded else
                   "The orders batch was committed to this session’s database.")
        questions([("What did this run validate?", f"{run.rows_validated} rows passed the {profile} profile."),
                   ("What was stored?", outcome),
                   ("What should I check next?", "Compare the validated count with the source export.")])
    else:
        docs = {d.metadata["section"]: d for d in corpus() if d.metadata["code"] == run.code}
        st.warning(f"Stopped during {run.stage} · {run.code}")
        problem = {
            "invalid_number": "A numeric field did not meet its format or range rule.",
            "invalid_date": "A date did not meet the ISO date rule.",
            "duplicate": "A field that must be unique contained a repeated value.",
            "missing_value": "A required value was missing.",
            "invalid_mapping": "The headers, selected columns, or configured limits did not meet the profile rules.",
            "invalid_csv": "The input could not be parsed as the expected UTF-8 CSV.",
            "database_failure": "The database operation failed.",
            "empty_file": "No data rows were available to validate.",
            "input_limit": "The input exceeded a configured file or row limit.",
        }.get(run.code, "The run did not complete.")
        # A parser failure may retain the last processed position rather than the failing line.
        where = (location(None, None) if run.code == "invalid_csv" else location(run.row, run.field))
        check = docs.get("Next check")
        questions([("Why did this run stop?", problem), ("Which row failed?", where),
                   ("What should I check next?", check.page_content if check else "Inspect the source export.")])
    with st.expander("Inspect the recorded evidence"):
        st.json(run.model_dump(), expanded=False)
    st.subheader("Investigate further")
    question = st.selectbox("Investigation question", ["What should I check next?",
        "How many orders are stored in this session?", "Has this failure happened before in this session?"])
    mode = st.radio("Investigation mode", ["Evidence only", "RAG", "Agent with read-only tools"])
    if mode == "Evidence only":
        st.write(evidence(run))
        st.caption("Offline keyword matches")
        for doc in keyword_search(run.code + " " + question, corpus()):
            st.write(doc.metadata["title"], doc.page_content)
    else:
        allow = st.checkbox("Allow Google to receive the selected question, sanitized run facts, public runbook passages and session aggregate counts.")
        if st.button("Investigate", disabled=not allow):
            st.session_state.pop("v2_answer", None)
            start = time.monotonic()
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
                key, model = gemini_settings(st.secrets)
                try:
                    em = st.secrets.get("GEMINI_EMBEDDING_MODEL")
                except FileNotFoundError:
                    em = None
                em = em or os.getenv("GEMINI_EMBEDDING_MODEL")
                if not em:
                    st.warning("Set GEMINI_EMBEDDING_MODEL to a text embedding model available in your Google project.")
                    st.stop()
                embeddings = GoogleGenerativeAIEmbeddings(model=em, google_api_key=key, vertexai=False)
                index = Index(folder / "index", em, embeddings)
                llm = ChatGoogleGenerativeAI(model=model, google_api_key=key, vertexai=False, temperature=0,
                                             timeout=30, max_retries=0, max_output_tokens=OUTPUT_TOKENS)
                result = investigate(run, question, index, llm, db, st.session_state.v2_history,
                                     agent=mode.startswith("Agent"))
                result["elapsed_seconds"] = round(time.monotonic() - start, 2)
                st.session_state.v2_answer = (mode, question, result)
            except Exception:
                st.warning("Investigation unavailable. Check the model settings, credentials and quota. The recorded pipeline evidence is available above.")
        answer = st.session_state.get("v2_answer")
        if answer and answer[:2] == (mode, question):
            st.json(answer[2])
            st.download_button("Download investigation", json.dumps(answer[2], indent=2), "investigation.json")
    st.download_button("Download evidence", run.model_dump_json(indent=2), "evidence.json")
