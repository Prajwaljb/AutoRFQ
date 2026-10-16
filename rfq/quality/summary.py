"""The Summary sheet: status, counts, fill rate, request lines, alerts, flags and AI suggestions.

No timings: the same RFQ always gives the same Summary.
"""
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill

from rfq import config

FILL_COLUMNS = [c for c in config.SPEC_COLUMNS if c != "Image"]  # Image mirrors Picture
NAVY, MIST = "00446A", "E6ECF0"
TITLE = Font(name="Inter", bold=True, size=14, color=NAVY)
SECTION = Font(name="Inter", bold=True, size=12, color=NAVY)
HEAD_FONT = Font(name="Inter", bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", start_color=NAVY, end_color=NAVY)
STATUS_TEXT = {"ready": "Ready", "needs_review": "Needs human review", "approved": "Approved",
               "sent": "Sent", "failed": "Processing error", "fallback_sent": "Processing error"}


def fill_rates(result):
    """(overall %, [(column, filled, total, %)]) over found items."""
    found = [i for i in result.items if i.found]
    rows = []
    filled_total = 0
    for column in FILL_COLUMNS:
        filled = sum(1 for i in found if column in i.cells and i.cells[column].value)
        filled_total += filled
        rows.append((column, filled, len(found), round(100 * filled / len(found), 1) if found else 0.0))
    cells = len(found) * len(FILL_COLUMNS)
    return (round(100 * filled_total / cells, 1) if cells else 0.0), rows


def _money(text):
    try:
        return float(str(text).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def request_lines(result):
    """[(id, description, qty, unit price, line total, price source)] and the estimated total."""
    lines, total = [], 0.0
    for item in result.items:
        if not item.found:
            continue
        price = _money(item.extra.get("Price (USD)", ""))
        qty_num = None
        if item.qty:
            try:
                qty_num = float(item.qty.split()[0])
            except ValueError:
                qty_num = None
        line_total = round(price * qty_num, 2) if price is not None and qty_num is not None else None
        if line_total is not None:
            total += line_total
        source = "ferguson.com (live)" if item.found_via == "live" else f"catalog list price, {config.CATALOG_DATE}"
        desc = item.cells["Description"].value if "Description" in item.cells else ""
        lines.append((item.product_id, desc, item.qty, price, line_total, source if price is not None else ""))
    return lines, round(total, 2)


def alerts(result):
    out = []
    for item in result.items:
        if item.found and item.extra.get("Availability") == "OutOfStock":
            out.append((item.product_id, "Out of stock: lead-time risk."))
    for item in result.items:
        if item.found and item.found_via != "live" and item.extra.get("Price (USD)"):
            out.append((item.product_id, f"Price is the catalog list price as of {config.CATALOG_DATE}, not live."))
    for item in result.items:
        if not item.found:
            out.append((item.product_id, item.reason or "Not found."))
    return out


def status_line(result):
    text = STATUS_TEXT.get(result.status.value, result.status.value)
    if result.reviewed_by:
        text = f"Reviewed by {result.reviewed_by}, {result.reviewed_at}"
    return text


def _table(ws, row, headers, rows, widths=None):
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
    for r in rows:
        row += 1
        for c, v in enumerate(r, start=1):
            cell = ws.cell(row=row, column=c, value=v)
            cell.alignment = Alignment(vertical="top", wrap_text=isinstance(v, str) and len(v) > 40)
    return row + 2


def add_sheet(wb, result):
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 26
    for col, width in zip("BCDEFG", (48, 16, 16, 40, 18, 14)):
        ws.column_dimensions[col].width = width
    ws["A1"] = "RFQ summary"
    ws["A1"].font = TITLE
    counts = result.counts()
    overall, by_column = fill_rates(result)
    high = sum(1 for f in result.flags if f.severity == "high" and not f.resolved)
    medium = sum(1 for f in result.flags if f.severity == "medium" and not f.resolved)
    kpis = [("Status", status_line(result)), ("Items requested", counts["items"]), ("Found", counts["found"]),
            ("Not found", counts["not_found"]), ("Fill rate (found items)", f"{overall}%"),
            ("Open flags", f"{high} high, {medium} medium"),
            ("Units standardised", result.units_converted),
            ("AI review", result.ai_status or "not run")]
    row = 3
    for label, value in kpis:
        ws.cell(row=row, column=1, value=label).font = Font(name="Inter", bold=True)
        ws.cell(row=row, column=2, value=value)
        row += 1
    ws["B3"].font = Font(name="Inter", bold=True, color="9A3412" if result.status.value == "needs_review"
                         else "166534")
    row += 1

    lines, total = request_lines(result)
    ws.cell(row=row, column=1, value="Request lines").font = SECTION
    row = _table(ws, row + 1, ["Item", "Description", "Qty", "Unit price (USD)", "Price source",
                               "Line total (USD)"],
                 [(l[0], l[1], l[2], l[3], l[5], l[4]) for l in lines])
    ws.cell(row=row - 1, column=5, value="Estimated total (USD)").font = Font(name="Inter", bold=True)
    ws.cell(row=row - 1, column=6, value=total).font = Font(name="Inter", bold=True)
    row += 1

    ws.cell(row=row, column=1, value="Alerts").font = SECTION
    row = _table(ws, row + 1, ["Item", "Alert"], alerts(result) or [("", "None")])

    ws.cell(row=row, column=1, value="Flags").font = SECTION
    flag_rows = [(f.product_id, f.column, f.value, f.issue, f.rule, f.severity,
                  "resolved" if f.resolved else "open") for f in result.flags if f.severity != "info"]
    row = _table(ws, row + 1, ["Item", "Column", "Value", "Issue", "Rule", "Severity", "State"],
                 flag_rows or [("", "", "", "No flags", "", "", "")])

    ws.cell(row=row, column=1, value="AI suggestions (advisory: never change a value or the status)").font = SECTION
    ai_rows = [(f.product_id, f.column, f.value, f.issue, f.rule, f.severity) for f in result.ai_suggestions]
    row = _table(ws, row + 1, ["Item", "Column", "Value", "Suggestion", "Source", "Severity"],
                 ai_rows or [("", "", "", result.ai_status or "None", "", "")])

    ws.cell(row=row, column=1, value="Fill rate by column").font = SECTION
    first = row + 1
    row = _table(ws, first, ["Column", "Filled", "Found items", "Fill rate %"],
                 [(c, f, t, p) for c, f, t, p in by_column])
    if by_column and any(t for _, _, t, _ in by_column):
        chart = BarChart()
        chart.type = "bar"
        chart.title = "Fill rate by column (%)"
        chart.y_axis.scaling.min, chart.y_axis.scaling.max = 0, 100
        chart.legend = None
        data = Reference(ws, min_col=4, min_row=first, max_row=first + len(by_column))
        cats = Reference(ws, min_col=1, min_row=first + 1, max_row=first + len(by_column))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        chart.height, chart.width = 12, 16
        chart.series[0].graphicalProperties.solidFill = NAVY
        ws.add_chart(chart, f"F{first}")
    ws.sheet_view.showGridLines = False
    return ws
