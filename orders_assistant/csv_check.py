"""Deterministic, validation-only CSV review. Inference proposes; rules decide."""
import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime

MAX_FILE_BYTES = 20_000_000
MAX_RECORDS = 100_000
MAX_COLUMNS = 200
MAX_FINDINGS = 5_000
SAMPLE_ROWS = 500
KINDS = ("Not checked", "Whole number", "Integer", "Number", "Text", "Identifier", "Date", "Boolean")
DATE_FORMATS = {
    "YYYY-MM-DD": ("%Y-%m-%d", r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    "DD/MM/YYYY": ("%d/%m/%Y", r"[0-9]{2}/[0-9]{2}/[0-9]{4}"),
    "MM/DD/YYYY": ("%m/%d/%Y", r"[0-9]{2}/[0-9]{2}/[0-9]{4}"),
    "DD-MM-YYYY": ("%d-%m-%Y", r"[0-9]{2}-[0-9]{2}-[0-9]{4}"),
    "MM-DD-YYYY": ("%m-%d-%Y", r"[0-9]{2}-[0-9]{2}-[0-9]{4}"),
    "YYYY/MM/DD": ("%Y/%m/%d", r"[0-9]{4}/[0-9]{2}/[0-9]{2}"),
}
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")
WORDS = dict(zip("zero one two three four five six seven eight nine ten eleven twelve".split(), map(str, range(13))))


@dataclass
class ColumnRule:
    kind: str = "Not checked"
    date_format: str | None = None
    allow_blank: bool = False
    reason: str = ""


@dataclass
class Report:
    source_sha256: str
    rules: dict
    rows_checked: int = 0
    issue_count: int = 0
    findings: list = field(default_factory=list)
    issue_counts: dict = field(default_factory=dict)
    complete: bool = True
    unchecked_columns: list = field(default_factory=list)
    file_error: str | None = None

    @property
    def status(self):
        if not self.complete:
            return "incomplete"
        if self.issue_count:
            return "issues_found"
        if self.unchecked_columns:
            return "partial_coverage"
        return "no_format_issues"

    def to_dict(self):
        return {**asdict(self), "status": self.status,
                "findings_truncated": self.issue_count > len(self.findings),
                "scope": "Confirmed types, date formats and blank-value rules only; no business correctness guarantee."}

    def add(self, line, column, entered, expected, code, suggestion):
        self.issue_count += 1
        self.issue_counts[code] = self.issue_counts.get(code, 0) + 1
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append(dict(line=line, column=column, entered=entered[:500],
                                      value_truncated=len(entered) > 500,
                                      expected=expected, code=code, suggestion=suggestion))


def reader(raw):
    return csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)


def headers_of(rows):
    headers = next(rows, [])
    if not headers:
        raise ValueError("The file has no header.")
    if len(headers) > MAX_COLUMNS:
        raise ValueError(f"The file exceeds {MAX_COLUMNS} columns.")
    normalized = [h.strip().casefold() for h in headers]
    if "" in normalized or len(set(normalized)) != len(normalized):
        raise ValueError("Headers must be nonempty and unique, ignoring surrounding spaces and case.")
    return headers


def valid_date(value, label):
    fmt, pattern = DATE_FORMATS[label]
    if not re.fullmatch(pattern, value):
        return False
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def matches(value, rule):
    if rule.kind == "Whole number":
        return bool(re.fullmatch(r"[0-9]+", value))
    if rule.kind == "Integer":
        return bool(re.fullmatch(r"[+-]?[0-9]+", value))
    if rule.kind == "Number":
        return bool(NUMBER.fullmatch(value))
    if rule.kind == "Text":
        return any(c.isalpha() for c in value)
    if rule.kind == "Identifier":
        return bool(value)
    if rule.kind == "Date":
        return valid_date(value, rule.date_format)
    if rule.kind == "Boolean":
        return value.casefold() in {"true", "false"}
    return False


