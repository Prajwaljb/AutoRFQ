"""How sources combine: live wins over the catalog, and every difference goes to the Notes sheet;
spec sheets only fill cells that are still blank, and a disagreement with a filled cell is noted."""
import re

LIST_COLUMNS = {"ASTM", "OSHA", "Application", "Material", "Product details"}
# Spec sheets describe the material's make-up ("Polyethylene Film") where the RFQ uses a category
# ("Plastic"): fill a blank, but a different wording is not a disagreement.
NO_SPEC_CONFLICT = {"Material"}


def _norm(value):
    return " ".join(str(value).lower().replace(".", "").split())


def _codes(value):
    """List cells as a set of codes, ignoring order and years ("ASTM D-2103 2008" == "ASTM D-2103")."""
    parts = re.split(r"[|;]", str(value))
    return {_norm(re.sub(r"\s+(19|20)\d\d$", "", p.strip())) for p in parts if p.strip()}


DEFAULT_UNITS = {"Length": "ft", "Width": "in", "Thickness": "mil", "Weight": "lb"}
UNIT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(ft|in|mil|lb)?$")


def same(column, a, b):
    """True if two values say the same thing: same list items, same number with or without its unit,
    or (Image / Picture) one URL out of the other's list."""
    if column in LIST_COLUMNS:
        return _codes(a) == _codes(b)
    if column in ("Image", "Picture"):
        return bool(_codes(a) & _codes(b))
    ma, mb = UNIT_RE.match(_norm(a)), UNIT_RE.match(_norm(b))
    if ma and mb:  # a bare number has the column's standard unit (data/README.md)
        unit = DEFAULT_UNITS.get(column)
        return float(ma.group(1)) == float(mb.group(1)) and (ma.group(2) or unit) == (mb.group(2) or unit)
    return _norm(a) == _norm(b)


def live_over_catalog(item, live, catalog, result):
    """Cells for an item found on both. Columns the page doesn't show keep the catalog value."""
    cells = dict(catalog)
    for column, cell in live.items():
        old = catalog.get(column)
        if old is not None and not same(column, old.value, cell.value):
            result.add_note(item, "lookup", f'{column}: ferguson.com shows "{cell.value}", the catalog has '
                                            f'"{old.value}"; used the live value.')
        cells[column] = cell
    return cells


def fill_from_spec(item, spec, result):
    """Adds spec sheet values to blank cells. Returns how many cells were filled."""
    filled = 0
    for column, cell in spec.items():
        current = item.cells.get(column)
        if current is None or current.value == "":
            item.cells[column] = cell
            filled += 1
        elif column in NO_SPEC_CONFLICT:
            continue
        elif column in LIST_COLUMNS:
            if not _codes(current.value) & _codes(cell.value):
                result.add_note(item, "spec", f'{column}: the spec sheet says "{cell.value}", kept '
                                              f'"{current.value}" ({current.source_type}).')
        elif not same(column, current.value, cell.value):
            result.add_note(item, "spec", f'{column}: the spec sheet says "{cell.value}", kept '
                                          f'"{current.value}" ({current.source_type}).')
    return filled
