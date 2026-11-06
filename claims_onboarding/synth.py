"""Generate a synthetic client claims extract with planted errors and a known-correct answer key.

Every value is invented. Run:  python -m claims_onboarding.synth
"""
import csv
import io
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "examples" / "claims"
ROWS = 2_000
SEED = 2026

# Client headings in the order the client exports them. Some are distractors.
CLIENT_COLUMNS = ["Clm_Nbr", "Group Nbr", "Subscriber Ref", "Patient Birth Dt", "Billing Prov NPI",
                  "Rendering NPI", "DOS_From", "Paid Dt", "Primary Dx", "Svc Code", "POS",
                  "Total Charges", "Allowed Amt", "Plan Paid Amt", "Claim Sts", "Line Count"]
# The correct mapping, used to measure how good mapping suggestions are.
ANSWER_KEY = {
    "claim_id": "Clm_Nbr", "member_id": "Subscriber Ref", "member_dob": "Patient Birth Dt",
    "provider_npi": "Rendering NPI", "service_date": "DOS_From", "diagnosis_code": "Primary Dx",
    "procedure_code": "Svc Code", "place_of_service": "POS", "billed_amount": "Total Charges",
    "allowed_amount": "Allowed Amt", "paid_amount": "Plan Paid Amt", "claim_status": "Claim Sts",
}
ICD10 = ["E11.9", "I10", "J06.9", "M54.50", "Z00.00", "R51.9", "K21.9", "F41.1", "N39.0", "E78.5"]
PROCEDURES = ["99213", "99214", "80053", "85025", "93000", "J1100", "71046", "97110"]
PLACES = ["11", "21", "22", "23", "81"]
STATUSES = ["paid"] * 7 + ["denied", "pending", "adjusted"]

# (field, rule as written in rules.txt, how many rows to break)
PLANTED = [
    ("claim_id", "unique", 5),
    ("member_id", "required", 4),
    ("provider_npi", "exactly 10 digits", 6),
    ("service_date", "not in the future", 3),
    ("service_date", "not before member_dob", 2),
    ("service_date", "date YYYY-MM-DD", 3),
    ("diagnosis_code", "ICD-10 format", 4),
    ("procedure_code", "exactly 5 characters", 3),
    ("billed_amount", "number", 3),
    ("paid_amount", "not greater than billed_amount", 4),
    ("paid_amount", "not negative", 2),
    ("allowed_amount", "not greater than billed_amount", 5),
    ("place_of_service", "exactly 2 digits", 5),
    ("claim_status", "one of paid / denied / pending / adjusted", 3),
]


def _clean_row(rng, i):
    dob = date(1945, 1, 1) + timedelta(days=rng.randrange(365 * 65))
    service = date(2025, 1, 1) + timedelta(days=rng.randrange(630))
    billed = round(rng.uniform(50, 2500), 2)
    allowed = round(billed * rng.uniform(0.5, 0.9), 2)
    status = rng.choice(STATUSES)
    paid = 0.0 if status == "denied" else round(allowed * rng.uniform(0.6, 1.0), 2)
    return {
        "Clm_Nbr": f"CLM{1_000_000 + i}", "Group Nbr": f"G{rng.randrange(100, 999)}",
        "Subscriber Ref": f"M{rng.randrange(10**7, 10**8)}", "Patient Birth Dt": dob.isoformat(),
        "Billing Prov NPI": f"1{rng.randrange(10**8, 10**9)}", "Rendering NPI": f"1{rng.randrange(10**8, 10**9)}",
        "DOS_From": service.isoformat(),
        "Paid Dt": (service + timedelta(days=rng.randrange(10, 45))).isoformat(),
        "Primary Dx": rng.choice(ICD10), "Svc Code": rng.choice(PROCEDURES), "POS": rng.choice(PLACES),
        "Total Charges": f"{billed:.2f}", "Allowed Amt": f"{allowed:.2f}", "Plan Paid Amt": f"{paid:.2f}",
        "Claim Sts": status, "Line Count": str(rng.randrange(1, 6)),
    }


def _break(row, field, rule, rng, rows):
    col = ANSWER_KEY[field]
    if rule == "unique":
        row[col] = rows[rng.randrange(0, 200)]["Clm_Nbr"]   # copy an earlier claim number
    elif rule == "required":
        row[col] = ""
    elif rule == "exactly 10 digits":
        row[col] = row[col][:9]
    elif rule == "not in the future":
        row[col] = f"2028-0{rng.randrange(1, 9)}-15"
    elif rule == "not before member_dob":
        row["Patient Birth Dt"] = "2026-10-01"
        row[col] = "2025-06-15"
    elif rule == "date YYYY-MM-DD":
        y, m, d = row[col].split("-")
        row[col] = f"{m}/{d}/{y}"
    elif rule == "ICD-10 format":
        row[col] = rng.choice(["119.0", "E1", "DIABETES", "E11.95X7Q"])
    elif rule == "exactly 5 characters":
        row[col] = row[col][:4]
    elif rule == "number":
        row[col] = "$" + row[col]
    elif rule == "not negative":
        row[col] = "-15.00"
    elif rule == "not greater than billed_amount":
        row[col] = f"{float(row['Total Charges']) + 100:.2f}"
        if field == "paid_amount":   # keep allowed consistent so only the planted rule fails
            row["Allowed Amt"] = row["Total Charges"]
            row["Claim Sts"] = "paid"
    elif rule == "exactly 2 digits":
        row[col] = "110"
    elif rule.startswith("one of"):
        row[col] = "approved"


def generate(rows=ROWS, seed=SEED):
    """Return (csv_bytes, answer_key) where answer_key lists every planted error by CSV line."""
    rng = random.Random(seed)
    data = [_clean_row(rng, i) for i in range(rows)]
    # Planted rows come from line 300 onwards so duplicate claim numbers point at earlier lines.
    targets = rng.sample(range(300, rows), sum(n for *_, n in PLANTED))
    planted, k = [], 0
    for field, rule, n in PLANTED:
        for _ in range(n):
            i = targets[k]
            k += 1
            _break(data[i], field, rule, rng, data)
            planted.append({"line": i + 2, "field": field, "rule": rule})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CLIENT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(data)
    key = {"mapping": ANSWER_KEY, "rows": rows, "seed": seed,
           "planted_errors": sorted(planted, key=lambda p: p["line"]),
           "note": "Synthetic data. Every value is invented; no real people or providers."}
    return buf.getvalue().encode("utf-8"), key


def main():
    raw, key = generate()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "client_claims.csv").write_bytes(raw)
    (OUT / "answer_key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {key['rows']} rows and {len(key['planted_errors'])} planted errors to {OUT}")


if __name__ == "__main__":
    main()
