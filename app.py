"""Generic upload-only CSV format review."""
import streamlit as st
from orders_assistant.investigation_ui import show_investigation
from orders_assistant.query_desk import header

st.set_page_config(page_title="Query Desk · CSV data review", layout="centered")
header("CSV DATA REVIEW", title="Is your data in the right format?")
st.caption("Upload a CSV, confirm its column types, and review all detected format issues. Files are processed on the server. Use synthetic data on this public demo.")
show_investigation(st.file_uploader("Upload your CSV · up to 20 MB", type=["csv"]))
