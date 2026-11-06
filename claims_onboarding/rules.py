"""Plain-language onboarding rules: parse them, then check every row with code (not AI)."""
import csv
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from orders_assistant.csv_check import DATE_FORMATS, MAX_FILE_BYTES, MAX_RECORDS, headers_of, reader

RULES_PATH = Path(__file__).with_name("rules.txt")
MAX_FINDINGS = 5_000
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")
# ICD-10-CM shape: a letter (not U), a digit, an alphanumeric, then an optional dot and 1-4 more.
ICD10 = re.compile(r"[A-TV-Z][0-9][0-9A-Z](?:\.?[0-9A-Z]{1,4})?")
BLOCKER, WARNING = "blocker", "warning"


class RulesError(ValueError):
    """A rules file line could not be understood. The message names the line."""


@dataclass
class Rule:
    name: str            # canonical name, e.g. "exactly_digits"
    text: str            # the phrase as the business user wrote it
    severity: str = BLOCKER
    arg: object = None


@dataclass
class FieldSpec:
    name: str
    description: str
    rules: list = field(default_factory=list)

    @property
    def required(self):
        return any(r.name == "required" for r in self.rules)

    def rule(self, name):
        return next((r for r in self.rules if r.name == name), None)


def _parse_rule(phrase, line_no):
    text = phrase.strip()
    severity = BLOCKER
    match = re.fullmatch(r"(.*?)\s*\(warning\)", text, re.IGNORECASE)
    if match:
        text, severity = match.group(1).strip(), WARNING
    low = text.casefold()
    simple = {"required": "required", "unique": "unique", "number": "number",
              "whole number": "whole_number", "not negative": "not_negative",
              "not in the future": "not_future", "icd-10 format": "icd10"}
    if low in simple:
        return Rule(simple[low], text, severity)
    if m := re.fullmatch(r"exactly (\d+) digits?", low):
        return Rule("exactly_digits", text, severity, int(m.group(1)))
    if m := re.fullmatch(r"exactly (\d+) characters?", low):
        return Rule("exactly_chars", text, severity, int(m.group(1)))
    if m := re.fullmatch(r"date (\S+)", text, re.IGNORECASE):
        fmt = m.group(1).upper()
        if fmt not in DATE_FORMATS:
            raise RulesError(f"Line {line_no}: unknown date format '{m.group(1)}'. Use one of {', '.join(DATE_FORMATS)}.")
        return Rule("date", text, severity, fmt)
    if m := re.fullmatch(r"not before ([a-z0-9_]+)", low):
        return Rule("not_before", text, severity, m.group(1))
    if m := re.fullmatch(r"not greater than ([a-z0-9_]+)", low):
        return Rule("not_greater_than", text, severity, m.group(1))
    if m := re.fullmatch(r"one of (.+)", text, re.IGNORECASE):
        options = [o.strip() for o in m.group(1).split("/") if o.strip()]
        if len(options) < 2:
            raise RulesError(f"Line {line_no}: 'one of' needs at least two values separated by slashes.")
        return Rule("one_of", text, severity, [o.casefold() for o in options])
    raise RulesError(f"Line {line_no}: the rule '{phrase.strip()}' is not recognised. See the list at the top of the rules file.")


def parse_rules(text):
    """Parse the business-editable rules text into field specs, rejecting anything unclear."""
    specs = {}
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            raise RulesError(f"Line {line_no}: expected 'field | description | rules'.")
        name, description, rule_text = parts
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise RulesError(f"Line {line_no}: field names use lowercase letters, digits and underscores.")
        if name in specs:
            raise RulesError(f"Line {line_no}: '{name}' is listed twice.")
        rules = [_parse_rule(p, line_no) for p in rule_text.split(",") if p.strip()]
        names = [r.name for r in rules]
        dupes = [n for n, c in Counter(names).items() if c > 1]
        if dupes:
            raise RulesError(f"Line {line_no}: the same kind of rule appears twice for '{name}'.")
        if sum(n in {"number", "whole_number", "date"} for n in names) > 1:
            raise RulesError(f"Line {line_no}: choose only one of number, whole number or date for '{name}'.")
        specs[name] = FieldSpec(name, description, rules)
    if not specs:
        raise RulesError("The rules file has no fields.")
    for spec in specs.values():
        for rule in spec.rules:
            if rule.name in {"not_before", "not_greater_than"}:
                other = specs.get(rule.arg)
                if other is None:
                    raise RulesError(f"'{spec.name}' refers to '{rule.arg}', which is not a field in the rules file.")
                wanted = "date" if rule.name == "not_before" else "number"
                if not other.rule(wanted) or not spec.rule(wanted):
                    raise RulesError(f"'{spec.name} {rule.text}' compares fields that are not both {wanted}s.")
    return specs


def load_rules(path=RULES_PATH):
    return parse_rules(Path(path).read_text(encoding="utf-8"))


@dataclass
class ValidationReport:
    source_sha256: str
    rows_checked: int = 0
    complete: bool = True
    file_error: str | None = None
    findings: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)  # (field, rule text, severity) -> count

    @property
    def blockers(self):
        return sum(c for (_, _, sev), c in self.counts.items() if sev == BLOCKER)

    @property
    def warnings(self):
        return sum(c for (_, _, sev), c in self.counts.items() if sev == WARNING)

    def add(self, line, spec, column, value, rule, message):
        self.counts[(spec.name, rule.text, rule.severity)] += 1
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append({"line": line, "field": spec.name, "client_column": column,
                                  "entered": value[:200], "rule": rule.text,
                                  "severity": rule.severity, "message": message})


