"""Rule flags: missing or odd values, and descriptions that disagree with the specs.

Severity: high only for values that are probably wrong (they hold the RFQ for review); medium for values
worth a second look; info for things the buyer already sees (Not found items). Deterministic: same RFQ in,
same flags out, in item then column order.
"""
import re

from rfq import config
from rfq.models import Flag

KEY_COLUMNS = ("Description", "Length", "Width")          # missing on a Found row: high
USEFUL_COLUMNS = ("Thickness", "Material", "Color Finish")  # missing: medium
RANGES = {"Length": (1, 5000, "ft"), "Width": (0.5, 24, "in"), "Thickness": (0.5, 30, "mil"),
          "Weight": (0.1, 200, "lb")}
COLORS = ("red", "blue", "yellow", "green", "orange", "purple", "white", "black", "brown", "pink", "silver",
          "gray", "grey")
NUM_UNIT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(ft|in|mil|lb)$")
# "6 in", "6 in.", '6"', "6-inch" for width; "1000 ft", "1000 ft.", "1,000'" for length
WIDTH_IN_DESC = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:in\b\.?|inch(?:es)?\b|\"|-inch\b)", re.I)
LENGTH_IN_DESC = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})*|\d+)\s*(?:ft\b\.?|feet\b|foot\b|')", re.I)


def _flag(flags, item, column, value, issue, rule, severity):
    flags.append(Flag(id=f"{item.index}:{column}:{rule}", product_id=item.product_id, column=column,
                      value=value, issue=issue, rule=rule, severity=severity))


def _number(value):
    m = NUM_UNIT_RE.match(str(value).strip())
    return float(m.group(1)) if m else None


def check_item(item):
    flags = []
    if not item.found:
        _flag(flags, item, "Lookup Status", config.NOT_FOUND, item.reason or "Not found in any source.",
              "not_found", "info")
        return flags
    cells = {c: cell.value for c, cell in item.cells.items()}

    for column in KEY_COLUMNS:
        if not cells.get(column):
            _flag(flags, item, column, "", f"{column} is missing on a found product.", "missing_key_value",
                  "high")
    for column in USEFUL_COLUMNS:
        if not cells.get(column):
            _flag(flags, item, column, "", f"{column} is missing.", "missing_value", "medium")

    for column, value in cells.items():
        if str(value).strip() in ("[]", "{}", "null", "None", "N/A", "-"):
            _flag(flags, item, column, value, "Empty placeholder instead of a value.", "placeholder", "medium")

    for column, (low, high, unit) in RANGES.items():
        value = cells.get(column)
        if not value:
            continue
        number = _number(value)
        if number is None:
            _flag(flags, item, column, value, f"Not a plain measurement in {unit}.", "not_numeric", "medium")
        elif not low <= number <= high:
            _flag(flags, item, column, value, f"Outside the usual range for tape ({low}-{high} {unit}).",
                  "out_of_range", "high")

    desc = cells.get("Description", "")
    if desc:
        width = _number(cells.get("Width", ""))
        found_w = [float(w) for w in WIDTH_IN_DESC.findall(desc)]
        if width is not None and found_w and width not in found_w:
            _flag(flags, item, "Width", cells["Width"],
                  f'The description says {", ".join(_fmt(w) for w in found_w)} in.', "description_mismatch", "high")
        length = _number(cells.get("Length", ""))
        found_l = [float(x.replace(",", "")) for x in LENGTH_IN_DESC.findall(desc)]
        if length is not None and found_l and length not in found_l:
            _flag(flags, item, "Length", cells["Length"],
                  f'The description says {", ".join(_fmt(x) for x in found_l)} ft.', "description_mismatch",
                  "high")
        color = cells.get("Color Finish", "")
        named = [c for c in COLORS if re.search(rf"\b{c}\b", desc, re.I)]
        if color and named and not any(re.search(rf"\b{c}\b", color, re.I) for c in named):
            _flag(flags, item, "Color Finish", color, f'The description says {", ".join(named)}.',
                  "description_mismatch", "medium")
    return flags


def _fmt(number):
    return f"{number:g}"


def check(result):
    flags = []
    for item in result.items:
        flags.extend(check_item(item))
    return flags
