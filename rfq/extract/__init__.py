"""Stage 1: the ordered, de-duplicated list of requested items."""
import re

from rfq.config import MAX_ITEMS
from rfq.extract.attachments import read_attachment
from rfq.extract.mail import read_email
from rfq.extract.patterns import find_items
from rfq.models import CODE, Item

__all__ = ["read_email", "extract_items"]


QUOTE_HEADER_RE = re.compile(r"^\s*On .{4,200}wrote:\s*$", re.MULTILINE)


def without_quoted_reply(text):
    """A reply's own text: drops "> " quoted lines and everything after "On <date>, <name> wrote:".
    Forwarded messages ("---------- Forwarded message") are kept: they carry the request."""
    m = QUOTE_HEADER_RE.search(text)
    if m:
        text = text[:m.start()]
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def _candidates(data, result):
    """(value, kind, line, brand, qty) in reading order: text parts, then attachments."""
    for _, text in data.texts:
        # A reply's own words win ("use 9677539" above our quoted RFQ); if they hold no item, the request
        # is in the quoted part (a customer replying "please quote these"), so read everything.
        for hit in find_items(without_quoted_reply(text)) or find_items(text):
            yield hit
    for name, payload in data.attachments:
        values, problems = read_attachment(name, payload)
        for text in problems:
            result.add_note(None, "extract", text)
            result.warnings.append(text)
        for value, row_label, qty in values:
            for hit in find_items(value):
                hit["line"] = row_label
                hit["qty"] = hit["qty"] or qty
                yield hit


def extract_items(data, result):
    """Fills result.items (and extract notes) from a parsed email."""
    for text in data.problems:
        result.add_note(None, "extract", text)
        result.warnings.append(text)

    seen = {}
    repeats = {}
    skipped = []
    for hit in _candidates(data, result):
        key = hit["value"].upper()
        if key in seen:
            repeats[key] = repeats.get(key, 1) + 1
            continue
        if len(result.items) >= MAX_ITEMS:
            if key not in skipped:
                skipped.append(key)
            continue
        item = Item(index=len(result.items), product_id=hit["value"], kind=hit["kind"],
                    line=hit["line"], brand=hit["brand"], qty=hit["qty"])
        seen[key] = item
        result.items.append(item)

    for key, count in repeats.items():
        times = "twice" if count == 2 else f"{count} times"
        result.add_note(seen[key], "extract", f"Listed {times} in the request; kept once.")
    for item in result.items:
        if item.kind == CODE:
            brand = f"brand named in the request: {item.brand}" if item.brand else "no brand named"
            result.add_note(item, "extract", f"Not a Ferguson item number ({brand}).")
    if skipped:
        text = (f"{len(skipped)} more items were listed than the {MAX_ITEMS} we process in one request; "
                f"not processed: {', '.join(skipped[:20])}{' ...' if len(skipped) > 20 else ''}.")
        result.add_note(None, "extract", text)
        result.warnings.append(text)
    if not result.items:
        result.add_note(None, "extract", "No item numbers were found in the request.")
    return result.items
