"""One standard unit per measurement (data/README.md): Length ft, Width in, Thickness mil, Weight lb.

A bare number gets its column's unit ("1000" -> "1000 ft"); a value in another unit is converted
("300 in" -> "25 ft"). The Sources row keeps its origin and says the quality agent normalised it, and
every change gets a Notes row. Values that aren't a plain measurement are left alone (rules.py flags them).
"""
import re

from rfq.models import Cell

STANDARD = {"Length": "ft", "Width": "in", "Thickness": "mil", "Weight": "lb"}
# factor to the standard unit
FACTORS = {
    "ft": {"ft": 1, "feet": 1, "foot": 1, "'": 1, "in": 1 / 12, "inch": 1 / 12, "inches": 1 / 12, '"': 1 / 12,
           "yd": 3, "yard": 3, "yards": 3, "m": 3.28084, "meter": 3.28084, "meters": 3.28084},
    "in": {"in": 1, "inch": 1, "inches": 1, '"': 1, "ft": 12, "feet": 12, "mm": 1 / 25.4, "cm": 1 / 2.54},
    "mil": {"mil": 1, "mils": 1, "in": 1000, "inch": 1000, "mm": 39.3701, "micron": 0.0393701,
            "um": 0.0393701},
    "lb": {"lb": 1, "lbs": 1, "pound": 1, "pounds": 1, "oz": 1 / 16, "kg": 2.20462, "g": 0.00220462},
}
MEASURE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(\"|'|[a-zA-Z]+\.?)?\s*$")


def _fmt(number):
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def standardise(column, value):
    """(new value, kind) where kind is "unit added" / "converted", or (value, None) if unchanged."""
    target = STANDARD[column]
    m = MEASURE_RE.match(str(value))
    if not m:
        return value, None
    number, unit = float(m.group(1)), (m.group(2) or "").lower().rstrip(".")
    if not unit:
        return f"{_fmt(number)} {target}", "unit added"
    factor = FACTORS[target].get(unit)
    if factor is None:
        return value, None
    if factor == 1:
        new = f"{_fmt(number)} {target}"
        return (new, "unit added") if new != value else (value, None)
    return f"{_fmt(number * factor)} {target}", "converted"


def normalise(item, result):
    """Standardises one item's measurements in place. Returns how many cells changed."""
    changed = 0
    for column in STANDARD:
        cell = item.cells.get(column)
        if cell is None or not cell.value:
            continue
        new, kind = standardise(column, cell.value)
        if kind is None:
            continue
        item.cells[column] = Cell(new, cell.source_type, cell.confidence,
                                  f"{cell.source} (unit normalised by the quality agent: {cell.value!s} -> {new})")
        what = "standard unit added" if kind == "unit added" else "converted to the standard unit"
        result.add_note(item, "quality", f'{column}: "{cell.value}" -> "{new}" ({what}).')
        changed += 1
    return changed
