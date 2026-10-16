"""The customer reply: reply.eml with a plain-text and an HTML body and RFQ.xlsx attached.

Written for a buyer. Never contains internal words (flag, rule, severity), fill rates, review links,
"AI" or "DRAFT", and no timings. mailbot.py rewrites From/To/threading headers when it sends it.
"""
import html
import os
from email.message import EmailMessage
from pathlib import Path
from string import Template

from rfq import config
from rfq.models import CODE

TEMPLATES = Path(__file__).resolve().parent / "templates"
NAVY, MIST, STEEL = "#00446a", "#e6ecf0", "#b2c7d2"
AVAILABILITY = {"InStock": "In stock", "OutOfStock": "Out of stock"}


def _first_name(name):
    name = (name or "").strip().strip('"')
    return name.split()[0] if name else ""


def unit_price(item):
    price = item.extra.get("Price (USD)", "")
    if not price:
        return ""
    try:
        price = f"${float(price):,.2f}"
    except ValueError:
        price = f"${price}"
    if item.found_via == "live":
        return price
    return f"{price} (list price as of {config.CATALOG_DATE})"


def availability(item):
    value = item.extra.get("Availability", "")
    return AVAILABILITY.get(value, value) or "Ask us"


def _rows(result):
    rows = []
    for n, item in enumerate(result.items, start=1):
        if item.found:
            desc = item.cells["Description"].value if "Description" in item.cells else ""
            rows.append([str(n), item.product_id, desc, "Found", unit_price(item), availability(item)])
        else:
            rows.append([str(n), item.product_id, "", "Not found", "", ""])
    return rows


HEADERS = ["#", "Item", "Description", "Status", "Unit price", "Availability"]


def _text_table(rows):
    if not rows:
        return ""
    clipped = [[c if len(c) <= 48 else c[:45] + "..." for c in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in clipped)) for i, h in enumerate(HEADERS)]
    line = lambda cells: "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()
    out = [line(HEADERS), line(["-" * w for w in widths])] + [line(r) for r in clipped]
    return "\n" + "\n".join(out) + "\n"


def _html_table(rows):
    if not rows:
        return ""
    th = "".join(f'<th align="left" style="padding:8px;background:{MIST};color:{NAVY};'
                 f'border-bottom:2px solid {NAVY};font-size:13px;">{html.escape(h)}</th>' for h in HEADERS)
    body = []
    for row in rows:
        not_found = row[3] == "Not found"
        tds = []
        for i, c in enumerate(row):
            style = f"padding:8px;border-bottom:1px solid {STEEL};font-size:13px;vertical-align:top;"
            if i == 1:
                style += "font-family:Consolas,Menlo,monospace;white-space:nowrap;"
            if i == 3:
                style += "font-weight:bold;" + ("color:#9a3412;" if not_found else "color:#166534;")
            tds.append(f'<td style="{style}">{html.escape(c)}</td>')
        bg = f' style="background:{MIST};"' if not_found else ""
        body.append(f"<tr{bg}>{''.join(tds)}</tr>")
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;margin:16px 0;">'
            f"<tr>{th}</tr>{''.join(body)}</table>")


def _unmatched(result):
    """(item, reason, next step) for every Not found item."""
    out = []
    for item in result.items:
        if item.found:
            continue
        reason = item.reason or "We could not find this item number."
        if item.kind == CODE:
            step = "Reply with the Ferguson item number, or ask us to suggest an equivalent."
        else:
            step = "Please check the number, or reply with the Ferguson item number."
        out.append((item, reason, step))
    return out


def _quality(result):
    if not result.quality_ran:
        return ""
    if result.status.value in ("approved", "sent") and any(f.resolved for f in result.flags):
        return "Quality check: checked by our team."
    units = result.units_converted
    text = "Quality check: every value checked."
    if units:
        text += f" {units} measurement{'s' if units != 1 else ''} converted to standard units (ft, in, mil, lb)."
    open_flags = [f for f in result.flags if not f.resolved]
    if open_flags:
        n = len(open_flags)
        text += (f" {n} value{'s are' if n != 1 else ' is'} worth a second look; "
                 f"{'they are' if n != 1 else 'it is'} listed on the Summary sheet.")
    else:
        text += " No issues found."
    return text


