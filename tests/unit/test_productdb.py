import time

from rfq.infra.productdb import ProductDB
from rfq.models import Cell, Item
from rfq.sources.catalog import CatalogSource


def test_store_read_freshness_and_clear(tmp_path):
    db = ProductDB(tmp_path / "p.db")
    cells = {"Description": Cell("6 in tape", "ferguson_page", "high", "https://x (read 2026-10-16)"),
             "Width": Cell("6 in", "ferguson_page", "high", "https://x")}
    db.upsert("5106912", cells, {"Price (USD)": "139.02", "alternatives": [1]}, "live", "https://x")
    cached, extra, record = db.fresh_live("5106912")
    assert cached["Width"] == cells["Width"] and extra == {"Price (USD)": "139.02"}  # lists are not stored
    assert db.get("5106912")["hits"] == 1
    assert db.fresh_live("5106912", max_age_hours=0) is None  # too old
    db.upsert("5106935", cells, {}, "catalog")
    assert db.fresh_live("5106935") is None  # only live pages are reused
    assert db.stats()["by_source"] == {"live": 1, "catalog": 1}
    assert [r["product_id"] for r in db.list("6 in")] and db.list("nope") == []
    assert db.clear() == 2 and db.stats()["products"] == 0


def test_seed_never_replaces_live(tmp_path):
    db = ProductDB(tmp_path / "p.db")
    db.upsert("5106912", {"Description": Cell("live", "ferguson_page", "high", "u")}, {}, "live")
    added = db.seed_from_catalog(CatalogSource())
    assert added == 55 and db.get("5106912")["source"] == "live"


def test_save_item_skips_items_read_from_the_db(tmp_path):
    db = ProductDB(tmp_path / "p.db")
    item = Item(0, "5106912", cells={"Description": Cell("d", "catalog", "high", "s")}, lookup_status="Found",
                found_via="catalog", extra={"from_db": "2026-10-16 10:00"})
    db.save_item(item)
    assert db.get("5106912") is None
