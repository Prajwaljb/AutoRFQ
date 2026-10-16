"""Finds item numbers in text: Ferguson product IDs and other (competitor or customer) part codes."""
import re

from rfq.config import KNOWN_BRANDS

# A Ferguson product ID: 5-7 digits standing alone, optionally with "#" in front. Not part of a longer
# token (hyphenated codes, decimals, URLs, paths): "1844552 ," and "#5106926" match, "17783-79-3000" and
# "14.25" don't, and "x 40 rolls" / "3 inch" are too short.
ID_RE = re.compile(r"(?<![\w.\-/$#])#?(\d{5,7})(?![\w\-/]|[.,]\d)")
# Another part code: alphanumeric groups joined by hyphens, e.g. 17783-79-3000, 31-024, MTX-4409-XQ.
CODE_RE = re.compile(r"(?<![\w\-/.#@])([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)(?![\w\-/@]|\.\w)")
URL_OR_EMAIL_RE = re.compile(r"(?:https?://|www\.)\S+|[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")

# Words that make the number after them something else (spec: tel / phone / fax / mobile / zip / pin /
# PO / order / invoice / qty).
_CONTEXT_WORDS = (r"tel|telephone|phone|ph|fax|mobile|mob|cell|zip|zipcode|postcode|postal\s+code|pin|"
                  r"pincode|pin\s+code|po|p\.o\.|purchase\s+order|order|invoice|inv|qty|quantity")
CONTEXT_RE = re.compile(rf"\b(?:{_CONTEXT_WORDS})\b\.?\s*(?:no\.?|number|num|#|code)?\s*[:#=.\-]?\s*$",
                        re.IGNORECASE)
PHONE_PREFIX_RE = re.compile(r"\+\d[\d\s().\-]*$")
STANDARD_PREFIX_RE = re.compile(r"\b(?:ASTM|ANSI|ISO|UL|EN|DIN|OSHA|CSA|NFPA|IEC)\s*$", re.IGNORECASE)
DATE_RE = re.compile(r"^(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}-\d{2,4})$")
PHONE_CODE_RE = re.compile(r"^\d{3}-\d{3}-\d{4}$")
QTY_RE = re.compile(
    r"(?:\bx\s*|\bqty\.?\s*[:=]?\s*|\bquantity\s*[:=]?\s*)(\d{1,6})\b"
    r"(?:\s*(rolls?|pcs|pieces|boxes|cases|units|each|ea|ft|feet|reels?))?",
    re.IGNORECASE,
)
_BRAND_RES = [(b, re.compile(rf"(?<!\w){re.escape(b)}(?!\w)", re.IGNORECASE)) for b in KNOWN_BRANDS]


def _blank_out(text, pattern):
    """Replaces matches with spaces, keeping every other character at its position."""
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def _line_bounds(text, pos):
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return start, len(text) if end == -1 else end


def _is_code(token, before):
    digits = sum(ch.isdigit() for ch in token)
    if digits < 4:
        return False
    if DATE_RE.match(token) or PHONE_CODE_RE.match(token):
        return False
    if STANDARD_PREFIX_RE.search(before):  # "ASTM D-2103" is a standard, not a part
        return False
    return True


def brand_in(line):
    for brand, pattern in _BRAND_RES:
        if pattern.search(line):
            return brand
    return ""


def find_items(text):
    """Item numbers in text, in order of appearance.

    Returns dicts: {"value", "kind" ("ferguson" or "code"), "line", "brand", "qty", "pos"}.
    Skipped numbers (phone, PO, zip...) are not returned.
    """
    clean = _blank_out(text, URL_OR_EMAIL_RE)
    hits = []
    for m in CODE_RE.finditer(clean):
        start, _ = _line_bounds(clean, m.start())
        before = clean[start:m.start()]
        if _is_code(m.group(1), before) and not CONTEXT_RE.search(before) \
                and not PHONE_PREFIX_RE.search(before):
            hits.append((m.start(), m.end(), "code", m.group(1)))
    taken = [(s, e) for s, e, _, _ in hits]
    for m in ID_RE.finditer(clean):
        if any(s <= m.start() < e for s, e in taken):
            continue
        start, _ = _line_bounds(clean, m.start())
        before = clean[start:m.start()]
        if CONTEXT_RE.search(before) or PHONE_PREFIX_RE.search(before):
            continue
        hits.append((m.start(), m.end(), "ferguson", m.group(1)))
    hits.sort()

    items = []
    for n, (pos, end, kind, value) in enumerate(hits):
        start, line_end = _line_bounds(clean, pos)
        line = text[start:line_end].strip()
        next_pos = hits[n + 1][0] if n + 1 < len(hits) else len(clean)
        segment = clean[end:min(line_end, next_pos)]
        qty_match = QTY_RE.search(segment)
        qty = " ".join(g for g in qty_match.groups() if g) if qty_match else ""
        items.append({
            "value": value, "kind": kind, "line": line[:200],
            "brand": brand_in(line) if kind == "code" else "", "qty": qty, "pos": pos,
        })
    return items
