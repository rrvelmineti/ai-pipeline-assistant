"""Streamlit workflow: upload, AI-suggested mapping, analyst approval, rule check, readiness report."""
import csv
import hashlib
import json
from pathlib import Path

import streamlit as st

from orders_assistant.csv_check import MAX_FILE_BYTES, headers_of, reader

from .handoff import client_letter, compare_submissions, comparison_markdown
from .mapping import as_dicts, correction_log, gemini_suggest, heuristic_suggest
from .readiness import findings_csv, gemini_summary, markdown_report, readiness, written_summary
from .rules import RULES_PATH, RulesError, parse_rules, validate

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "claims" / "client_claims.csv"
NOT_MAPPED = "— not mapped —"


def _reset(prefix):
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]


def show_onboarding(upload):
    if SAMPLE.exists():
        st.download_button("Download the synthetic sample claims file", SAMPLE.read_bytes(),
                           file_name="client_claims.csv", mime="text/csv")
    if upload is None:
        _reset("claims_")
        st.info("Upload a client claims CSV to begin. Use synthetic data only; no real member information.")
        return
    raw = upload.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    if st.session_state.get("claims_source") != digest:
        _reset("claims_")
        st.session_state.claims_source = digest
    if len(raw) > MAX_FILE_BYTES:
        st.error("The upload exceeds 20 MB. Split it into smaller files.")
        return
    try:
        headers = headers_of(reader(raw))
    except (ValueError, UnicodeError, csv.Error):
        st.error("Cannot read the CSV header. Check UTF-8 encoding, quoting, and nonempty unique headings.")
        return

    st.subheader("1 · Onboarding rules")
    with st.expander("Plain-language rules (a business user can edit these)"):
        if "claims_rules_text" not in st.session_state:
            st.session_state.claims_rules_text = RULES_PATH.read_text(encoding="utf-8")
        st.text_area("Rules", key="claims_rules_text", height=320, label_visibility="collapsed")
        st.caption("Edits apply to this session only. Code checks these rules, not AI.")
    try:
        specs = parse_rules(st.session_state.claims_rules_text)
    except RulesError as exc:
        st.error("The rules could not be read. " + str(exc))
        return

    st.subheader("2 · Map client columns to target fields")
    if "claims_suggestions" not in st.session_state:
        st.session_state.claims_suggestions = heuristic_suggest(headers, specs)
        st.session_state.claims_suggestion_version = 0
    with st.expander("Ask Gemini to suggest mappings"):
        st.caption("Gemini receives the column headings and the target field descriptions. Cell values are never sent.")
        consent = st.checkbox("Send the column headings to Google for mapping suggestions", key="claims_ai_consent")
        if st.button("Get AI mapping suggestions", disabled=not consent):
            try:
                with st.spinner("Asking Gemini…"):
                    st.session_state.claims_suggestions = gemini_suggest(headers, specs, secrets=st.secrets)
                st.session_state.claims_suggestion_version += 1
                st.session_state.pop("claims_facts", None)
            except ValueError as exc:
                st.warning(str(exc) + " Name-matching suggestions are still shown.")
    suggestions = st.session_state.claims_suggestions
    version = st.session_state.claims_suggestion_version
    options = [NOT_MAPPED, *headers]
    chosen = {}
    for f, spec in specs.items():
        s = suggestions.get(f)
        default = options.index(s.column) if s and s.column in headers else 0
        label = f"{f}{' (required)' if spec.required else ''}"
        pick = st.selectbox(label, options, index=default, key=f"claims_map_{version}_{f}", help=spec.description)
        chosen[f] = None if pick == NOT_MAPPED else pick
        if s and s.column:
            st.caption(f"Suggested by {s.source}: {s.column}. {s.reason}")
        elif s:
            st.caption(f"No suggestion. {s.reason} Choose the column yourself.")
    corrections = correction_log(suggestions, chosen)
    used = [c for c in chosen.values() if c]
    duplicate = sorted({c for c in used if used.count(c) > 1})
    missing = [f for f, s in specs.items() if s.required and not chosen[f]]
    if corrections:
        st.caption(f"You changed {len(corrections)} suggested mapping(s). Each change is logged in the report.")
    if duplicate:
        st.warning("Each client column can map to only one field: " + ", ".join(duplicate))
    if missing:
        st.warning("Map every required field before checking: " + ", ".join(missing))

    identity = json.dumps([digest, st.session_state.claims_rules_text, chosen], sort_keys=True)
    if st.session_state.get("claims_identity") != identity:
        for key in ("claims_facts", "claims_report", "claims_ai_summary"):
            st.session_state.pop(key, None)
        st.session_state.claims_identity = identity

    st.subheader("3 · Check the file")
    if st.button("Approve mapping and check every row", type="primary", disabled=bool(duplicate or missing)):
        report = validate(raw, chosen, specs)
        st.session_state.claims_report = report
        st.session_state.claims_facts = readiness(specs, chosen, report, corrections)
        st.session_state.pop("claims_ai_summary", None)
    facts = st.session_state.get("claims_facts")
    if facts is None:
        return
    report = st.session_state.claims_report
    show_report(facts, report, as_dicts(suggestions), specs)


