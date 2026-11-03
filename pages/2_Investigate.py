"""Session-isolated v2 portfolio workflow."""
import csv
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import streamlit as st

from orders_assistant.core import MAX_BYTES
from orders_assistant.explain import gemini_settings
from orders_assistant.investigate import Index, OUTPUT_TOKENS, corpus, evidence, investigate, keyword_search
from orders_assistant.pipeline_v2 import PROFILES, process, reader_for

ROOT = Path(__file__).resolve().parents[1]
st.title("Pipeline investigation")
st.caption("Use synthetic CSVs. This session has its own database and run history.")
if "v2_dir" not in st.session_state:
    st.session_state.v2_dir = tempfile.TemporaryDirectory()
    st.session_state.v2_history = []
folder = Path(st.session_state.v2_dir.name)
db = folder / "orders.sqlite"
choice = st.selectbox("Input", ["Broken orders", "Successful orders", "Inventory snapshot", "Upload CSV"])
profile = "inventory" if choice == "Inventory snapshot" else "orders"
if choice == "Upload CSV":
    profile = st.selectbox("Validation profile", list(PROFILES))
    upload = st.file_uploader("Synthetic CSV", type="csv")
    if upload is None:
        st.stop()
    if upload.size > MAX_BYTES:
        st.error("The file exceeds two million bytes.")
        st.stop()
    raw = upload.getvalue()
else:
    files = {"Broken orders": "orders/invalid_quantity.csv", "Successful orders": "orders/Orders.csv",
             "Inventory snapshot": "inventory/snapshot.csv"}
    raw = (ROOT / "examples" / files[choice]).read_bytes()
try:
    headers = next(reader_for(raw), [])
except (UnicodeError, csv.Error):
    headers = []
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
st.subheader("Recorded evidence")
st.json(run.model_dump(), expanded=False)
if run.code == "ok":
    st.success(f"{run.rows_validated} rows validated.")
    if run.total_cents is not None:
        st.metric("Committed batch total", f"{run.total_cents // 100}.{run.total_cents % 100:02d}")
else:
    st.warning(f"{run.stage} failed: {run.code} · line {run.row or 'unknown'} · field {run.field or 'unknown'}")
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
