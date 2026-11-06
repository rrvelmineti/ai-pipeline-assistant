"""Client handoff: the issue letter sent back to the client, and the comparison with their resubmission.

Onboarding is rarely one file. The client sends an extract, the implementation team returns the
problems, and the client resubmits. These helpers make both steps repeatable:

- client_letter: a plain-English letter grouping the findings by rule, with example lines and how to fix each.
- compare_submissions: what was fixed, what is still open and what is new between two readiness reports.

Both are written by code from the verified report. No AI is used.
"""
from .rules import BLOCKER

EXAMPLES_PER_RULE = 5

# How to fix each kind of finding, keyed by the rule's canonical name (see rules.py).
FIX = {
    "required": "Fill in the missing values from your source system. We cannot guess them.",
    "unique": "Each value must appear once. Remove duplicate rows or correct the repeated identifiers.",
    "number": "Send plain numbers such as 125.50, without currency symbols, commas or words.",
    "whole_number": "Send digits only, with no decimals or signs.",
    "not_negative": "Amounts must be zero or more. Check for reversals exported as negatives.",
    "exactly_digits": "Check the identifier's length and remove spaces, dashes or letters.",
    "exactly_chars": "Check the code's length; codes may have lost or gained characters on export.",
    "date": "Send every date in the stated format, for example 2026-03-31.",
    "not_future": "Dates cannot be after the extract date. Check for typing or conversion errors.",
    "not_before": "This date cannot be earlier than the related date on the same row.",
    "not_greater_than": "This amount cannot be larger than the related amount on the same row.",
    "icd10": "Send ICD-10-CM diagnosis codes, such as E11.9.",
    "one_of": "Use only the allowed values listed for this field.",
    "row_shape": "The row has the wrong number of columns. Check delimiters and quoting in the export.",
}


def _rule_name(specs, field, rule_text):
    if field == "(row)":
        return "row_shape"
    spec = specs.get(field)
    match = next((r for r in spec.rules if r.text == rule_text), None) if spec else None
    return match.name if match else None


# Notes in the findings meant for the analyst, not the client.
ANALYST_NOTES = (" Ask the client for it; do not guess.",)


def _client_words(text, columns):
    """Use the client's own column names instead of the platform's field names."""
    for target, column in sorted(columns.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(target, column)
    for note in ANALYST_NOTES:
        text = text.replace(note, "")
    return text


def client_letter(facts, report, specs, client="the client"):
    """Markdown letter for the client, built only from the verified report."""
    columns = {f: c for f, c in facts.get("mapping", {}).items() if c}
    examples = {}
    for f in report.findings:
        examples.setdefault((f["field"], f["rule"]), []).append(f)
    blockers = [r for r in facts["findings_by_rule"] if r["severity"] == BLOCKER]
    warnings = [r for r in facts["findings_by_rule"] if r["severity"] != BLOCKER]
    lines = [f"# Claims file review for {client}", "",
             f"We checked all {facts['rows_checked']:,} rows of your claims file against the onboarding rules.", ""]
    if facts["decision"] == "Ready":
        lines += ["**The file is ready for go-live.** No changes are required."]
    elif not facts["scan_complete"]:
        lines += ["**We could not check the whole file.** " + next(
            (r for r in facts["reasons"] if r.startswith("The scan did not finish")), "The scan stopped early.")
            + " Please fix this and resend the file so every row can be checked."]
    else:
        lines += [f"**The file is not ready yet.** We found {facts['blockers']:,} problems that must be fixed "
                  f"across {facts['rows_with_blockers']:,} rows. Please correct them in your source system and "
                  "resend the whole file."]
    for title, group, note in (("Must fix before go-live", blockers, None),
                               ("Please review", warnings, "These do not block go-live, but please confirm or correct them.")):
        if not group:
            continue
        lines += ["", f"## {title}", ""]
        if note:
            lines += [note, ""]
        for r in group:
            shown = examples.get((r["field"], r["rule"]), [])[:EXAMPLES_PER_RULE]
            fix = FIX.get(_rule_name(specs, r["field"], r["rule"]), "Please check these values.")
            column = shown[0]["client_column"] if shown else r["field"]
            lines += [f"### {column}: {_client_words(r['rule'], columns)} ({r['count']:,} rows)", "", fix, ""]
            if shown:
                lines += ["| Line | Value sent | Problem |", "| --- | --- | --- |"]
                lines += [f"| {x['line']} | {_cell(x['entered']) or '(blank)'} | {_cell(_client_words(x['message'], columns))} |" for x in shown]
                if r["count"] > len(shown):
                    lines += ["", f"The attached findings file lists all {r['count']:,} rows."]
                lines += [""]
    lines += ["", "Line numbers are physical lines in the file you sent, counting the header as line 1.", ""]
    return "\n".join(lines)


def _cell(text):
    return str(text).replace("|", "/").replace("\n", " ")[:80]


def compare_submissions(previous, current):
    """Compare two readiness reports (the JSON download) rule by rule.

    Findings are matched by field, rule and severity, not by line, because a resubmitted file can
    reorder or add rows.
    """
    def counts(facts):
        return {(r["field"], r["rule"], r["severity"]): r["count"] for r in facts.get("findings_by_rule", [])}
    before, after = counts(previous), counts(current)
    rows = []
    for key in sorted(set(before) | set(after), key=lambda k: (k[2] != BLOCKER, k[0], k[1])):
        b, a = before.get(key, 0), after.get(key, 0)
        status = "fixed" if a == 0 else ("new" if b == 0 else ("improved" if a < b else ("worse" if a > b else "unchanged")))
        rows.append({"field": key[0], "rule": key[1], "severity": key[2], "before": b, "after": a, "status": status})
    return {
        "previous_decision": previous.get("decision"), "current_decision": current.get("decision"),
        "previous_blockers": previous.get("blockers", 0), "current_blockers": current.get("blockers", 0),
        "previous_warnings": previous.get("warnings", 0), "current_warnings": current.get("warnings", 0),
        "same_file": previous.get("source_sha256") == current.get("source_sha256"),
        "mapping_changed": previous.get("mapping") != current.get("mapping"),
        "rows": rows,
        "fixed": sum(r["status"] == "fixed" for r in rows),
        "new": sum(r["status"] == "new" for r in rows),
    }


def comparison_markdown(c):
    lines = ["# Resubmission comparison", "",
             f"Decision: {c['previous_decision']} → **{c['current_decision']}**. "
             f"Blockers: {c['previous_blockers']:,} → {c['current_blockers']:,}. "
             f"Warnings: {c['previous_warnings']:,} → {c['current_warnings']:,}.", ""]
    if c["same_file"]:
        lines += ["Note: both reports are for the same file, so this is not a resubmission.", ""]
    if c["mapping_changed"]:
        lines += ["Note: the column mapping changed between the two checks, so some differences may come from "
                  "the mapping rather than the data.", ""]
    lines += [f"{c['fixed']} rule groups fixed, {c['new']} new.", "",
              "| Field | Rule | Severity | Before | After | Status |", "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {r['field']} | {r['rule']} | {r['severity']} | {r['before']:,} | {r['after']:,} | {r['status']} |"
              for r in c["rows"]] or ["| none | | | 0 | 0 | |"]
    return "\n".join(lines) + "\n"
