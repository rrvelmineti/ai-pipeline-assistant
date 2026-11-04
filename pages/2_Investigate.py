"""Compatibility route to the same validation-only workspace."""
import streamlit as st
from orders_assistant.investigation_ui import show_investigation
from orders_assistant.query_desk import header

header("CSV DATA REVIEW", title="Review your CSV.")
st.caption("Upload your own file. Confirm column types, review issues, then optionally retrieve guidance.")
show_investigation(st.file_uploader("Upload your CSV · up to 20 MB", type=["csv"]))
