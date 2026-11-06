"""Measure mapping suggestions and rule checks against the synthetic answer key.

Offline (name matching and rule checks):   python -m evaluation.claims_mapping
With Gemini as well:                       set GEMINI_API_KEY and GEMINI_MODEL, then add --gemini
Save results for the README:               add --save
"""
import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from claims_onboarding.mapping import gemini_suggest, heuristic_suggest
from claims_onboarding.rules import load_rules, validate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "claims"
RESULTS = ROOT / "evaluation" / "results" / "claims_mapping.json"


def score(suggestions, key):
    rows, totals = [], Counter()
    for f, correct in key.items():
        got = suggestions[f].column
        outcome = "correct" if got == correct else ("left blank" if got is None else "wrong")
        totals[outcome] += 1
        rows.append({"field": f, "expected": correct, "suggested": got, "outcome": outcome,
                     "source": suggestions[f].source})
    return {"correct": totals["correct"], "wrong": totals["wrong"], "left_blank": totals["left blank"],
            "fields": len(key), "details": rows}


def rule_recall(key, today):
    raw = (EXAMPLE / "client_claims.csv").read_bytes()
    report = validate(raw, key["mapping"], load_rules(), today=today)
    got = Counter((f["line"], f["field"], f["rule"]) for f in report.findings)
    want = Counter((p["line"], p["field"], p["rule"]) for p in key["planted_errors"])
    return {"planted": sum(want.values()), "caught": sum((got & want).values()),
            "missed": sum((want - got).values()), "false_alarms": sum((got - want).values()),
            "rows_checked": report.rows_checked}


def print_score(name, result):
    print(f"\n{name}: {result['correct']} of {result['fields']} correct, "
          f"{result['wrong']} wrong, {result['left_blank']} left blank")
    for r in result["details"]:
        mark = {"correct": "ok", "wrong": "WRONG", "left blank": "blank"}[r["outcome"]]
        print(f"  {mark:6} {r['field']:18} expected {r['expected']!s:18} got {r['suggested']!s}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gemini", action="store_true", help="also score live Gemini suggestions")
    parser.add_argument("--save", action="store_true", help=f"write results to {RESULTS.relative_to(ROOT)}")
    args = parser.parse_args(argv)
    key = json.loads((EXAMPLE / "answer_key.json").read_text())
    headers = (EXAMPLE / "client_claims.csv").read_text().splitlines()[0].split(",")
    specs = load_rules()
    results = {"name_matching": score(heuristic_suggest(headers, specs), key["mapping"])}
    print_score("Name matching", results["name_matching"])
    if args.gemini:
        import os
        results["gemini"] = score(gemini_suggest(headers, specs), key["mapping"])
        results["gemini"]["model"] = os.environ.get("GEMINI_MODEL")
        print_score(f"Gemini ({results['gemini']['model']})", results["gemini"])
    results["rule_checks"] = rule_recall(key, date(2026, 11, 5))
    r = results["rule_checks"]
    print(f"\nRule checks: caught {r['caught']} of {r['planted']} planted errors, "
          f"{r['missed']} missed, {r['false_alarms']} false alarms, across {r['rows_checked']:,} rows")
    if args.save:
        RESULTS.parent.mkdir(exist_ok=True)
        results["evaluated_on"] = date.today().isoformat()
        RESULTS.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"\nSaved {RESULTS.relative_to(ROOT)}")
    if r["missed"] or r["false_alarms"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