def build(result, xlsx_path, original=None):
    """The reply as an EmailMessage."""
    counts = result.counts()
    first = _first_name(result.sender_name)
    greeting = f"Hi {first}," if first else "Hi,"
    total = counts["items"]
    if total == 0:
        summary = ("We could not find any item numbers in your request. Please reply with the Ferguson "
                   "item numbers (one per line, or in an attached .xlsx sheet) and we will prepare the RFQ.")
    else:
        need = counts["not_found"]
        tail = f"{counts['found']} matched, {need} need{'s' if need == 1 else ''} your input." if need \
            else f"all {counts['found']} matched."
        summary = f"Your RFQ for {total} item{'s' if total != 1 else ''} is attached: {tail}"
    capped = any("not processed" in w for w in result.warnings)
    if capped:
        summary += f" Your list was longer than {config.MAX_ITEMS} items; the rest are listed in the Notes sheet."

    rows = _rows(result)
    unmatched = _unmatched(result)
    quality = _quality(result)

    text_unmatched = ""
    html_unmatched = ""
    if unmatched:
        lines = ["Items we couldn't match:"]
        lis = []
        for item, reason, step in unmatched:
            lines.append(f"- {item.product_id}: {reason} {step}")
            lis.append(f"<li style=\"margin:0 0 6px 0;\"><strong style=\"font-family:Consolas,Menlo,monospace;\">"
                       f"{html.escape(item.product_id)}</strong>: {html.escape(reason)} {html.escape(step)}</li>")
        text_unmatched = "\n".join(lines) + "\n"
        html_unmatched = (f'<p style="margin:16px 0 6px 0;color:{NAVY};font-weight:bold;">Items we couldn\'t '
                          f'match</p><ul style="margin:0;padding-left:20px;">{"".join(lis)}</ul>')

    values = {
        "greeting": greeting, "summary": summary, "found": counts["found"], "total": total,
        "not_found": counts["not_found"],
    }
    text = Template((TEMPLATES / "reply.txt").read_text(encoding="utf-8")).substitute(
        values, quality_line=quality, item_table=_text_table(rows), unmatched_section=text_unmatched)
    page = Template((TEMPLATES / "reply.html").read_text(encoding="utf-8")).substitute(
        {k: html.escape(str(v)) for k, v in values.items()},
        quality_html=f'<p style="margin:0 0 4px 0;">{html.escape(quality)}</p>' if quality else "",
        item_table=_html_table(rows), unmatched_html=html_unmatched)

    msg = EmailMessage()
    msg["From"] = os.environ.get("BOT_EMAIL", "").strip() or "rfq-agent@localhost"
    msg["To"] = result.sender or "unknown@localhost"
    subject = result.subject or "RFQ request"
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if result.message_id:
        msg["In-Reply-To"] = result.message_id
        msg["References"] = result.message_id
    msg.set_content(text.replace("\n\n\n", "\n\n"))
    msg.add_alternative(page, subtype="html")
    msg.add_attachment(Path(xlsx_path).read_bytes(), maintype="application",
                       subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="RFQ.xlsx")
    return msg


def fallback(result, original_subject=""):
    """The "a person will follow up" reply, used when the flow could not finish."""
    msg = EmailMessage()
    msg["From"] = os.environ.get("BOT_EMAIL", "").strip() or "rfq-agent@localhost"
    msg["To"] = result.sender or "unknown@localhost"
    subject = original_subject or result.subject or "RFQ request"
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if result.message_id:
        msg["In-Reply-To"] = result.message_id
        msg["References"] = result.message_id
    first = _first_name(result.sender_name)
    msg.set_content(f"{'Hi ' + first + ',' if first else 'Hi,'}\n\nThank you for your RFQ. We could not "
                    "process it automatically this time; a person from our team will follow up with you "
                    "shortly.\n\nKind regards,\nFerguson RFQ Agent\n")
    return msg