def _parse_value(spec, value):
    """Return the typed value used by cross-field rules, or None if it cannot be typed."""
    if (r := spec.rule("date")) and _valid_date(value, r.arg):
        return datetime.strptime(value, DATE_FORMATS[r.arg][0]).date()
    if (spec.rule("number") and NUMBER.fullmatch(value)) or (spec.rule("whole_number") and value.isdigit()):
        return float(value)
    return None


def _valid_date(value, label):
    fmt, pattern = DATE_FORMATS[label]
    if not re.fullmatch(pattern, value):
        return False
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def _single_value_problem(rule, value, today):
    """Check a rule that needs only this cell. Returns a message, or None if it passes."""
    n = rule.name
    if n == "number" and not NUMBER.fullmatch(value):
        return "Not a plain number. Remove currency symbols, commas and words."
    if n == "whole_number" and not value.isdigit():
        return "Not a whole number."
    if n == "not_negative" and NUMBER.fullmatch(value) and float(value) < 0:
        return "Negative value."
    if n == "exactly_digits" and not re.fullmatch(rf"[0-9]{{{rule.arg}}}", value):
        return f"Expected exactly {rule.arg} digits; found {len(value)} characters."
    if n == "exactly_chars" and len(value) != rule.arg:
        return f"Expected exactly {rule.arg} characters; found {len(value)}."
    if n == "date" and not _valid_date(value, rule.arg):
        return f"Not a valid date in {rule.arg} format."
    if n == "icd10" and not ICD10.fullmatch(value.upper()):
        return "Does not look like an ICD-10-CM code (for example E11.9)."
    if n == "one_of" and value.casefold() not in rule.arg:
        return "Not one of the allowed values: " + " / ".join(rule.arg) + "."
    return None


def validate(raw, mapping, specs, today=None):
    """Check every readable row. mapping: target field -> client column (or None)."""
    today = today or date.today()
    report = ValidationReport(hashlib.sha256(raw).hexdigest())
    try:
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("The upload exceeds the 20 MB limit; split the file.")
        rows = reader(raw)
        headers = headers_of(rows)
        missing = [f for f, s in specs.items() if s.required and not mapping.get(f)]
        if missing:
            raise ValueError("Map every required field before validating: " + ", ".join(missing) + ".")
        used = [c for c in mapping.values() if c]
        if len(used) != len(set(used)):
            raise ValueError("Each client column can be mapped to only one target field.")
        if unknown := [c for c in used if c not in headers]:
            raise ValueError("Mapped columns are not in this file: " + ", ".join(unknown) + ".")
        position = {h: i for i, h in enumerate(headers)}
        mapped = {f: mapping[f] for f in specs if mapping.get(f)}
        seen = {f: {} for f, s in specs.items() if s.rule("unique") and f in mapped}
        while True:
            line = rows.line_num + 1
            row = next(rows, None)
            if row is None:
                break
            if report.rows_checked >= MAX_RECORDS:
                raise ValueError("The scan reached 100,000 records; split the file. Remaining rows were not checked.")
            report.rows_checked += 1
            if len(row) != len(headers):
                spec = FieldSpec("(row)", "Whole row")
                report.add(line, spec, "(row)", f"{len(row)} fields",
                           Rule("row_shape", "correct number of fields"), f"Expected {len(headers)} fields; check delimiters and quoting.")
                continue
            values = {f: row[position[c]].strip() for f, c in mapped.items()}
            typed = {}
            for f, value in values.items():
                spec, column = specs[f], mapped[f]
                if not value:
                    if r := spec.rule("required"):
                        report.add(line, spec, column, row[position[column]], r, "Missing value. Ask the client for it; do not guess.")
                    continue
                for rule in spec.rules:
                    if rule.name in {"required", "not_before", "not_greater_than", "not_future", "unique"}:
                        continue
                    if (msg := _single_value_problem(rule, value, today)):
                        report.add(line, spec, column, value, rule, msg)
                typed[f] = _parse_value(spec, value)
                if (r := spec.rule("not_future")) and isinstance(typed[f], date) and typed[f] > today:
                    report.add(line, spec, column, value, r, f"Date is after today ({today.isoformat()}).")
                if f in seen:
                    key = value.casefold()
                    if key in seen[f]:
                        report.add(line, spec, column, value, spec.rule("unique"),
                                   f"Duplicate of line {seen[f][key]}.")
                    else:
                        seen[f][key] = line
            for f, value in typed.items():
                spec = specs[f]
                for rule in spec.rules:
                    if rule.name not in {"not_before", "not_greater_than"}:
                        continue
                    other = typed.get(rule.arg)
                    if value is None or other is None:
                        continue  # a type problem was already reported, or the other field is blank/unmapped
                    if rule.name == "not_before" and value < other:
                        report.add(line, spec, mapped[f], values[f], rule,
                                   f"Earlier than {rule.arg} ({values[rule.arg]}).")
                    if rule.name == "not_greater_than" and value > other:
                        report.add(line, spec, mapped[f], values[f], rule,
                                   f"Greater than {rule.arg} ({values[rule.arg]}).")
        if report.rows_checked == 0:
            raise ValueError("The CSV has a header but no data rows.")
    except (ValueError, UnicodeError, csv.Error) as exc:
        report.complete = False
        report.file_error = (str(exc) if type(exc) is ValueError
                             else "Parsing stopped: check UTF-8 encoding and CSV quoting. Later rows were not checked.")
    return report
