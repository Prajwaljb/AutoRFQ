"""The live ferguson.com product page, read through the Chrome window opened for scraping (CDP).

ferguson.com blocks plain scripts, so this attaches to a real browser (python rfq/chrome.py) with
Playwright's connect_over_cdp. It opens its own tab and closes it at the end; it never touches the user's
tabs. Every page read is cached (HTML + screenshot) in out/.cache/pages/, so --replay can rebuild a run
without the network.

A page counts only if it shows "Item #<id>". A redirect to another product or a search page with no exact
match is "not on the live site" (returns {}); a block, timeout or changed layout raises SourceUnavailable
so the caller falls back to the catalog.
"""
import html as htmllib
import json
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

from rfq.infra.io import write_bytes_atomic, write_text_atomic
from rfq.models import Cell
from rfq.sources.base import Source, SourceUnavailable

SEARCH_URL = "https://www.ferguson.com/search/?q={pid}"
BASE_URL = "https://www.ferguson.com"
PAGE_TIMEOUT_MS = 20000
PACE_SECONDS = 1.5
BLOCK_MARKERS = ("access denied", "pardon our interruption", "captcha", "are you a robot",
                 "request unsuccessful", "unusual traffic")

# Ferguson attribute labels -> template columns (lower-case, spaces collapsed).
LABELS = {
    "length": "Length", "thickness": "Thickness", "width": "Width", "color finish name": "Color Finish",
    "color finish": "Color Finish", "color/finish": "Color Finish", "color": "Color Finish",
    "lettering": "Lettering", "material": "Material", "material type": "Material Type",
    "application": "Application", "osha": "OSHA", "ansi": "ANSI", "astm": "ASTM", "ul listed": "UL Listed",
    "temperature range": "Temperature Range", "tool type": "Tool Type",
    "number of tools included": "No of Tools", "no of tools": "No of Tools", "weight": "Weight",
    "product weight": "Weight", "waterworks application": "Waterworks Application",
}
PAIR_RE = re.compile(
    r'class="[^"]*c-product-details__specs__attribute[^"]*">(.*?)</div>\s*'
    r'<div class="[^"]*c-product-details__specs__attribute[^"]*">(.*?)</div>', re.S)
LD_JSON_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
# Ferguson's product feed writes some quotes as pseudo-tags.
FEED_QUOTES = [(re.compile(r"<\s*CQUOTA\s*/?\s*>", re.I), "'"), (re.compile(r"<\s*CDQUOTA\s*/?\s*>", re.I), '"')]
# Multi-value attributes: the site separates them with ", ", the RFQ uses "|" (as the catalog does).
PIPE_COLUMNS = {"Application", "Material", "ASTM"}


def _text(fragment):
    for pattern, char in FEED_QUOTES:
        fragment = pattern.sub(char, fragment)
    return " ".join(htmllib.unescape(TAG_RE.sub(" ", fragment)).split())


def page_text(page_html):
    page_html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page_html)
    return _text(page_html)


def is_blocked(page_html, status=None):
    if status in (403, 429) or (status is not None and status >= 500):
        return True
    text = page_text(page_html).lower()
    has_items = re.search(r"item\s*#\s*\d", text) is not None
    return not has_items and any(m in text for m in BLOCK_MARKERS)


def shows_item(page_html, product_id):
    return re.search(rf"Item\s*#\s*{re.escape(product_id)}\b", page_text(page_html)) is not None


def find_product_link(page_html, product_id):
    """The product page URL for this exact item on a search results page, or None."""
    m = re.search(rf'href="([^"]*/{re.escape(product_id)}\.html)[^"]*"', page_html)
    if not m:
        return None
    href = htmllib.unescape(m.group(1))
    return href if href.startswith("http") else BASE_URL + href


def _product_ld(page_html):
    for block in LD_JSON_RE.findall(page_html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict) and obj.get("@type") == "Product":
                return obj
    return {}


def parse_product_html(page_html, product_id):
    """({column: value}, extra) from a product page. Pure function: used live and in --replay."""
    values = {}
    for label, value in PAIR_RE.findall(page_html):
        column = LABELS.get(" ".join(_text(label).lower().split()))
        value = _text(value)
        if column and value and column not in values:
            if column in PIPE_COLUMNS:
                value = "|".join(v.strip() for v in value.split(", ") if v.strip())
            values[column] = value
    ld = _product_ld(page_html)
    extra = {}
    if ld:
        if ld.get("name"):
            values.setdefault("Description", _text(str(ld["name"])))
        desc = ld.get("description")
        if isinstance(desc, list) and desc:
            values.setdefault("Product details", "|".join(_text(str(d)) for d in desc if str(d).strip()))
        image = ld.get("image")
        image = image[0] if isinstance(image, list) and image else image
        if isinstance(image, str) and image.startswith("https://"):
            values.setdefault("Image", image)
            values.setdefault("Picture", image)
        offers = ld.get("offers") or {}
        offers = offers[0] if isinstance(offers, list) and offers else offers
        if isinstance(offers, dict):
            if offers.get("price"):
                extra["Price (USD)"] = str(offers["price"])
            if offers.get("availability"):
                extra["Availability"] = str(offers["availability"]).rsplit("/", 1)[-1]
        brand = ld.get("brand")
        if isinstance(brand, dict) and brand.get("name"):
            extra["Brand"] = str(brand["name"])
        if ld.get("url"):
            extra["Ferguson URL"] = str(ld["url"])
    return values, extra


