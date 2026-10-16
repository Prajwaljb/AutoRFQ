"""Competitor Product Finder: what is another brand's part, according to the web? Every value cites its page.

For a part code that isn't a Ferguson item ("Mutual Industries 17783-79-3000"), it searches the web (SerpApi)
for the brand and code, keeps only results that name this exact code, and reads specs out of their titles and
snippets: width, length (yards converted to feet: "333.33 yds." -> "1000 ft"), colour, detectable or not, the
utility on the lettering, thickness and a seen price. Each value keeps the URL it came from.

The specs are used to suggest a Ferguson equivalent (sources/alternatives.py) and are shown in the Summary's
competitor cross-reference. They never go into the RFQ row: that stays Not found, as the spec requires. A code
nobody on the web names (a customer's own code) gets nothing: no guess, the reply asks the customer instead.

Results are kept in the product database's cross-reference table, so the same code is not searched twice.
"""
import json
import os
import re
import urllib.parse
import urllib.request

from rfq.quality.units import fmt

COLORS = ("red", "yellow", "blue", "green", "orange", "purple", "brown", "white", "black", "silver", "pink")
UTILITY_RE = re.compile(r"\b(reclaimed water|water|sewer|storm drain|gas|oil|electric|fiber optic|telephone|"
                        r"communication|cable tv|irrigation|force main)\s+line\b", re.I)
WIDTH_RE = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d+)?)\s*(?:\"|”|''|in\b\.?|inch(?:es)?\b)(?:\s*(?:w\b|wide))?", re.I)
LENGTH_RE = re.compile(r"(?<![\d.])(\d{2,5}(?:[.,]\d+)?)\s*(yds?\b\.?|yards?\b|ft\b\.?|feet\b|'|’)(?:\s*l\b)?", re.I)
THICK_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*mil\b", re.I)
PRICE_RE = re.compile(r"\$\s?(\d{1,4}(?:,\d{3})?\.\d{2})")
TO_FT = {"y": 3.0, "f": 1.0, "'": 1.0, "’": 1.0}


def _norm(code):
    return re.sub(r"[\s\-]", "", code or "").lower()


def search(query, logger=None):
    """SerpApi organic results [{link, title, snippet}], or [] (no key, network error)."""
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        return []
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode({"q": query, "api_key": key, "num": 8})
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        if logger:
            logger.warning("web search failed: %s", type(e).__name__)
        return []
    return [{"link": r.get("link", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")}
            for r in data.get("organic_results", [])]


def extract_specs(results, code):
    """{"specs": {name: {"value", "source"}}, "sources": [urls], "title": str} from results naming the code."""
    specs, sources, title = {}, [], ""
    for r in results:
        text = f"{r.get('title', '')} | {r.get('snippet', '')}"
        if _norm(code) not in _norm(text):
            continue  # only a page that names this exact part counts
        link = r.get("link", "")
        sources.append(link)
        title = title or r.get("title", "")

        def put(name, value):
            if value and name not in specs:
                specs[name] = {"value": value, "source": link}

        m = UTILITY_RE.search(text)
        put("Utility", m.group(1).title() if m else "")
        if re.search(r"non[- ]?detect", text, re.I):
            put("Detectable", "No")
        elif re.search(r"\bdetect", text, re.I):
            put("Detectable", "Yes")
        for m in WIDTH_RE.finditer(text):
            if 0.5 <= float(m.group(1)) <= 24:
                put("Width", f"{fmt(float(m.group(1)))} in")
                break
        for m in LENGTH_RE.finditer(text):
            number = float(m.group(1).replace(",", ""))
            feet = number * TO_FT.get(m.group(2)[0].lower(), 1.0)
            if 50 <= feet <= 5000:
                original = f" (given as {m.group(1)} {m.group(2).rstrip('.')})" if m.group(2)[0].lower() == "y" else ""
                put("Length", f"{fmt(feet)} ft{original}")
                break
        colors = [c for c in COLORS if re.search(rf"\b{c}\b", text, re.I)]
        if colors:
            put("Color", "/".join(c.title() for c in colors))
        m = THICK_RE.search(text)
        put("Thickness", f"{fmt(float(m.group(1)))} mil" if m else "")
        m = PRICE_RE.search(text)
        if m and float(m.group(1).replace(",", "")) < 2000:
            put("Price seen", f"${m.group(1)}")
    return {"specs": specs, "sources": sources, "title": title}


def describe(specs):
    """A plain description built only from found specs, for matching and for people."""
    s = {k: v["value"] for k, v in specs.items()}
    parts = []
    if s.get("Utility"):
        parts.append(f"{s['Utility']} line")
    if s.get("Detectable"):
        parts.append("detectable" if s["Detectable"] == "Yes" else "non-detectable")
    parts.append("underground marking tape")
    size = " x ".join(x for x in (s.get("Width", ""), s.get("Length", "").split(" (")[0]) if x)
    if size:
        parts.append(size)
    if s.get("Color"):
        parts.append(s["Color"].lower())
    if s.get("Thickness"):
        parts.append(s["Thickness"])
    return ", ".join(parts)


def find(item, db=None, logger=None):
    """What the web says about a competitor code: {brand, description, specs, sources} or None.

    Uses the product database's cross-reference first; searches only for a code it hasn't seen.
    """
    if db is not None:
        try:
            cached = db.get_crossref(item.product_id)
        except Exception:
            cached = None
        if cached is not None:  # {} = searched before and the web knew nothing: don't search again
            return cached or None
    query = f"{item.brand} {item.product_id}".strip()
    found = extract_specs(search(query, logger), item.product_id)
    if not found["specs"] and item.brand:  # some shops list the code without the brand
        found = extract_specs(search(item.product_id, logger), item.product_id)
    if not found["sources"]:
        info = None
    else:
        info = {"code": item.product_id, "brand": item.brand, "description": describe(found["specs"]),
                "title": found["title"], "specs": found["specs"], "sources": found["sources"][:5]}
    if db is not None and os.environ.get("SERPAPI_API_KEY", "").strip():
        try:
            db.save_crossref(item.product_id, item.brand, info)
        except Exception:
            pass
    return info