def infer(header, values):
    # No LLM and no external transmission. These are suggestions, not business rules.
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", header)
    tokens = set(re.findall(r"[a-z0-9]+", words.lower()))
    vals = [v.strip() for v in values if v.strip()]
    rule = ColumnRule()
    if tokens & {"id", "sku", "code", "zip", "postcode", "postal", "phone", "account"}:
        rule.kind, rule.reason = "Identifier", "Heading suggests an identifier; preserve letters and leading zeros."
    elif tokens & {"date", "dob"}:
        rule.kind, rule.reason = "Date", "Heading suggests a date; confirm its single format."
    elif tokens & {"quantity", "qty", "count", "units", "stock", "age"}:
        rule.kind, rule.reason = "Whole number", "Heading suggests a non-negative count, with no decimal point."
    elif tokens & {"amount", "price", "cost", "sales", "revenue", "balance", "salary", "rate", "total"}:
        rule.kind, rule.reason = "Number", "Heading suggests a number; decimals and signs are accepted."
    elif tokens & {"name", "description", "city", "country", "title", "category"}:
        rule.kind, rule.reason = "Text", "Heading suggests text containing at least one letter."
    elif vals:
        for kind in ("Boolean", "Whole number", "Integer", "Number"):
            if sum(matches(v, ColumnRule(kind)) for v in vals) / len(vals) >= .8:
                rule.kind, rule.reason = kind, "At least 80% of nonempty sample values fit this type; confirm the intended meaning."
                break
        if rule.kind == "Not checked":
            if sum(any(valid_date(v, f) for f in DATE_FORMATS) for v in vals) / len(vals) >= .8:
                rule.kind, rule.reason = "Date", "Sample values resemble dates; confirm the intended format."
            elif all(any(c.isalpha() for c in v) for v in vals):
                rule.kind, rule.reason = "Text", "Sample values contain letters; confirm this is a text column."
    if rule.kind == "Date" and vals:
        scores = {fmt: sum(valid_date(v, fmt) for v in vals) for fmt in DATE_FORMATS}
        best = max(scores.values())
        choices = [fmt for fmt, score in scores.items() if score == best]
        if best and len(choices) == 1:
            rule.date_format = choices[0]
        else:
            rule.reason += " Format is ambiguous or unsupported; choose explicitly."
    if not rule.reason:
        rule.reason = "No reliable type suggestion; choose a type or leave this column explicitly unchecked."
    return rule


def suggest(raw):
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("The upload exceeds the 20 MB limit. Split it into smaller CSV files.")
    rows = reader(raw)
    headers = headers_of(rows)
    samples = {h: [] for h in headers}
    try:
        for i, row in enumerate(rows):
            if i >= SAMPLE_ROWS:
                break
            if len(row) == len(headers):
                for h, v in zip(headers, row):
                    samples[h].append(v)
    except csv.Error:
        # Full review records the partial scan; preserve earlier readable samples.
        pass
    return headers, {h: infer(h, samples[h]) for h in headers}


def check(raw, rules):
    report = Report(hashlib.sha256(raw).hexdigest(), {h: asdict(r) for h, r in rules.items()})
    try:
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("The upload exceeds the 20 MB limit; split the file.")
        rows = reader(raw)
        headers = headers_of(rows)
        if set(rules) != set(headers):
            raise ValueError("Confirm one type selection for each current column.")
        for rule in rules.values():
            if rule.kind not in KINDS or (rule.kind == "Date" and rule.date_format not in DATE_FORMATS):
                raise ValueError("Choose a valid type and a single format for every date column.")
        report.unchecked_columns = [h for h in headers if rules[h].kind == "Not checked"]
        while True:
            line = rows.line_num + 1
            row = next(rows, None)
            if row is None:
                break
            if report.rows_checked >= MAX_RECORDS:
                raise ValueError("The scan reached 100,000 records; split the file. Remaining rows were not checked.")
            report.rows_checked += 1
            if len(row) != len(headers):
                report.add(line, "(row)", repr(row), f"{len(headers)} fields", "field_count",
                           "Verify delimiters and quoting in the source export.")
                continue
            for h, value in zip(headers, row):
                rule = rules[h]
                if rule.kind == "Not checked":
                    continue
                stripped = value.strip()
                expected = rule.date_format if rule.kind == "Date" else rule.kind
                if not stripped:
                    if not rule.allow_blank:
                        report.add(line, h, value, expected, "missing_value", "Check the source; do not invent a missing value.")
                elif not matches(stripped, rule):
                    code = "invalid_date" if rule.kind == "Date" else "invalid_type"
                    proposal = WORDS.get(stripped.casefold()) if rule.kind in ("Whole number", "Integer", "Number") else None
                    suggestion = (f"Possible replacement: {proposal}. Verify the intended value in the source before changing it."
                                  if proposal is not None else "Check the source and the confirmed type; no reliable replacement is known.")
                    if rule.kind == "Date":
                        possible = [f for f in DATE_FORMATS if valid_date(stripped, f)]
                        suggestion = ("A different date format may be present. Verify its meaning, then use " + rule.date_format + " consistently."
                                      if possible else "Check that the date exists and uses " + rule.date_format + ".")
                    report.add(line, h, value, expected, code, suggestion)
        if report.rows_checked == 0:
            raise ValueError("The CSV has a header but no data records to review.")
    except (ValueError, UnicodeError, csv.Error) as exc:
        report.complete = False
        report.file_error = (str(exc) if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError)
                             else "Parsing stopped: check UTF-8 encoding, field sizes and CSV quoting. Later rows were not reviewed.")
    return report
