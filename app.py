"""Upload-first orders validation workspace."""
import streamlit as st

from orders_assistant.investigation_ui import show_investigation
from orders_assistant.query_desk import header

st.set_page_config(page_title="Query Desk · Orders CSV checker", layout="centered")
header("ORDERS CSV CHECK", title="Review your orders CSV.")
st.caption("Upload a synthetic orders CSV to check quantities and unit prices across the file. Other columns are listed as unchecked.")
show_investigation(st.file_uploader("Upload your orders CSV · up to 2 MB", type=["csv"]), profile="orders")
