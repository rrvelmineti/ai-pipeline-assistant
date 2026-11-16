"""Synthetic client files for the scenarios, the demo seed and the tests. Every value is invented."""
import csv
import io
import random

from claims_onboarding import synth

# Scenario C: another vendor's extract layout. Two NPI columns tie on name matching, and some headings are vague.
VENDOR_C = {
    "Clm_Nbr": "Claim Reference", "Group Nbr": "Group ID", "Subscriber Ref": "Member Number",
    "Patient Birth Dt": "Member DOB", "Billing Prov NPI": "Billing Provider NPI",
    "Rendering NPI": "Servicing Provider NPI", "DOS_From": "Service Date From", "Paid Dt": "Paid Date",
    "Primary Dx": "Diagnosis 1", "Svc Code": "Procedure", "POS": "Place of Service", "Total Charges": "Billed Amount",
    "Allowed Amt": "Allowed Amount", "Plan Paid Amt": "Paid Amount", "Claim Sts": "Status", "Line Count": "Lines",
}
VENDOR_C_MAPPING = {f: VENDOR_C[c] for f, c in synth.ANSWER_KEY.items()}
DATE_COLUMNS = ("Patient Birth Dt", "DOS_From", "Paid Dt")


def _us_date(iso):
    y, m, d = iso.split("-")
    return f"{m}/{d}/{y}"


def build_file(rows=500, seed=7, breaks=(), rename=None, us_dates=False, first_claim=0):
    """Return (csv bytes, planted errors). breaks: (field, rule, count) as in synth.PLANTED, plus the extra
    ('member_dob', 'future') which also makes the service date fall before the birth date."""
    rng = random.Random(seed)
    data = [synth._clean_row(rng, first_claim + i) for i in range(rows)]
    total = sum(n for *_, n in breaks)
    targets = rng.sample(range(max(rows // 2, min(rows, 250)), rows), total) if total else []
    planted, k = [], 0
    for field, rule, n in breaks:
        for _ in range(n):
            i = targets[k]
            k += 1
            if (field, rule) == ("member_dob", "future"):
                data[i]["Patient Birth Dt"] = "2031-02-01"
                planted.append({"line": i + 2, "field": "member_dob", "rule": "not in the future"})
                planted.append({"line": i + 2, "field": "service_date", "rule": "not before member_dob"})
                continue
            synth._break(data[i], field, rule, rng, data)
            planted.append({"line": i + 2, "field": field, "rule": rule})
    columns = list(synth.CLIENT_COLUMNS)
    if us_dates:
        for row in data:
            for c in DATE_COLUMNS:
                if len(row[c]) == 10 and row[c][4] == "-":
                    row[c] = _us_date(row[c])
    if rename:
        data = [{rename.get(k, k): v for k, v in row.items()} for row in data]
        columns = [rename.get(c, c) for c in columns]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    w.writerows(data)
    return buf.getvalue().encode("utf-8"), sorted(planted, key=lambda p: p["line"])


def truncated(raw):
    """A file cut off part-way through its last row, as when a transfer stops early."""
    return raw[: raw.rfind(b"\n", 0, len(raw) - 1) + 25]


def corrupted(raw):
    """A file with invalid UTF-8 bytes in the middle, so it cannot be read to the end."""
    mid = raw.find(b"\n", len(raw) // 2) + 1
    return raw[:mid] + b"\xff\xfe\xfa" + raw[mid:]


US_DATE_RULES_CHANGE = {"member_dob": ("date YYYY-MM-DD", "date MM/DD/YYYY"),
                        "service_date": ("date YYYY-MM-DD", "date MM/DD/YYYY")}


def rules_with_us_dates(text):
    out = []
    for line in text.splitlines():
        name = line.split("|")[0].strip()
        if name in US_DATE_RULES_CHANGE and not line.lstrip().startswith("#"):
            old, new = US_DATE_RULES_CHANGE[name]
            line = line.replace(old, new)
        out.append(line)
    return "\n".join(out) + "\n"
