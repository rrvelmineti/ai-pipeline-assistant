"""Mapping suggestions with confidence levels and abstention. Suggestions only: a person confirms and approves."""
from claims_onboarding.mapping import gemini_suggest, heuristic_suggest, score_heading
from orders_assistant.explain import ExplanationError

# A heading needs this score to be suggested at all; below it the platform abstains (leaves the field blank).
ABSTAIN_BELOW = 0.5
# If another heading scores within this margin of the chosen one, the suggestion is ambiguous.
AMBIGUITY_MARGIN = 0.15


def ai_error_text(exc):
    """Explain an AI problem in the platform's terms (the shared settings helper speaks Streamlit)."""
    text = str(exc)
    if text.startswith("Missing GEMINI"):
        return ("Gemini is not configured on this server (set GEMINI_API_KEY and GEMINI_MODEL). "
                "Nothing depends on it: the rule-based results are complete.")
    return text


def _candidates(field, headers):
    out = []
    for h in headers:
        match = score_heading(field, h)
        if match is not None:
            out.append((round(match[0], 3), h))
    return sorted(out, key=lambda c: -c[0])


def _template_for(headers, templates):
    """A saved template applies when every column it maps exists in this file's headings."""
    present = set(headers)
    for t in templates:
        used = {c for c in t.mapping.values() if c}
        if used and used <= present:
            return t
    return None


def suggest(headers, specs, templates=(), use_ai=False, ai_suggest=None):
    """Return {field: suggestion} where each suggestion has column, source, reason, confidence, level,
    alternatives and needs_confirmation. Levels: high, medium, low, ambiguous, none (abstained)."""
    names = heuristic_suggest(headers, specs)
    template = _template_for(headers, templates)
    ai, ai_error = {}, None
    if use_ai:
        try:
            ai = (ai_suggest or gemini_suggest)(headers, specs)
        except ExplanationError as exc:
            ai_error = ai_error_text(exc)
    out = {}
    for f, spec in specs.items():
        cands = _candidates(f, headers)
        s = names[f]
        column, source, reason = s.column, s.source, s.reason
        score = next((sc for sc, h in cands if h == column), 0.0) if column else 0.0
        others = [(sc, h) for sc, h in cands if h != column]
        ambiguous = bool(column and others and score - others[0][0] < AMBIGUITY_MARGIN)
        if column is None:
            level = "none"
        elif ambiguous:
            level = "ambiguous"
        elif score >= 0.9:
            level = "high"
        elif score >= 0.7:
            level = "medium"
        else:
            level = "low"
        alternatives = [h for _, h in others[:3]]
        if template is not None and f in template.mapping:
            t_col = template.mapping[f]
            exact_layout = set(template.headers) == set(headers)
            if exact_layout and t_col is not None:
                # Same layout as an approved, saved mapping: reuse it with high confidence.
                if column and column != t_col and column not in alternatives:
                    alternatives.insert(0, column)
                column, source, level = t_col, "template", "high"
                reason = f"Same file layout as saved template '{template.name}'."
            elif t_col == column and column is not None:
                source, reason, level = "template + name matching", f"Matches saved template '{template.name}'.", "high"
            elif t_col is not None:
                if column and column not in alternatives:
                    alternatives.insert(0, column)
                column, source, reason = t_col, "template", f"From saved template '{template.name}'."
                level = "medium" if s.column is None else "ambiguous"
        if f in ai:
            a = ai[f].column
            if a is not None and a == column:
                if level in ("medium", "low"):
                    level = "high"
                source = source + " + gemini" if source != "none" else "gemini"
                reason = reason + " Gemini agrees."
            elif a is not None and column is None:
                column, source, reason, level = a, "gemini", ai[f].reason, "medium"
            elif a is not None and a != column:
                if column not in alternatives:
                    alternatives.insert(0, column)
                column, source, reason, level = a, "gemini", ai[f].reason + f" Name matching suggested '{s.column}'.", "ambiguous"
            elif a is None and column is not None and level == "high" and source == "name matching":
                level = "medium"
        out[f] = {
            "field": f, "description": spec.description, "required": spec.required,
            "column": column, "source": source, "reason": reason,
            "confidence": round(score, 3) if s.column else None, "level": level,
            "alternatives": [h for h in alternatives if h != column][:3],
            # Anything not clearly matched must be confirmed by a person, including a blank (abstained) field.
            "needs_confirmation": level != "high",
        }
    return {"suggestions": out, "ai_used": bool(ai), "ai_error": ai_error,
            "template": template.name if template is not None else None}


def check_mapping(headers, specs, suggestions, chosen, confirmed):
    """Validate a mapping before it is saved for approval. Returns (problems, corrections)."""
    problems = []
    unknown_fields = sorted(set(chosen) - set(specs))
    chosen = {f: (chosen.get(f) or None) for f in specs}
    if unknown_fields:
        problems.append("Unknown target fields: " + ", ".join(unknown_fields) + ".")
    missing = [f for f, s in specs.items() if s.required and not chosen.get(f)]
    if missing:
        problems.append("Required fields are not mapped: " + ", ".join(missing) + ".")
    used = [c for c in chosen.values() if c]
    dupes = sorted({c for c in used if used.count(c) > 1})
    if dupes:
        problems.append("A client column is mapped to more than one field: " + ", ".join(dupes) + ".")
    absent = sorted({c for c in used if c not in headers})
    if absent:
        problems.append("Mapped columns are not in the file: " + ", ".join(absent) + ".")
    corrections = []
    for f in specs:
        sug = suggestions.get(f, {})
        if chosen.get(f) != sug.get("column"):
            corrections.append({"field": f, "suggested_column": sug.get("column"),
                                "suggested_by": sug.get("source", "none"), "chosen_column": chosen.get(f)})
    changed = {c["field"] for c in corrections}
    # A field the analyst changed is an explicit decision. Anything else not clearly matched must be ticked.
    unconfirmed = [f for f in specs if suggestions.get(f, {}).get("needs_confirmation", True)
                   and f not in changed and f not in set(confirmed)]
    if unconfirmed:
        problems.append("Confirm these fields before saving (ambiguous, low-confidence, AI-only or not mapped): "
                        + ", ".join(unconfirmed) + ".")
    return problems, corrections, unconfirmed
