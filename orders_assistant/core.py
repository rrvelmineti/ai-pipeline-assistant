"""Deterministic CSV validation. No model participates in calculations."""
import csv
import hashlib
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

MAX_BYTES = 2_000_000
MAX_ROWS = 10_000
RULES = {
    "input_unreadable": ("The input file could not be read.", "Check the path and file permissions."),
    "input_too_large": ("The CSV exceeds the 2 MB limit.", "Split the export into smaller files."),
    "invalid_csv": ("The input is not a valid UTF-8 CSV.", "Export the source again as UTF-8 CSV."),
    "invalid_headers": ("The headers must be quantity,unit_price, each exactly once.", "Compare the header with the sample CSV."),
    "empty_orders": ("The CSV contains no orders.", "Add at least one order from the source system."),
    "too_many_rows": ("The CSV exceeds 10,000 orders.", "Split the export into smaller files."),
    "invalid_row": ("The row must contain exactly two fields.", "Check commas and missing fields in this row."),
    "invalid_quantity": ("Quantity must be a whole number from 1 to 1,000,000.", "Verify the quantity in the source system; do not guess a replacement."),
    "invalid_price": ("Unit price must be a non-negative decimal with at most two decimal places, no greater than 1,000,000.", "Verify the unit price in the source system; use a dot as the decimal separator."),
}


def analyze(path):
    """Return a complete evidence record, including failures. CSV rows are physical lines."""
    record = {"schema_version": 1, "run_id": str(uuid4()),
              "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "error", "stage": "ingestion", "source_sha256": None,
              "rows_processed": 0, "total_sales": None, "error": None}

    def fail(code, row=None, field=None):
        problem, next_check = RULES[code]
        record["error"] = {"code": code, "row": row, "field": field,
                           "problem": problem, "next_check": next_check,
                           "underlying_cause": None}
        return record

    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
    except OSError:
        return fail("input_unreadable")
    if len(raw) > MAX_BYTES:
        return fail("input_too_large")
    record["source_sha256"] = hashlib.sha256(raw).hexdigest()
    record["stage"] = "validation"
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        headers = next(reader, [])
        if len(headers) != 2 or set(headers) != {"quantity", "unit_price"}:
            return fail("invalid_headers", 1)
        total = Decimal("0.00")
        for count, values in enumerate(reader, 1):
            row = reader.line_num
            if count > MAX_ROWS:
                return fail("too_many_rows", row)
            if len(values) != 2:
                return fail("invalid_row", row)
            order = dict(zip(headers, values))
            quantity, price = order["quantity"].strip(), order["unit_price"].strip()
            if not re.fullmatch(r"[0-9]{1,7}", quantity) or not 1 <= int(quantity) <= 1_000_000:
                return fail("invalid_quantity", row, "quantity")
            if not re.fullmatch(r"[0-9]{1,7}(?:\.[0-9]{1,2})?", price) or Decimal(price) > 1_000_000:
                return fail("invalid_price", row, "unit_price")
            total += int(quantity) * Decimal(price)
            record["rows_processed"] = count
        if not record["rows_processed"]:
            return fail("empty_orders")
    except (UnicodeError, csv.Error):
        return fail("invalid_csv")
    record.update(status="success", stage="completed", total_sales=f"{total:.2f}")
    return record
