"""One standard unit per measurement (data/README.md): Length ft, Width in, Thickness mil, Weight lb.

A bare number gets its column's unit ("1000" -> "1000 ft"); a value in another unit is converted
("333.33 yds." -> "1000 ft"). Never a quiet fix: a conversion that would contradict the description
("300 in" on a "6 in. x 300 ft." tape) or leave the plausible range is not made; the value stays as it is and
rules.py flags it. Every change keeps its Sources row (origin + "unit normalised by the quality agent") and
gets a Note.
"""
import re

from rfq.models import Cell

STANDARD = {"Length": "ft", "Width": "in", "Thickness": "mil", "Weight": "lb"}
# factor to the standard unit
FACTORS = {
    "ft": {"ft": 1, "feet": 1, "foot": 1, "'": 1, "in": 1 / 12, "inch": 1 / 12, "inches": 1 / 12, '"': 1 / 12,
           "yd": 3, "yds": 3, "yard": 3, "yards": 3, "m": 3.28084, "meter": 3.28084, "meters": 3.28084,
           "metre": 3.28084, "metres": 3.28084},
    "in": {"in": 1, "inch": 1, "inches": 1, '"': 1, "ft": 12, "feet": 12, "mm": 1 / 25.4, "cm": 1 / 2.54},
    "mil": {"mil": 1, "mils": 1, "in": 1000, "inch": 1000, "mm": 39.3701, "micron": 0.0393701,
            "um": 0.0393701},
    "lb": {"lb": 1, "lbs": 1, "pound": 1, "pounds": 1, "oz": 1 / 16, "kg": 2.20462, "g": 0.00220462},
}
PLAUSIBLE = {"Length": (1, 5000), "Width": (0.5, 24), "Thickness": (0.5, 30), "Weight": (0.05, 200)}
MEASURE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(\"|'|[a-zA-Z]+\.?)?\s*$")
# What the description says for a column: "6 in. x 300 ft." -> Width 6, Length 300.
DESC_PATTERNS = {
    "Length": re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})*|\d+)\s*(?:ft\b\.?|feet\b|foot\b|')", re.I),
    "Width": re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:in\b\.?|inch(?:es)?\b|\"|-inch\b)", re.I),
    "Thickness": re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*mils?\b", re.I),
}


def fmt(number):
    """2 decimals at most; a value within 0.1% of a whole number is that number (999.99 -> 1000)."""
    whole = round(number)
    if whole and abs(number - whole) / abs(whole) < 0.001:
        return str(int(whole))
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def described(column, description):
    """Numbers the description gives for a column in its standard unit."""
    pattern = DESC_PATTERNS.get(column)
    if not pattern or not description:
        return []
    return [float(x.replace(",", "")) for x in pattern.findall(description)]


def standardise(column, value, description=""):
    """(new value, kind) where kind is "unit added" / "converted", or (value, None) if left alone."""
    target = STANDARD[column]
    m = MEASURE_RE.match(str(value))
    if not m:
        return value, None
    number = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "").lower().rstrip(".")
    if not unit:
        return f"{fmt(number)} {target}", "unit added"
    factor = FACTORS[target].get(unit)
    if factor is None:
        return value, None
    if factor == 1:
        new = f"{fmt(number)} {target}"
        return (new, "unit added") if new != value else (value, None)
    converted = number * factor
    low, high = PLAUSIBLE[column]
    says = described(column, description)
    if not low <= converted <= high:
        return value, None  # implausible after conversion: leave it, rules.py flags it
    if says and number in says and converted not in says:
        return value, None  # the number matches the description, the unit doesn't: a typo, not a conversion
    return f"{fmt(converted)} {target}", "converted"


def normalise(item, result):
    """Standardises one item's measurements in place. Returns how many cells changed."""
    changed = 0
    description = item.cells["Description"].value if "Description" in item.cells else ""
    for column in STANDARD:
        cell = item.cells.get(column)
        if cell is None or not cell.value:
            continue
        new, kind = standardise(column, cell.value, description)
        if kind is None:
            continue
        item.cells[column] = Cell(new, cell.source_type, cell.confidence,
                                  f"{cell.source} (unit normalised by the quality agent: {cell.value!s} -> {new})")
        what = "standard unit added" if kind == "unit added" else "converted to the standard unit"
        result.add_note(item, "quality", f'{column}: "{cell.value}" -> "{new}" ({what}).')
        changed += 1
    return changed
