"""Suggest how client columns map to target fields. Suggestions only; the analyst decides."""
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from orders_assistant.explain import ExplanationError, gemini_settings

# Common abbreviations in client claims extracts, expanded before matching.
ABBREVIATIONS = {
    "clm": "claim", "mbr": "member", "mem": "member", "subscriber": "member", "insured": "member",
    "patient": "member", "pt": "member", "prov": "provider", "rendering": "provider",
    "dos": "service date", "svc": "service", "srv": "service", "dx": "diagnosis", "diag": "diagnosis",
    "icd": "diagnosis", "cpt": "procedure", "hcpcs": "procedure", "proc": "procedure",
    "pos": "place of service", "chg": "billed", "charge": "billed", "charges": "billed",
    "billed": "billed", "pd": "paid", "amt": "amount", "allwd": "allowed", "allow": "allowed",
    "sts": "status", "stat": "status", "dob": "dob", "birth": "dob", "nbr": "id", "num": "id",
    "no": "id", "number": "id", "ref": "id", "dt": "date",
}
# Words that describe each target field, used for name matching.
FIELD_WORDS = {
    "claim_id": {"claim", "id"}, "member_id": {"member", "id"}, "member_dob": {"member", "dob"},
    "provider_npi": {"provider", "npi"}, "service_date": {"service", "date"},
    "diagnosis_code": {"diagnosis", "code"}, "procedure_code": {"procedure", "code"},
    "place_of_service": {"place", "of", "service"}, "billed_amount": {"billed", "amount"},
    "allowed_amount": {"allowed", "amount"}, "paid_amount": {"paid", "amount"},
    "claim_status": {"claim", "status"},
}


@dataclass
class Suggestion:
    field: str
    column: str | None
    source: str      # "name matching", "gemini", or "none"
    reason: str


def _words(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    words = []
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        words.extend(ABBREVIATIONS.get(token, token).split())
    return set(words)


def heuristic_suggest(headers, specs):
    """Score word overlap between each heading and each field, then assign best pairs first."""
    scored = []
    for f in specs:
        target = FIELD_WORDS.get(f, set(f.split("_")))
        for h in headers:
            words = _words(h)
            overlap = target & words
            if not overlap:
                continue
            # Reward covering the field's words; lightly penalise extra words in the heading.
            score = len(overlap) / len(target) - 0.05 * len(words - target)
            # The distinctive word (not generic id/code/amount/date) must match.
            distinctive = target - {"id", "code", "amount", "date", "of"}
            if distinctive and not distinctive & words:
                continue
            scored.append((score, f, h, sorted(overlap)))
    scored.sort(key=lambda s: -s[0])
    chosen, used = {}, set()
    for score, f, h, overlap in scored:
        if f in chosen or h in used or score < 0.5:
            continue
        chosen[f] = Suggestion(f, h, "name matching", "Heading words match: " + ", ".join(overlap) + ".")
        used.add(h)
    return {f: chosen.get(f, Suggestion(f, None, "none", "No heading matched this field's name.")) for f in specs}


def _prompt(headers, specs):
    fields = [{"field": f, "description": s.description} for f, s in specs.items()]
    return (
        "You map columns from a client's health insurance claims extract to a platform's target fields. "
        "You see only the column headings, not any data. For each target field, choose the single client "
        "heading that most likely holds it, or null if none fits. Never use one heading twice. "
        "Return only JSON: {\"mappings\": [{\"field\": <target field>, \"column\": <exact heading or null>, "
        "\"reason\": <one short sentence>}]} with one entry per target field.\n"
        "Target fields: " + json.dumps(fields) + "\nClient headings: " + json.dumps(headers))


def check_model_mapping(payload, headers, specs):
    """Accept the model's answer only if it is well-formed and refers to real fields and headings."""
    entries = payload.get("mappings") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError("No mappings list")
    out, used = {}, set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Bad entry")
        f, column, reason = entry.get("field"), entry.get("column"), entry.get("reason", "")
        if f not in specs or f in out:
            raise ValueError("Unknown or repeated field")
        if column is not None and (column not in headers or column in used):
            raise ValueError("Unknown or reused heading")
        if column:
            used.add(column)
        reason = reason if isinstance(reason, str) else ""
        out[f] = Suggestion(f, column, "gemini" if column else "none",
                            (reason.strip()[:200] or "Suggested by Gemini.") if column else "Gemini found no matching heading.")
    if set(out) != set(specs):
        raise ValueError("Missing fields")
    return out


def gemini_suggest(headers, specs, *, secrets=None, opener=None):
    """Ask Gemini for mappings from headings and field descriptions only. No cell values are sent."""
    key, model = gemini_settings(secrets)
    body = {"contents": [{"parts": [{"text": _prompt(headers, specs)}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    payload = call_gemini(body, key, model, opener)
    try:
        return check_model_mapping(payload, headers, specs)
    except ValueError:
        raise ExplanationError("Gemini's mapping referred to unknown fields or headings, so it was rejected. "
                               "Name-matching suggestions are still available.") from None


def call_gemini(body, key, model, opener=None):
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(request, timeout=30) as response:
            raw = response.read(200_001)
        if len(raw) > 200_000:
            raise ValueError("Response too large")
        candidate = json.loads(raw)["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Incomplete response")
        text = "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
        return json.loads(text) if body["generationConfig"].get("responseMimeType") == "application/json" else text
    except urllib.error.HTTPError as exc:
        raise ExplanationError(f"Gemini returned HTTP {exc.code}. Check the model ID, key and quota.") from None
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ExplanationError("Gemini was unavailable or returned an answer that could not be read.") from None


def correction_log(suggested, chosen):
    """List every field where the analyst's choice differs from the suggestion."""
    log = []
    for f, s in suggested.items():
        if chosen.get(f) != s.column:
            log.append({"field": f, "suggested_column": s.column, "suggested_by": s.source,
                        "chosen_column": chosen.get(f)})
    return log


def as_dicts(suggestions):
    return {f: asdict(s) for f, s in suggestions.items()}
