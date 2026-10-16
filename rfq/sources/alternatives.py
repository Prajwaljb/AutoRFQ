"""Ferguson alternatives for Not found items. Suggestions only: never put on the RFQ by themselves.

What an unmatched item is, comes from (in this order):
1. the "Not in catalog" sheet of data/product_catalog.xlsx (old description of a removed Ferguson item),
2. the email line it was found on ("the Mutual detectable electric tape, part 17774-79-3000"),
3. optionally a web search for "<brand> <code>" (SerpApi, only with SERPAPI_API_KEY and not offline).

The description is reduced to attributes (colour, utility, detectable, width, length, tape kind; APWA
colours tie a utility to a colour: electric red, gas yellow, water blue, sewer green, telecom orange,
reclaimed purple, force main brown). Catalog products are scored on the same attributes. A colour or tape
kind conflict rules a product out. Ranking is deterministic: score, then product_id.
"""
import json
import os
import re
import urllib.parse
import urllib.request

from rfq import config

COLORS = ("red", "yellow", "blue", "green", "orange", "purple", "brown", "white", "pink")
APWA = [("reclaimed", "purple"), ("irrigation", "purple"), ("slurry", "purple"), ("force main", "brown"),
        ("fiber", "orange"), ("fibre", "orange"), ("telecom", "orange"), ("communication", "orange"),
        ("cable", "orange"), ("electric", "red"), ("power", "red"), ("gas", "yellow"), ("oil", "yellow"),
        ("steam", "yellow"), ("sewer", "green"), ("storm", "green"), ("drain", "green"), ("water", "blue"),
        ("potable", "blue")]
WIDTH_RE = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\s*(?:in\b\.?|inch(?:es)?\b|\"|-inch\b|x\s*\d{3,4})", re.I)
LENGTH_RE = re.compile(r"(?<![\d.])(\d{3,4}|1,000)\s*(?:ft\b\.?|feet\b|')", re.I)
TYPE_WORDS = {"marking", "detector", "warning", "caution", "barrier", "magnesium", "tracer", "fireline"}
MIN_SCORE = 4
MAX_SUGGESTIONS = 3


def attributes(text):
    """{color, utility, detectable, width, length, kind} found in a product description."""
    t = " " + " ".join(str(text).lower().split()) + " "
    attrs = {}
    utility = next((u for u, _ in APWA if re.search(rf"\b{u}", t)), None)
    if utility:
        attrs["utility"] = utility
    color = next((c for c in COLORS if re.search(rf"\b{c}\b", t)), None)
    if color:
        attrs["color"] = color
    elif utility:
        attrs["color"] = dict(APWA)[utility]
    if re.search(r"non[- ]?detect", t):
        attrs["detectable"] = False
    elif re.search(r"detect|tracer|locat", t):
        attrs["detectable"] = True
    if re.search(r"barri|barricade|danger|do not enter|construction area|open trench|crystalline", t):
        attrs["kind"] = "barrier"
    elif re.search(r"restrain", t):
        attrs["kind"] = "joint"
    elif re.search(r"detector|detectable|underground|buried|marking|warning", t):
        attrs["kind"] = "underground"
    m = WIDTH_RE.search(t)
    if m:
        attrs["width"] = float(m.group(1))
    m = LENGTH_RE.search(t)
    if m:
        attrs["length"] = float(m.group(1).replace(",", ""))
    words = TYPE_WORDS & set(re.findall(r"[a-z]+", t))
    if words:
        attrs["words"] = words
    return attrs


def _product_text(product):
    return " ".join(str(product.get(k, "")) for k in ("Description", "Color Finish", "Lettering", "Width",
                                                       "Length", "Product Family", "Tool Type"))


def _number(value):
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(value or ""))
    return float(m.group(1)) if m else None


