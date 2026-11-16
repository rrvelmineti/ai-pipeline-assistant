"""Client communication and issue explanations.

Letters are written by code from verified findings. AI may only reword an explanation, receives no cell
values, and its text is rejected if it states a number the facts do not contain.
"""
import json
import re
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from claims_onboarding.handoff import FIX, _rule_name, client_letter, comparison_markdown, compare_submissions
from claims_onboarding.mapping import call_gemini
from claims_onboarding.rules import BLOCKER, parse_rules
from orders_assistant.explain import ExplanationError, gemini_settings

from . import audit
from .db import utcnow
from .models import Communication, RuleSet, Submission, ValidationRun
from .reporting import findings_rows
from .workflow import latest_run

WHY = {
    "required": "A missing value stops the claim from loading or sends it to manual follow-up.",
    "unique": "Duplicate claim numbers can overwrite another claim or lead to a double payment downstream.",
    "number": "Amounts that are not plain numbers cannot be loaded into financial fields.",
    "whole_number": "Counts with decimals or signs cannot be loaded into whole-number fields.",
    "not_negative": "Negative amounts usually mean reversals were exported as claims and break reconciliation.",
    "exactly_digits": "Identifiers with the wrong length fail provider or member matching.",
    "exactly_chars": "Codes with the wrong length fail code-table lookups.",
    "date": "Dates in an unexpected format can be misread, for example with day and month swapped.",
    "not_future": "Dates after the extract date point to keying or conversion errors.",
    "not_before": "A service dated before the member's birth points to a wrong date or the wrong member.",
    "not_greater_than": "An amount above the billed amount breaks payment reconciliation.",
    "icd10": "Diagnosis codes in the wrong format fail clinical edits and reporting.",
    "one_of": "Unrecognised values cannot be translated to the platform's code list.",
    "row_shape": "Rows with the wrong number of columns shift values into the wrong fields.",
    "file": "Rows after the point where reading stopped were not checked, so the file cannot be approved.",
}


def explanation(exc, rule_text_specs):
    """Deterministic explanation, always available."""
    name = "file" if exc.field == "(file)" else _rule_name(rule_text_specs, exc.field, exc.rule)
    column = exc.client_column or exc.field
    if exc.field == "(file)":
        what = "The latest file could not be read to the end."
    elif exc.current_count:
        what = (f"{exc.current_count:,} rows in the column '{column}' (platform field {exc.field}) "
                f"break the rule '{exc.rule}'.")
    else:
        what = f"The latest file has no rows breaking the rule '{exc.rule}' in '{column}'."
    severity = ("This is a blocker: go-live cannot be approved until a resubmitted file no longer contains it."
                if exc.severity == BLOCKER else
                "This is a warning: it does not block go-live, but it must be fixed or accepted with a note.")
    return {"summary": what + " " + severity, "why_it_matters": WHY.get(name, "It fails an onboarding rule."),
            "how_to_fix": FIX.get(name, "Check these values in the source system and resend the file."),
            "source": "rules"}


def _allowed_numbers(facts):
    text = json.dumps(facts)
    return {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)}


def check_ai_text(text, facts):
    if not isinstance(text, str) or not (20 <= len(text.strip()) <= 900):
        raise ValueError("missing or wrong length")
    extra = {int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)} - _allowed_numbers(facts)
    if extra:
        raise ValueError(f"unsupported figures {sorted(extra)}")
    return text.strip()


def ai_explanation(exc, base, *, opener=None):
    """Ask Gemini to reword the explanation. Only the rule, field, column heading and count are sent."""
    key, model = gemini_settings()
    facts = {"field": exc.field, "client_column": exc.client_column, "rule": exc.rule, "severity": exc.severity,
             "rows_affected": exc.current_count, "why_it_matters": base["why_it_matters"],
             "how_to_fix": base["how_to_fix"]}
    prompt = ("Explain this claims data-quality issue to the client's data team in plain English, in under 90 words. "
              "Use only these facts. Do not add numbers, examples or values that are not in the facts. "
              "Facts: " + json.dumps(facts))
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}
    text = call_gemini(body, key, model, opener)
    try:
        return check_ai_text(text, facts)
    except ValueError as err:
        raise ExplanationError(f"The AI explanation was rejected ({err}); the rule-based one is shown.") from None


def _specs_for_run(db, run):
    return parse_rules(db.get(RuleSet, run.rule_set_id).text)


def draft(db, cipher, client, user, kind, subject="", body=""):
    run = None
    if kind == "note":
        if not subject.strip() or not body.strip():
            raise HTTPException(422, "A note needs a subject and a message.")
        subject, text = subject.strip()[:200], body.strip()[:20000]
    else:
        subs = db.execute(select(Submission).where(Submission.client_id == client.id)
                          .order_by(Submission.sequence.desc())).scalars().all()
        runs = [latest_run(db, s.id, completed_only=True) for s in subs]
        if not runs or runs[0] is None:
            raise HTTPException(409, "Validate the latest file before writing to the client.")
        run = runs[0]
        if kind == "issue_letter":
            report = SimpleNamespace(findings=list(findings_rows(db, cipher, run.id)))
            text = client_letter(run.facts, report, _specs_for_run(db, run), client=client.name)
            subject = f"Claims file review: submission #{subs[0].sequence} ({run.facts['decision']})"
        elif kind == "resubmission_summary":
            if len(runs) < 2 or runs[1] is None:
                raise HTTPException(409, "A resubmission summary needs two validated submissions.")
            text = comparison_markdown(compare_submissions(runs[1].facts, run.facts))
            subject = f"Resubmission #{subs[0].sequence} compared with #{subs[1].sequence}"
        else:
            raise HTTPException(422, "kind must be issue_letter, resubmission_summary or note.")
    c = Communication(client_id=client.id, run_id=run.id if run else None, kind=kind, subject=subject,
                      body_enc=cipher.encrypt(text), status="draft", created_by=user.id)
    db.add(c)
    db.flush()
    audit.record(db, user, "comms.drafted", client_id=client.id, entity="communication", entity_id=c.id,
                 detail={"kind": kind, "subject": subject})
    return c


def send(db, c, user):
    """Pilot: 'sent' records the release to the client contact inside the platform. No e-mail is sent."""
    if c.status != "draft":
        raise HTTPException(409, "This message was already sent.")
    c.status, c.sent_by, c.sent_at = "sent", user.id, utcnow()
    audit.record(db, user, "comms.sent", client_id=c.client_id, entity="communication", entity_id=c.id,
                 detail={"kind": c.kind, "subject": c.subject})
    return c


def run_for(db, c):
    return db.get(ValidationRun, c.run_id) if c.run_id else None
