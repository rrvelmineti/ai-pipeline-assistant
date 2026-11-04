"""Shared presentation for the quick check and investigation pages."""
import streamlit as st

_STYLE = """
<style>
.qd-mast {display:flex;align-items:center;gap:.7rem;border-bottom:1px solid #c0d6e9;
 padding-bottom:1rem;font-weight:650;letter-spacing:-.025em}
.qd-mark {display:inline-grid;place-items:center;width:1.85rem;height:1.85rem;
 background:#225781;color:white;border-radius:.55rem;font-size:1.4rem}
.qd-edition {margin-left:auto;font:600 .72rem/1.5 monospace;letter-spacing:.07em}
.qd-intro {text-align:center;padding:clamp(1.7rem,5vw,3.4rem) 0 1.5rem}
.qd-intro small {font:650 .73rem/1.5 monospace;letter-spacing:.13em}
.qd-intro h1 {font-size:clamp(2.5rem,6vw,4.6rem);letter-spacing:-.062em;
 line-height:1.04;padding:.5rem 0 .65rem;font-weight:550;color:inherit}
.qd-intro p {margin:0 auto;max-width:36rem}
.st-key-qd_questions details {border-radius:1rem;border:1px solid #b0cce1;
 background:var(--secondary-background-color);margin:.15rem 0}
.st-key-qd_questions summary {min-height:3rem}
</style>
"""


def header(workspace, title="Ask about this run."):
    # Callers supply fixed page labels; no file or user text goes into HTML.
    st.markdown(_STYLE + f"""
<div class="qd-mast"><span class="qd-mark" aria-hidden="true">≋</span>
<span>Pipeline Assistant</span><span class="qd-edition">QUERY DESK</span></div>
<div class="qd-intro"><small>{workspace}</small><h1>{title}</h1>
<p>Upload your file. Confirm the suggested types. See which values need attention.</p></div>
""", unsafe_allow_html=True)


def questions(items):
    st.subheader("Questions about this run")
    with st.container(key="qd_questions"):
        for prompt, answer in items:
            with st.expander(prompt):
                st.write(answer)


def location(row, field):
    if row is None:
        return "The run did not identify a specific CSV line."
    return f"CSV line {row}" + (f", field: {field}." if field else ". No individual field was identified.")