def score(query, product):
    """(score, matched attribute names) or (None, []) if the product conflicts with the request."""
    cand = attributes(_product_text(product))
    if product.get("Color Finish"):
        cand["color"] = str(product["Color Finish"]).lower()
    width, length = _number(product.get("Width")), _number(product.get("Length"))
    if width:
        cand["width"] = width
    if length:
        cand["length"] = length
    total, matched = 0, []
    if "color" in query:
        if cand.get("color") != query["color"]:
            return None, []
        total, matched = total + 3, matched + [query["color"]]
    if "kind" in query and cand.get("kind") and cand["kind"] != query["kind"]:
        return None, []
    if query.get("kind") and cand.get("kind") == query["kind"]:
        total, matched = total + 1, matched + [f"{query['kind']} tape"]
    if "utility" in query and query["utility"] in _product_text(product).lower():
        total, matched = total + 2, matched + [query["utility"]]
    if "detectable" in query and "detectable" in cand:
        if cand["detectable"] == query["detectable"]:
            total, matched = total + 2, matched + ["detectable" if query["detectable"] else "non-detectable"]
        else:
            total -= 3
    if "width" in query and "width" in cand:
        if cand["width"] == query["width"]:
            total, matched = total + 2, matched + [f"{query['width']:g} in wide"]
        else:
            total -= 1
    if "length" in query and "length" in cand:
        if cand["length"] == query["length"]:
            total, matched = total + 1, matched + [f"{query['length']:g} ft"]
        else:
            total -= 1
    words = set(re.findall(r"[a-z]+", str(product.get("Description", "")).lower()))
    for word in sorted(TYPE_WORDS & words & query.get("words", set())):
        total, matched = total + 1, matched + [word]
    return total, matched


def _not_in_catalog():
    """product_id -> old description, from the kit's catalog workbook."""
    path = config.ROOT / "data" / "product_catalog.xlsx"
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        rows = list(wb["Not in catalog"].iter_rows(min_row=2, values_only=True))
        wb.close()
        return {str(r[0]): str(r[1]) for r in rows if r and r[0] and r[1]}
    except Exception:
        return {}


def web_description(item, logger=None):
    """(text, url) from a web search for the code, or ("", ""). Needs SERPAPI_API_KEY."""
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        return "", ""
    q = f"{item.brand} {item.product_id} tape".strip()
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode({"q": q, "api_key": key, "num": 5})
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        if logger:
            logger.warning("web search for %s failed: %s", item.product_id, type(e).__name__)
        return "", ""
    for r in data.get("organic_results", [])[:5]:
        text = f"{r.get('title', '')} {r.get('snippet', '')}"
        if item.product_id.lower() in text.lower():  # only a result that names this exact part
            return text, r.get("link", "")
    return "", ""


class Alternatives:
    def __init__(self, catalog, web=False, logger=None):
        self.catalog = catalog
        self.web = web
        self.logger = logger
        self.old = _not_in_catalog()

    def describe(self, item):
        """(description, where it came from) for a Not found item."""
        if item.product_id in self.old:
            return self.old[item.product_id], "Ferguson's earlier listing (data/product_catalog.xlsx)"
        line = item.line or ""
        if line and not line.lower().startswith(tuple(f"{n}" for n in ("email", "rfq_items"))) and " row " not in line:
            text = re.sub(re.escape(item.product_id), " ", line, flags=re.I)
            if attributes(text):
                return " ".join(text.split()), "the request email"
        if self.web and item.kind == "code":
            text, url = web_description(item, self.logger)
            if text:
                return text, f"web search: {url}"
        return "", ""

    def suggest(self, item):
        """Up to 3 alternatives: [{product_id, description, score, matched, price, availability}]."""
        text, origin = self.describe(item)
        query = attributes(text) if text else {}
        if len([k for k in query if k != "words"]) < 2:
            return text, origin, []
        ranked = []
        for pid, product in self.catalog.products.items():
            s, matched = score(query, product)
            if s is not None and s >= MIN_SCORE:
                ranked.append((-s, pid, matched, product))
        ranked.sort()
        out = []
        for neg, pid, matched, product in ranked[:MAX_SUGGESTIONS]:
            out.append({"product_id": pid, "description": product.get("Description", ""), "score": -neg,
                        "matched": matched, "price": str(product.get("Price (USD)", "")),
                        "availability": str(product.get("Availability", ""))})
        return text, origin, out
