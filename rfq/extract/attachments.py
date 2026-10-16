"""Reads item lists from attachments: .xlsx / .xlsm (openpyxl, read-only) and .csv.

Returns ([(cell text, row label, qty)], [problem notes]). Never raises for a bad file: a file that can't be
read becomes a note asking the sender to resend it.
"""
import csv
import io
import re
from pathlib import PurePath

from rfq.config import MAX_ATTACHMENT_BYTES, MAX_SHEET_ROWS

ITEM_HEADER_RE = re.compile(r"\b(item|product|sku|part|id)\b", re.IGNORECASE)
QTY_HEADER_RE = re.compile(r"\b(qty|quantity)\b(?:\s*\(([^)]+)\))?", re.IGNORECASE)
SPREADSHEET_EXT = {".xlsx", ".xlsm"}
UNREADABLE_EXT = {".xls", ".ods", ".numbers", ".xlsb"}
WHOLE_FLOAT_RE = re.compile(r"^(\d+)\.0+$")


def cell_text(value):
    """A sheet value as text: whole floats lose the .0, "#" and spaces are dropped."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    m = WHOLE_FLOAT_RE.match(text)
    if m:
        text = m.group(1)
    return text.lstrip("#").strip()


def _rows_to_values(rows, label):
    """rows: list of lists of raw values. Uses the item column if a header names one."""
    rows = rows[:MAX_SHEET_ROWS]
    header_index, item_cols, qty_col, qty_unit = None, [], None, ""
    for r, row in enumerate(rows[:10]):
        texts = [cell_text(v) for v in row]
        cols = [c for c, t in enumerate(texts) if t and ITEM_HEADER_RE.search(t) and not t.isdigit()]
        if cols:
            header_index, item_cols = r, cols
            for c, t in enumerate(texts):
                m = QTY_HEADER_RE.search(t or "")
                if m:
                    qty_col, qty_unit = c, (m.group(2) or "").strip()
                    break
            break

    def qty_of(row):
        if qty_col is None or qty_col >= len(row):
            return ""
        q = cell_text(row[qty_col])
        return f"{q} {qty_unit}".strip() if q else ""

    if header_index is None:  # no header: every cell, row by row
        return [(cell_text(v), f"{label} row {r + 1}", "") for r, row in enumerate(rows) for v in row
                if cell_text(v)]

    # Several columns may look like item columns ("Item number", "Product description"): use the one
    # that holds the most item-like values.
    def score(col):
        return sum(1 for row in rows[header_index + 1:] if col < len(row)
                   and re.fullmatch(r"[A-Za-z0-9#\-. ]{4,20}", cell_text(row[col]) or "-"))
    col = max(item_cols, key=score)
    return [(cell_text(row[col]), f"{label} row {r + header_index + 2}", qty_of(row))
            for r, row in enumerate(rows[header_index + 1:]) if col < len(row) and cell_text(row[col])]


def read_xlsx(data, name):
    import openpyxl  # imported here so a missing openpyxl only affects attachments
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    values = []
    try:
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append(list(row))
                if len(rows) >= MAX_SHEET_ROWS:
                    break
            label = name if len(wb.worksheets) == 1 else f"{name} sheet {ws.title}"
            values.extend(_rows_to_values(rows, label))
    finally:
        wb.close()
    return values


def read_csv(data, name):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    return _rows_to_values(rows, name)


def read_attachment(name, data):
    """Item values in one attachment, plus notes for anything that could not be read."""
    ext = PurePath(name or "").suffix.lower()
    if ext not in SPREADSHEET_EXT | UNREADABLE_EXT | {".csv"}:
        return [], []  # images, signatures, PDFs: not item lists in the base
    if len(data) > MAX_ATTACHMENT_BYTES:
        return [], [f"Attachment {name} is larger than 10 MB and was not read; please send a smaller file."]
    if ext in UNREADABLE_EXT:
        return [], [f"Could not read attachment {name}; please resend it as .xlsx or .csv."]
    try:
        values = read_csv(data, name) if ext == ".csv" else read_xlsx(data, name)
    except Exception as e:  # corrupt, password-protected, not really a spreadsheet
        return [], [f"Could not read attachment {name} ({type(e).__name__}); please resend it as .xlsx."]
    return values, []
