"""Single-user local demo: python -m streamlit run app.py."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from orders_assistant.investigation_ui import show_investigation
from orders_assistant.query_desk import header, location, questions
from orders_assistant.core import analyze, MAX_BYTES
from orders_assistant.explain import explain, gemini_explain, ExplanationError

st.set_page_config(page_title="Query Desk · Pipeline Assistant", layout="centered")
header("PIPELINE INVESTIGATION")
st.caption("Use synthetic data. Files are processed on the server; download your report before leaving this session.")
upload = st.file_uploader("Upload your CSV · up to 2 MB", type=["csv"])
if upload is None:
    for key in ("input_hash", "record", "ai", "v2_identity", "v2_run", "v2_answer"):
        st.session_state.pop(key, None)
    st.stop()
workflow = st.radio("Workflow", ["Guided investigation", "Quick orders check"], horizontal=True)
if workflow == "Guided investigation":
    show_investigation(upload)
    st.stop()

st.caption("The quick check expects the columns quantity and unit_price.")
raw = upload.getvalue()
fingerprint = hashlib.sha256(raw).hexdigest()
if st.session_state.get("input_hash") != fingerprint:
    st.session_state.pop("record", None)
    st.session_state.pop("ai", None)
    st.session_state["input_hash"] = fingerprint
if len(raw) > MAX_BYTES:
    st.error("Please upload a CSV smaller than 2 MB.")
elif st.button("Run pipeline", type="primary"):
    with TemporaryDirectory() as folder:
        source = Path(folder) / "Orders.csv"
        source.write_bytes(raw)
        st.session_state.record = analyze(source)
    st.session_state.pop("ai", None)
record = st.session_state.get("record")
if record:
    if record["status"] == "success":
        st.success("Pipeline completed")
        left, right = st.columns(2)
        left.metric("Total sales · currency units", record["total_sales"])
        right.metric("Orders validated", record["rows_processed"])
        questions([
            ("What did this run validate?", f"All {record['rows_processed']} orders passed the quantity and unit price checks."),
            ("How was the total calculated?", "Each quantity was multiplied by its unit price, then the order totals were added."),
            ("What should I check next?", "Compare the validated count and total with your source export."),
        ])
    else:
        detail = explain(record)
        st.error("Pipeline stopped during " + detail["stage"] + ".")
        questions([
            ("Why did this run stop?", detail["problem"]),
            ("Which row failed?", location(detail["row"], detail["field"])),
            ("What should I check next?", detail["next_check"]),
        ])
        st.caption("The upstream cause is unknown. Gemini verification is optional.")
        st.checkbox("Allow sending the generic error category to Google Gemini", key="allow_ai")
        if st.button("Verify classification with Gemini", disabled=not st.session_state.allow_ai):
            try:
                with st.spinner("Checking the evidence…"):
                    st.session_state.ai = gemini_explain(record, secrets=st.secrets)
            except ExplanationError as exc:
                st.warning(str(exc))
        if st.session_state.get("ai"):
            st.success("Gemini classification matched the recorded evidence. No data was changed.")
    with st.expander("Inspect the evidence"):
        st.json(record)
    st.download_button("Download run report (JSON)", json.dumps(record, indent=2),
                       file_name=f"run-{record['run_id']}.json", mime="application/json")
st.divider()
st.caption("No automatic repairs. Offline checks are deterministic; optional AI classification is checked against the evidence.")
