"""Paths, modes, limits and column order: one place for every setting the flow uses."""
import os
from pathlib import Path

from rfq.infra import env

env.load()  # .env -> environment, before any setting below is read

ROOT = Path(__file__).resolve().parents[1]


def _path(env_name, default):
    """A path from the environment (tests point these elsewhere), else the kit default."""
    value = os.environ.get(env_name, "").strip()
    return Path(value) if value else default


TEMPLATE = _path("RFQ_TEMPLATE", ROOT / "templates" / "rfq_template.xlsx")
CATALOG_JSON = _path("RFQ_CATALOG", ROOT / "data" / "product_catalog.json")
CATALOG_SOURCES = _path("RFQ_CATALOG_SOURCES", ROOT / "data" / "product_catalog_sources.csv")
SPEC_LINKS = ROOT / "data" / "spec_sheet_links.csv"
SPEC_CACHE = ROOT / "data" / "spec_cache"
# RFQ_SPEC_DOWNLOAD=0 reads spec sheets from the bundled copies only (tests, no network).
SPEC_DOWNLOAD = os.environ.get("RFQ_SPEC_DOWNLOAD", "1").strip() != "0"
REFERENCE = ROOT / "reference" / "email-1 reference output.xlsx"

# Modes, from most to least sources used.
LIVE, NO_BROWSER, OFFLINE = "live", "no-browser", "offline"
MODES = (LIVE, NO_BROWSER, OFFLINE)
# Live mode opens the scraping window itself when it isn't running (RFQ_AUTO_BROWSER=0 turns that off).
AUTO_BROWSER = os.environ.get("RFQ_AUTO_BROWSER", "1").strip() != "0"
DEFAULT_CDP = "http://127.0.0.1:9333"  # 127.0.0.1, not localhost: on Windows localhost can resolve to ::1

# The RFQ sheet columns, in template order. Checked against the template at start-up.
RFQ_COLUMNS = [
    "product_id", "Description", "ANSI", "Application", "Color Finish", "Length", "Lettering", "Material",
    "Material Type", "No of Tools", "Temperature Range", "Thickness", "Tool Type", "UL Listed", "Width",
    "OSHA", "Waterworks Application", "Product details", "Weight", "ASTM", "Image", "Picture",
    "Lookup Status",
]
SOURCES_COLUMNS = ["product_id", "column", "value", "source_type", "confidence", "source"]
NOTES_COLUMNS = ["product_id", "note"]
# Filled from the lookup but without a Sources row, as in the reference.
NO_SOURCE_COLUMNS = {"product_id", "Description", "Lookup Status"}
# Spec columns a lookup can fill (everything between product_id and Lookup Status).
SPEC_COLUMNS = [c for c in RFQ_COLUMNS if c not in ("product_id", "Lookup Status")]

FOUND, NOT_FOUND = "Found", "Not found"

# Limits.
MAX_ITEMS = 300
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_SHEET_ROWS = 5000
MAX_CELL_CHARS = 32000
LIVE_BUDGET_SECONDS = 8 * 60

# When the backup catalog was collected (data/README.md); shown next to catalog prices.
CATALOG_DATE = "24 Sep 2026"

# Brands that may be named next to a competitor part number. Longest names first.
KNOWN_BRANDS = [
    "Mutual Industries", "Pro-Pak Industries", "Northern Safety", "Christy's", "King Sales", "Pro-Trace",
    "Pro-Line", "Presco", "Mutual", "Empire", "Paddock", "Brady", "Reef", "3M",
]