def show_report(facts, report, suggestions, specs):
    st.subheader("4 · Go-live readiness")
    (st.success if facts["decision"] == "Ready" else st.error)(f"Decision: {facts['decision']}")
    for reason in facts["reasons"]:
        st.write("• " + reason)
    a, b, c = st.columns(3)
    a.metric("Rows checked", f"{facts['rows_checked']:,}")
    b.metric("Blockers", facts["blockers"])
    c.metric("Warnings", facts["warnings"])
    if facts["findings_by_rule"]:
        st.dataframe(facts["findings_by_rule"], hide_index=True, width="stretch")
    summary = written_summary(facts)
    st.markdown("**Summary for the approver**")
    st.write(summary)
    with st.expander("Optional AI-written summary"):
        st.caption("Gemini receives only aggregate counts, field names and rule text. "
                   "Its summary is rejected if it states any figure or decision the report does not contain.")
        consent = st.checkbox("Send the aggregate figures to Google", key="claims_summary_consent")
        if st.button("Write AI summary", disabled=not consent):
            try:
                st.session_state.claims_ai_summary = gemini_summary(facts, secrets=st.secrets)
            except ValueError as exc:
                st.session_state.claims_ai_summary = None
                st.warning(str(exc))
        if st.session_state.get("claims_ai_summary"):
            st.write(st.session_state.claims_ai_summary)
            st.caption("Checked: every figure in this summary appears in the verified report.")
    if report.findings:
        st.markdown("**Findings for the client**")
        st.dataframe(report.findings, hide_index=True, width="stretch")
        if report.blockers + report.warnings > len(report.findings):
            st.caption("All findings are counted, but only the first 5,000 details are listed.")
    if facts["mapping_corrections"]:
        st.markdown("**Mapping corrections**")
        st.dataframe(facts["mapping_corrections"], hide_index=True, width="stretch")
    left, mid, right = st.columns(3)
    left.download_button("Findings (CSV)", findings_csv(report), file_name="claims-findings.csv", mime="text/csv")
    mid.download_button("Report (Markdown)", markdown_report(facts, st.session_state.get("claims_ai_summary") or summary),
                        file_name="claims-readiness.md", mime="text/markdown")
    right.download_button("Report (JSON)", json.dumps({**facts, "suggestions": suggestions}, indent=2),
                          file_name="claims-readiness.json", mime="application/json")
    show_handoff(facts, report, specs)


def show_handoff(facts, report, specs):
    st.subheader("5 · Send back to the client")
    client = st.text_input("Client name for the letter", value="the client", key="claims_client_name")
    letter = client_letter(facts, report, specs, client.strip() or "the client")
    with st.expander("Preview the client issue letter"):
        st.markdown(letter)
    st.download_button("Client issue letter (Markdown)", letter, file_name="claims-client-letter.md",
                       mime="text/markdown")
    st.caption("Written by code from the verified report: grouped by rule, with example lines and how to fix each.")

    st.subheader("6 · Compare with the previous submission")
    previous = st.file_uploader("Upload the JSON report from the client's previous file", type=["json"],
                                key="claims_previous_report")
    if previous is None:
        st.caption("After the client resubmits, upload the earlier JSON report to see what was fixed and what is new.")
        return
    try:
        before = json.loads(previous.getvalue())
        if not isinstance(before, dict) or "findings_by_rule" not in before:
            raise ValueError
    except (ValueError, UnicodeError):
        st.error("That is not a readiness report. Upload the Report (JSON) file downloaded from this page.")
        return
    comparison = compare_submissions(before, facts)
    a, b, c = st.columns(3)
    a.metric("Blockers", f"{comparison['current_blockers']:,}",
             delta=comparison["current_blockers"] - comparison["previous_blockers"], delta_color="inverse")
    b.metric("Rule groups fixed", comparison["fixed"])
    c.metric("New rule groups", comparison["new"])
    if comparison["same_file"]:
        st.warning("Both reports are for the same file, so this is not a resubmission.")
    if comparison["mapping_changed"]:
        st.warning("The column mapping changed between the two checks; some differences may come from the mapping.")
    st.dataframe(comparison["rows"], hide_index=True, width="stretch")
    st.download_button("Comparison (Markdown)", comparison_markdown(comparison),
                       file_name="claims-resubmission.md", mime="text/markdown")
