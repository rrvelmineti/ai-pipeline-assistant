import streamlit as st

from orders_assistant.investigation_ui import show_investigation
from orders_assistant.query_desk import header

header("INVESTIGATION / GUIDED REVIEW")
st.caption("Use synthetic CSVs. This session has its own database and run history.")
show_investigation(st.file_uploader("Upload your CSV · up to 2 MB", type="csv"))
