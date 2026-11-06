"""Go-live readiness: a decision made by code, and summaries that may only use verified figures."""
import csv
import io
import json
import re

from orders_assistant.explain import ExplanationError, gemini_settings

from .mapping import call_gemini
from .rules import BLOCKER


def readiness(specs, mapping, report, corrections):
    """Build the facts an approver needs. The decision is computed here, never by a model."""
    unmapped_required = [f for f, s in specs.items() if s.required and not mapping.get(f)]
    unmapped_optional = [f for f, s in specs.items() if not s.required and not mapping.get(f)]
    reasons = []
    if unmapped_required:
        reasons.append("Required fields are not mapped: " + ", ".join(unmapped_required) + ".")
    if not report.complete:
        reasons.append("The scan did not finish: " + (report.file_error or "unknown reason") + ".")
    if report.blockers:
        reasons.append(f"{report.blockers} blocker findings must be fixed by the client.")
    by_rule = [{"field": f, "rule": r, "severity": sev, "count": c}
               for (f, r, sev), c in sorted(report.counts.items(), key=lambda kv: (kv[0][2] != BLOCKER, -kv[1]))]
    return {
        "decision": "Not ready" if reasons else "Ready",
        "reasons": reasons or ["All required fields are mapped, the full file was scanned and there are no blockers."],
        "rows_checked": report.rows_checked,
        "scan_complete": report.complete,
        "blockers": report.blockers,
        "warnings": report.warnings,
        "rows_with_blockers": len({x["line"] for x in report.findings if x["severity"] == BLOCKER}),
        "findings_by_rule": by_rule,
        "mapping": dict(mapping),
        "unmapped_optional_fields": unmapped_optional,
        "mapping_corrections": corrections,
        "source_sha256": report.source_sha256,
        "scope": "Format and business-rule checks from rules.txt only. Synthetic data. "
                 "Does not verify clinical appropriateness or that values are true.",
    }


def written_summary(facts):
    """A plain-English summary built only from the facts. Always available, no AI needed."""
    parts = [f"Decision: {facts['decision']}. {facts['rows_checked']:,} rows were checked."]
    if facts["blockers"]:
        top = [r for r in facts["findings_by_rule"] if r["severity"] == BLOCKER][:3]
        parts.append(f"There are {facts['blockers']} blockers across {facts['rows_with_blockers']} rows. The largest groups are "
                     + "; ".join(f"{r['field']} ({r['rule']}): {r['count']}" for r in top) + ".")
    else:
        parts.append("There are no blockers.")
    if facts["warnings"]:
        parts.append(f"There are also {facts['warnings']} warnings that do not block go-live but should go back to the client.")
    if facts["mapping_corrections"]:
        parts.append(f"The analyst changed {len(facts['mapping_corrections'])} suggested column mappings.")
    if facts["decision"] != "Ready":
        parts.append("Next step: send the findings file to the client and re-run the check on the corrected file.")
    return " ".join(parts)


def _allowed_numbers(facts):
    numbers = {facts["rows_checked"], facts["blockers"], facts["warnings"], facts["rows_with_blockers"],
               len(facts["mapping_corrections"]), len(facts["findings_by_rule"])}
    numbers |= {r["count"] for r in facts["findings_by_rule"]}
    # Digits that are part of field names or rules (e.g. "exactly 10 digits", "ICD-10") are also allowed.
    text = json.dumps([r["rule"] for r in facts["findings_by_rule"]] + list(facts["mapping"]))
    numbers |= {int(n) for n in re.findall(r"\d+", text)}
    return numbers


def check_summary(text, facts):
    """Reject a model summary that states a figure or a decision the facts do not support."""
    if not isinstance(text, str) or not (20 <= len(text.strip()) <= 1500):
        raise ValueError("Summary missing or the wrong length")
    found = {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)}
    if extra := found - _allowed_numbers(facts):
        raise ValueError(f"Unsupported figures: {sorted(extra)}")
    says_ready = re.search(r"\bnot ready\b", text, re.IGNORECASE) is None and re.search(r"\bready\b", text, re.IGNORECASE)
    if (facts["decision"] == "Ready") != bool(says_ready):
        raise ValueError("Summary contradicts the decision")
    return text.strip()


def gemini_summary(facts, *, secrets=None, opener=None):
    """Ask Gemini to rewrite the verified aggregate facts for a non-technical approver.

    Only aggregate counts, field names and rule text are sent: no cell values, member or claim IDs.
    """
    key, model = gemini_settings(secrets)
    shared = {k: facts[k] for k in ("decision", "reasons", "rows_checked", "blockers", "warnings",
                                    "rows_with_blockers", "findings_by_rule", "unmapped_optional_fields")}
    shared["mapping_corrections"] = len(facts["mapping_corrections"])
    prompt = ("Write a short plain-English summary (under 120 words) of this claims-file go-live readiness "
              "report for a non-technical approver. Use only the facts given. Do not add any number that is not "
              "in the facts, do not estimate, and state the decision exactly as given. Facts: " + json.dumps(shared))
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}
    text = call_gemini(body, key, model, opener)
    try:
        return check_summary(text, facts)
    except ValueError as exc:
        raise ExplanationError(f"The AI summary was rejected ({exc}). The code-written summary is shown instead.") from None


def findings_csv(report):
    buf = io.StringIO()
    cols = ["line", "field", "client_column", "entered", "rule", "severity", "message"]
    writer = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    writer.writeheader()
    writer.writerows(report.findings)
    return buf.getvalue()


def markdown_report(facts, summary):
    lines = [f"# Claims onboarding readiness: {facts['decision']}", "", summary, "", "## Reasons", ""]
    lines += [f"- {r}" for r in facts["reasons"]]
    lines += ["", "## Findings by rule", "", "| Field | Rule | Severity | Count |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['field']} | {r['rule']} | {r['severity']} | {r['count']} |" for r in facts["findings_by_rule"]] or ["| none | | | 0 |"]
    lines += ["", "## Approved mapping", "", "| Target field | Client column |", "| --- | --- |"]
    lines += [f"| {f} | {c or 'not mapped'} |" for f, c in facts["mapping"].items()]
    if facts["mapping_corrections"]:
        lines += ["", "## Mapping corrections by the analyst", "", "| Field | Suggested | Suggested by | Chosen |", "| --- | --- | --- | --- |"]
        lines += [f"| {c['field']} | {c['suggested_column'] or 'none'} | {c['suggested_by']} | {c['chosen_column'] or 'not mapped'} |"
                  for c in facts["mapping_corrections"]]
    lines += ["", f"_Scope: {facts['scope']}_", ""]
    return "\n".join(lines)