def chrome_available(cdp, timeout=1.0):
    """True if a Chrome with remote debugging answers at cdp (one quick probe)."""
    try:
        with urllib.request.urlopen(cdp.rstrip("/") + "/json/version", timeout=timeout) as resp:
            return b"Browser" in resp.read(4096)
    except Exception:
        return False


class LiveSource(Source):
    name = "live"
    found_via = "live"

    def __init__(self, cdp, cache_dir, replay=False):
        self.cdp = cdp
        self.cache_dir = Path(cache_dir) / "pages"
        self.replay = replay
        self._pw = self._browser = self._page = None
        self.last_extra = {}
        self.last_screenshot = ""
        self._last_visit = 0.0

    # Browser lifecycle -------------------------------------------------------------------------------
    def open(self):
        if self.replay:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise SourceUnavailable("Playwright is not installed") from e
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp, timeout=10000)
            context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
            self._page = context.new_page()  # our own tab
        except Exception as e:
            self.close()
            raise SourceUnavailable(f"could not attach to Chrome at {self.cdp} ({type(e).__name__})") from e

    def close(self):
        for closer in (lambda: self._page and self._page.close(),
                       lambda: self._pw and self._pw.stop()):  # stop() detaches; the browser stays open
            try:
                closer()
            except Exception:
                pass
        self._pw = self._browser = self._page = None

    # One product -------------------------------------------------------------------------------------
    def _goto(self, url):
        wait = PACE_SECONDS - (time.monotonic() - self._last_visit)
        if wait > 0:
            time.sleep(wait)  # be polite to the site
        self._last_visit = time.monotonic()
        try:
            resp = self._page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        except Exception as e:
            name = type(e).__name__
            if "Target" in str(e) and "closed" in str(e):
                raise SourceUnavailable("the Chrome window was closed") from e
            raise SourceUnavailable(f"page did not load ({name}: {str(e).splitlines()[0][:80]})") from e
        try:
            self._page.wait_for_selector(".c-product-details__specs__attribute, .product-tile, h1",
                                         timeout=8000)
        except Exception:
            pass
        status = resp.status if resp is not None else None
        return self._page.content(), status

    def _cache(self, product_id, page_html, url):
        write_text_atomic(self.cache_dir / f"{product_id}.html", page_html)
        write_text_atomic(self.cache_dir / f"{product_id}.json", json.dumps({"url": url}))
        shot = self.cache_dir / f"{product_id}.png"
        try:
            write_bytes_atomic(shot, self._page.screenshot(type="png"))
            self.last_screenshot = str(shot)
        except Exception:
            self.last_screenshot = ""

    def _from_cache(self, product_id):
        path = self.cache_dir / f"{product_id}.html"
        if not path.exists():
            raise SourceUnavailable("not in the replay cache")
        meta = self.cache_dir / f"{product_id}.json"
        url = json.loads(meta.read_text(encoding="utf-8")).get("url", "") if meta.exists() else ""
        shot = self.cache_dir / f"{product_id}.png"
        self.last_screenshot = str(shot) if shot.exists() else ""
        return path.read_text(encoding="utf-8"), url

    def lookup(self, product_id, url=None):
        """{column: Cell} from the live page; {} if the item is not on ferguson.com."""
        self.last_extra, self.last_screenshot = {}, ""
        if self.replay:
            page_html, url = self._from_cache(product_id)
        else:
            if self._page is None:
                raise SourceUnavailable("browser not attached")
            url = url or SEARCH_URL.format(pid=product_id)
            page_html, status = self._goto(url)
            if is_blocked(page_html, status):
                raise SourceUnavailable(f"ferguson.com blocked the page (HTTP {status})")
            if status == 404:
                return {}
            if not shows_item(page_html, product_id) or "/search" in self._page.url:
                link = find_product_link(page_html, product_id)
                if link:
                    url = link
                    page_html, status = self._goto(url)
                    if is_blocked(page_html, status):
                        raise SourceUnavailable(f"ferguson.com blocked the page (HTTP {status})")
            url = self._page.url
            self._cache(product_id, page_html, url)
        if not shows_item(page_html, product_id):
            return {}  # a search page, or another product: not on the live site
        values, extra = parse_product_html(page_html, product_id)
        if len(values) <= 1:  # selectors found nothing: the layout changed, never "Found with blanks"
            raise SourceUnavailable("the product page layout was not recognised")
        self.last_extra = extra
        source = f"{url} (read {date.today().isoformat()})"
        return {column: Cell(value, "ferguson_page", "high", source) for column, value in values.items()}
