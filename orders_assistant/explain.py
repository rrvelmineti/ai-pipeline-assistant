"""Evidence-first explanations with optional, constrained Gemini classification."""
import json
import os
import re
import urllib.error
import urllib.request
from .core import RULES


class ExplanationError(ValueError):
    pass


def explain(record):
    if record.get("schema_version") != 1 or record.get("status") not in {"success", "error"}:
        raise ExplanationError("Unsupported run record. Run the pipeline again.")
    if record["status"] == "success":
        return {"source": "rules", "stage": "completed", "problem": None,
                "underlying_cause": None, "next_check": "No validation error was found."}
    error = record.get("error")
    if not isinstance(error, dict) or error.get("code") not in RULES:
        raise ExplanationError("Unrecognized evidence code.")
    code = error["code"]
    problem, check = RULES[code]
    expected_stage = "ingestion" if code in {"input_unreadable", "input_too_large"} else "validation"
    if record.get("stage") != expected_stage:
        raise ExplanationError("Evidence stage does not match its error code.")
    return {"source": "rules", "stage": expected_stage, "problem": problem,
            "row": error.get("row"), "field": error.get("field"),
            "underlying_cause": None, "next_check": check}


def gemini_settings(secrets=None):
    """Read explicit Streamlit secrets first, then environment settings for the CLI."""
    values = {}
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL"):
        try:
            value = secrets.get(name) if secrets is not None else None
        except (FileNotFoundError, KeyError):
            value = None
        if value is None:
            value = os.environ.get(name)
        if value is not None and not isinstance(value, str):
            raise ExplanationError(f"{name} must be text inside quotation marks.")
        values[name] = value.strip() if value else ""
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ExplanationError(
            "Missing " + " and ".join(missing) +
            ". Save these as top-level entries in Streamlit Settings > Secrets "
            "(outside any [section]), then reboot the app. For the CLI, set environment variables.")
    model = values["GEMINI_MODEL"].removeprefix("models/")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ExplanationError(
            "GEMINI_MODEL must be the API model ID from AI Studio's Get code, "
            "not a display name with spaces. An optional models/ prefix is accepted.")
    if any(ord(char) < 32 or ord(char) == 127 for char in values["GEMINI_API_KEY"]):
        raise ExplanationError("GEMINI_API_KEY contains an invalid control character. Paste the key again.")
    return values["GEMINI_API_KEY"], model


def gemini_explain(record, opener=None, *, secrets=None):
    baseline = explain(record)
    if record["status"] == "success":
        return baseline
    key, model = gemini_settings(secrets)
    # Never send CSV cells, source paths, or the full record to the model.
    evidence = {"stage": baseline["stage"], "problem": baseline["problem"]}
    prompt = ("Classify this validated orders-pipeline evidence. Return only a JSON object with "
              "code (one of the codes below), stage, and underlying_cause (null; the cause is unknown). "
              "No other fields. Codes: " + json.dumps(RULES) + " Evidence: " + json.dumps(evidence))
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(request, timeout=30) as response:
            raw = response.read(100_001)
        if len(raw) > 100_000:
            raise ValueError("Response too large")
        payload = json.loads(raw)
        candidate = payload["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Incomplete response")
        text = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought"))
        result = json.loads(text)
        expected = {"code": record["error"]["code"], "stage": baseline["stage"], "underlying_cause": None}
        if result != expected:
            raise ValueError("Unsupported model claim")
    except urllib.error.HTTPError as exc:
        guidance = {
            400: "Google rejected the request. Verify the model supports generateContent and JSON output.",
            401: "Google rejected authentication. Check your API key in Streamlit Secrets.",
            403: "Google denied access. Check your key's API restrictions and project permissions.",
            404: "The configured model was not found for this API request. Check the exact model ID and availability for your project.",
            429: "Google's quota or rate limit was reached. Check project limits before retrying.",
        }.get(exc.code, "Check model access, quota, and credentials.")
        raise ExplanationError(f"Gemini returned HTTP {exc.code}. {guidance}") from None
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ExplanationError("Gemini was unavailable or its response did not match the evidence.") from None
    # Render only trusted wording; a model cannot introduce a made-up cause or repair.
    return dict(baseline, source="gemini-verified classification")
