"""Storage and display rules for custom field types."""
from __future__ import annotations

from datetime import date
import re

FIELD_TYPES = ("Text", "Date")
FIELD_TYPE_LABELS = {"Text": "Text / Number", "Date": "Date"}
DATE_FORMATS = ("DD/MM/YYYY", "MM/DD/YYYY", "YYYY/MM/DD")
DATE_PATTERNS = dict(zip(DATE_FORMATS, ("%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d")))


def parse_saved_date(value: str) -> date | None:
    # Never infer locale or century from legacy text such as 1/2/94.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize_value(field_type: str, value) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "" if field_type != "Text" else (value or "")
    if field_type == "Text":
        return str(value)
    if field_type == "Date":
        parsed = value if type(value) is date else parse_saved_date(str(value))
        if parsed is None:
            raise ValueError("Choose a valid date using the calendar before saving.")
        return parsed.isoformat()
    raise ValueError("Unknown field type.")


def widget_value(field: dict, saved: str):
    if field["field_type"] == "Date":
        return parse_saved_date(saved)
    return saved


def display_value(field: dict, saved: str) -> str:
    if not saved.strip():
        return "-"
    if field["field_type"] == "Date":
        parsed = parse_saved_date(saved)
        if parsed:
            return parsed.strftime(DATE_PATTERNS[field["date_format"]])
    return saved
