"""The backup catalog: data/product_catalog.json + data/product_catalog_sources.csv.

Values and their Sources rows are carried over exactly as given. Image and Picture both use the catalog's
"Picture URL" and its source row, as in the reference.
"""
import csv
import json

from rfq import config
from rfq.models import Cell
from rfq.sources.base import Source

EXTRA_FIELDS = ["Price (USD)", "Availability", "Status", "Brand", "Manufacturer Part #", "Ferguson URL",
                "Spec Sheet URL", "Category", "Product Family", "UPC"]


class KitBroken(Exception):
    """A kit file (template, catalog) is missing or corrupt: the flow can't run for any email."""


class CatalogSource(Source):
    name = "catalog"
    found_via = "catalog"

    def __init__(self, catalog_path=None, sources_path=None):
        catalog_path = catalog_path or config.CATALOG_JSON
        sources_path = sources_path or config.CATALOG_SOURCES
        try:
            self.products = json.loads(catalog_path.read_text(encoding="utf-8"))
            if not isinstance(self.products, dict):
                raise ValueError("expected an object keyed by product_id")
        except (OSError, ValueError) as e:
            raise KitBroken(f"Catalog {catalog_path} is missing or not valid JSON ({e}).") from e
        self.sources = {}
        try:
            with sources_path.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    self.sources[(row["product_id"], row["column"])] = row
        except (OSError, KeyError, csv.Error) as e:
            raise KitBroken(f"Catalog sources {sources_path} is missing or unreadable ({e}).") from e

    def has(self, product_id):
        return product_id in self.products

    def _cell(self, product_id, column, value):
        row = self.sources.get((product_id, column))
        if row is None:  # every catalog value has a row today; never write a value without a source
            return Cell(value, "catalog", "medium", f"data/product_catalog.json ({config.CATALOG_DATE})")
        return Cell(value, row["source_type"], row["confidence"], row["source"])

    def lookup(self, product_id):
        product = self.products.get(product_id)
        if not product:
            return {}
        cells = {}
        for column in config.SPEC_COLUMNS:
            if column in ("Image", "Picture"):
                value = (product.get("Picture URL") or "").strip()
                if value:
                    cells[column] = self._cell(product_id, "Picture URL", value)
                continue
            value = product.get(column)
            if value is None or str(value).strip() == "":
                continue
            value = str(value)
            if column == "Description":
                cells[column] = Cell(value, "catalog", "high", "data/product_catalog.json")
            else:
                cells[column] = self._cell(product_id, column, value)
        return cells

    def extra(self, product_id):
        product = self.products.get(product_id) or {}
        return {k: str(product[k]) for k in EXTRA_FIELDS if product.get(k)}

    def nearest_ids(self, product_id):
        """Catalog IDs one digit off, or with two neighbouring digits swapped. Sorted, never applied."""
        out = []
        for other in self.products:
            if len(other) != len(product_id) or other == product_id:
                continue
            diff = [i for i, (a, b) in enumerate(zip(other, product_id)) if a != b]
            if len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and other[diff[0]] == product_id[diff[1]]
                                  and other[diff[1]] == product_id[diff[0]]):
                out.append(other)
        return sorted(out)
