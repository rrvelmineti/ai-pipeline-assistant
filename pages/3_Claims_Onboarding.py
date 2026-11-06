"""Claims data onboarding: AI-suggested mappings, analyst approval, rule checks and readiness."""
import streamlit as st
from claims_onboarding.ui import show_onboarding
from orders_assistant.query_desk import header

st.set_page_config(page_title="Query Desk · Claims onboarding", layout="centered")
header("CLAIMS DATA ONBOARDING", title="Is this client file ready to go live?",
       tagline="Upload the client file. Approve the column mapping. Get a go-live decision.")
st.caption("Map a new client's claims columns with AI help, approve each mapping, check every row against "
           "plain-language rules, and get a go-live decision. Synthetic data only.")
show_onboarding(st.file_uploader("Upload the client claims CSV · up to 20 MB", type=["csv"]))
