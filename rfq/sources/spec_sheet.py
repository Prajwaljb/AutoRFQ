"""Manufacturer spec sheet PDFs: download -> bundled copy -> skip. Fills blank cells only.

Values are read from the PDF text with pypdf and simple patterns (Thickness, ASTM, OSHA, Material). Each
value keeps the PDF URL, the page number and the text snippet it was read from.
"""
import csv
import io
import json
import logging
import re
import urllib.request

from rfq import config
from rfq.infra.io import write_bytes_atomic
from rfq.models import Cell
from rfq.sources.base import Source

logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are noise here

USER_AGENT = "Mozilla/5.0 (RFQ flow; spec sheet reader)"
TIMEOUT = 30

THICKNESS_RE = re.compile(r"(?:overall\s+)?thickness\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mils?\b", re.IGNORECASE)
ASTM_RE = re.compile(r"\bASTM\s*([A-Z])\s*[-‐-–]?\s*(\d{2,5})\b")
OSHA_RE = re.compile(r"\bOSHA\s*(?:standard\s*)?(\d{4}[.\-]\d+(?:\([a-z0-9]+\))*)", re.IGNORECASE)
MATERIAL_RE = re.compile(r"\bmaterial\s*:\s*([A-Za-z][A-Za-z /,&-]{2,40})", re.IGNORECASE)


def download_pdf(url, timeout=TIMEOUT):
    """The PDF bytes. Raises on HTTP errors, timeouts, or anything that is not a PDF."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(config.MAX_ATTACHMENT_BYTES * 3)
    if not data.startswith(b"%PDF"):
        raise ValueError("not a PDF (an error page?)")
    return data


def _snippet(text, start, end, width=60):
    s = max(0, start - width)
    return " ".join(text[s:end + width].split())


def read_values(pdf_bytes):
    """{column: (value, page number, snippet)} found in a spec sheet."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    found = {}
    astm = []
    osha = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        m = THICKNESS_RE.search(text)
        if m and "Thickness" not in found:
            value = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
            found["Thickness"] = (f"{value} mil", page_no, _snippet(text, m.start(), m.end()))
        for m in ASTM_RE.finditer(text):
            value = f"ASTM {m.group(1)}-{m.group(2)}"
            if value not in [a[0] for a in astm]:
                astm.append((value, page_no, _snippet(text, m.start(), m.end())))
        for m in OSHA_RE.finditer(text):
            value = f"OSHA {m.group(1)}"
            if value not in [o[0] for o in osha]:
                osha.append((value, page_no, _snippet(text, m.start(), m.end())))
        m = MATERIAL_RE.search(text)
        if m and "Material" not in found:
            found["Material"] = (m.group(1).strip(" ,-"), page_no, _snippet(text, m.start(), m.end()))
    if astm:
        found["ASTM"] = ("|".join(a[0] for a in astm), astm[0][1], astm[0][2])
    if osha:
        found["OSHA"] = (";".join(o[0] for o in osha), osha[0][1], osha[0][2])
    return found


class SpecSheetSource(Source):
    name = "spec"
    found_via = "spec"

    def __init__(self, cache_dir, replay=False, download=True):
        self.cache_dir = cache_dir
        self.replay = replay
        self.download = download and not replay and config.SPEC_DOWNLOAD
        self.links = {}
        try:
            with config.SPEC_LINKS.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    self.links[row["product_id"]] = row["spec_sheet_url"]
        except OSError:
            pass
        index = config.SPEC_CACHE / "index.json"
        try:
            self.bundled = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.bundled = {}
        self.last_problem = ""
        self.last_origin = ""
        self.download_problem = ""

    def url(self, product_id):
        return self.links.get(product_id, "")

    def _cached(self, product_id):
        path = self.cache_dir / f"{product_id}.pdf"
        if path.exists():
            data = path.read_bytes()
            if data.startswith(b"%PDF"):
                return data
            path.unlink(missing_ok=True)  # half-written or bad: never keep it
        return None

    def get_pdf(self, product_id, url=None):
        """(pdf bytes, origin) where origin is download / cache / bundled; (None, reason) if none."""
        url = url or self.url(product_id)
        if not url:
            return None, "no spec sheet link"
        data = self._cached(product_id)
        if data:
            return data, "cache"
        problem = "download skipped (replay)" if self.replay else "download turned off"
        if self.download:
            try:
                data = download_pdf(url)
                write_bytes_atomic(self.cache_dir / f"{product_id}.pdf", data)
                return data, "download"
            except Exception as e:
                problem = f"download failed ({type(e).__name__})"
        self.download_problem = problem
        name = self.bundled.get(product_id)
        if name and (config.SPEC_CACHE / name).exists():
            return (config.SPEC_CACHE / name).read_bytes(), "bundled"
        return None, problem + "; no bundled copy"

    def lookup(self, product_id, url=None):
        """{column: Cell} read from the product's spec sheet. Sets last_problem when nothing was read."""
        self.last_problem = ""
        self.last_origin = ""
        url = url or self.url(product_id)
        data, origin = self.get_pdf(product_id, url)
        if data is None:
            self.last_problem = origin
            return {}
        self.last_origin = origin
        try:
            values = read_values(data)
        except Exception as e:
            self.last_problem = f"spec sheet could not be read ({type(e).__name__})"
            return {}
        cells = {}
        for column, (value, page, snippet) in values.items():
            cells[column] = Cell(value, "spec_sheet", "medium",
                                 f'{url} (page {page}: "{snippet[:160]}")')
        return cells
