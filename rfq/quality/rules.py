"""Rule flags (by code): missing values, odd values, wrong units, and values that contradict the row.

Severity:
- high: probably wrong; holds the RFQ for review (wrong unit, out of range, a measurement that disagrees
  with the description, a blank Description/Length/Width on a found product);
- medium: worth a second look (placeholders, non-numeric measurements, colour or application that disagree);
- low: a blank cell (missing): counted for the fill rate, greyed in the Excel, never holds the RFQ;
- info: a Not found item (the buyer already sees it).
Deterministic: same RFQ in, same flags out, in item then column order. Flags never change a value.
"""
import re

from rfq import config
from rfq.models import Flag
from rfq.quality.units import FACTORS, PLAUSIBLE, STANDARD, described

KEY_COLUMNS = ("Description", "Length", "Width")
CHECK_COLUMNS = [c for c in config.SPEC_COLUMNS if c != "Image"]  # Image mirrors Picture
COLORS = ("red", "yellow", "blue", "green", "orange", "purple", "white", "black", "brown", "pink", "silver",
          "gray", "grey")
NUM_UNIT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(\"|'|[a-zA-Z]+\.?)?$")
# APWA utility groups. "Reclaimed water" is its own group; storm drains and force mains count as sewer.
UTILITIES = [
    ("reclaimed", r"reclaimed|irrigation|slurry", "purple"),
    ("sewer", r"sewer|storm|drain|force main", "green"),
    ("gas", r"\bgas\b|\boil\b|steam", "yellow"),
    ("electric", r"electric|power", "red"),
    ("telecom", r"fiber|fibre|optic|telecom|communication|\bcable\b", "orange"),
    ("water", r"water|potable", "blue"),
]


def _flag(flags, item, column, value, issue, rule, severity):
    flags.append(Flag(id=f"{item.index}:{column}:{rule}", product_id=item.product_id, column=column,
                      value=value, issue=issue, rule=rule, severity=severity))


def utilities(text):
    """APWA utility groups named in a text ("reclaimed water" counts as reclaimed only)."""
    t = str(text or "").lower()
    found = []
    for name, pattern, _ in UTILITIES:
        if re.search(pattern, t):
            found.append(name)
            if name == "reclaimed":
                t = re.sub(r"water", " ", t)
    return found


def _measure(value):
    m = NUM_UNIT_RE.match(str(value).strip())
    if not m:
        return None, None
    return float(m.group(1)), (m.group(2) or "").lower().rstrip(".")


def _fmt(number):
    return f"{number:g}"


def check_item(item):
    flags = []
    if not item.found:
        _flag(flags, item, "Lookup Status", config.NOT_FOUND, item.reason or "Not found in any source.",
              "not_found", "info")
        return flags
    cells = {c: cell.value for c, cell in item.cells.items()}
    desc = cells.get("Description", "")

    for column in CHECK_COLUMNS:  # every blank is a missing value
        if not cells.get(column):
            if column in KEY_COLUMNS:
                _flag(flags, item, column, "", f"{column} is missing on a found product.", "missing_key_value",
                      "high")
            else:
                _flag(flags, item, column, "", f"{column} is blank: no source gave a value.", "missing", "low")

    for column, value in cells.items():
        if str(value).strip() in ("[]", "{}", "null", "None", "N/A", "-"):
            _flag(flags, item, column, value, "Empty placeholder instead of a value.", "placeholder", "medium")

    for column, unit in STANDARD.items():
        value = cells.get(column)
        if not value:
            continue
        number, given = _measure(value)
        low, high = PLAUSIBLE[column]
        says = described(column, desc)
        if number is None:
            _flag(flags, item, column, value, f"Not a plain measurement in {unit}.", "not_numeric", "medium")
        elif given and given != unit and given in FACTORS[unit]:
            reason = f"{column} is given in {given}; the standard is {unit}."
            if says:
                reason += f" The description says {', '.join(_fmt(s) for s in says)} {unit}."
            _flag(flags, item, column, value, reason + " Left unchanged for a person to check.", "wrong_unit",
                  "high")
        elif not low <= number <= high:
            _flag(flags, item, column, value, f"Outside the usual range for tape ({low}-{high} {unit}).",
                  "out_of_range", "high")
        elif says and number not in says:
            _flag(flags, item, column, value,
                  f"The description says {', '.join(_fmt(s) for s in says)} {unit}.", "description_mismatch", "high")

    color = cells.get("Color Finish", "")
    named = [c for c in COLORS if re.search(rf"\b{c}\b", desc, re.I)]
    if color and named and not any(re.search(rf"\b{c}\b", color, re.I) for c in named):
        _flag(flags, item, "Color Finish", color, f'The description says {", ".join(named)}.',
              "description_mismatch", "medium")

    application = cells.get("Application", "")
    marked = utilities(cells.get("Lettering", "")) or utilities(desc)
    applied = utilities(application)
    if application and marked and applied and not set(marked) & set(applied):
        colour_of = {name: c for name, _, c in UTILITIES}
        evidence = "Lettering" if utilities(cells.get("Lettering", "")) else "Description"
        reason = (f"Application says {', '.join(applied)}, but the {evidence} says {', '.join(marked)}")
        if color and colour_of.get(marked[0]) == color.lower():
            reason += f" (and {color} is the APWA colour for {marked[0]})"
        _flag(flags, item, "Application", application, reason + ".", "application_mismatch", "medium")
    return flags


def check(result):
    flags = []
    for item in result.items:
        flags.extend(check_item(item))
    return flags
