import json

import pytest

from rfq import config
from rfq.models import Cell, Item, RunResult
from rfq.sources import merge
from rfq.sources.base import SourceUnavailable
from rfq.sources.catalog import CatalogSource
from rfq.sources.ferguson_live import (LiveSource, find_product_link, is_blocked, parse_product_html,
                                       shows_item)
from rfq.sources.spec_sheet import SpecSheetSource, read_values


def product_page(pid="5106912", pairs=None, name="6 in x 1000 ft Blue Detector Tape"):
    """A small page with the same structure as a ferguson.com product page."""
    pairs = pairs or [("Length", "1000 ft"), ("Width", "6 in"), ("Color Finish Name", "Blue"),
                      ("Application", "Water, Marking, Underground"), ("Material", "Aluminum Foil, Plastic")]
    rows = "".join(
        '<div class="d-flex c-product-details__specs__specsAttributes py-4">'
        f'<div class="font-weight-bold c-product-details__specs__attribute">\n {label}\n</div>\n'
        f'<div class="c-product-details__specs__attribute">\n {value}\n</div></div>' for label, value in pairs)
    ld = {"@context": "https://schema.org", "@type": "Product", "sku": pid, "name": name,
          "description": ["Pro-Line<CQUOTA/>s tape", "Durable"], "brand": {"@type": "Brand", "name": "Presco"},
          "image": [f"https://i.ferg-img.com/i/fergusonprod/{pid}_1_primary"],
          "offers": {"@type": "Offer", "price": "139.02", "availability": "InStock"}}
    return (f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head><body>'
            f"<h1>{name}</h1><span>Item #{pid}</span>{rows}</body></html>")


def test_parse_product_page():
    values, extra = parse_product_html(product_page(), "5106912")
    assert values["Color Finish"] == "Blue"
    assert values["Application"] == "Water|Marking|Underground"
    assert values["Material"] == "Aluminum Foil|Plastic"
    assert values["Product details"] == "Pro-Line's tape|Durable"
    assert values["Image"] == values["Picture"] == "https://i.ferg-img.com/i/fergusonprod/5106912_1_primary"
    assert extra == {"Price (USD)": "139.02", "Availability": "InStock", "Brand": "Presco"}


def test_right_product_and_search_link():
    assert shows_item(product_page(), "5106912")
    assert not shows_item(product_page(), "5106913")
    search = '<a href="/product/pro-pak-6-in-water-tape-pdtwu/225123.html?x=1">x</a> Item #2513'
    assert find_product_link(search, "225123") == \
        "https://www.ferguson.com/product/pro-pak-6-in-water-tape-pdtwu/225123.html"
    assert find_product_link(search, "999999") is None


def test_block_detection():
    assert is_blocked("<html><body>Access Denied</body></html>", 200)
    assert is_blocked(product_page(), 403)
    assert is_blocked("<html><title>Pardon Our Interruption</title></html>", 200)
    assert not is_blocked(product_page(), 200)


def test_replay_reads_the_page_cache(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "5106912.html").write_text(product_page(), encoding="utf-8")
    (pages / "5106912.json").write_text(json.dumps({"url": "https://www.ferguson.com/x/5106912.html"}))
    live = LiveSource("http://127.0.0.1:1", tmp_path, replay=True)
    cells = live.lookup("5106912")
    assert cells["Width"] == Cell("6 in", "ferguson_page", "high", cells["Width"].source)
    assert cells["Width"].source.startswith("https://www.ferguson.com/x/5106912.html (read ")
    with pytest.raises(SourceUnavailable):
        live.lookup("5106935")  # not cached


def test_layout_change_is_not_found_with_blanks(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "5106912.html").write_text("<html><body>Item #5106912 new layout</body></html>", encoding="utf-8")
    with pytest.raises(SourceUnavailable, match="layout"):
        LiveSource("x", tmp_path, replay=True).lookup("5106912")


@pytest.mark.parametrize("column,a,b,expected", [
    ("Length", "1000", "1000 ft", True),
    ("Length", "300", "300 in", False),     # a bare length is feet
    ("Width", "6", "6 in", True),
    ("Application", "Water|Marking", "Marking|Water", True),
    ("ASTM", "ASTM D-2103 2008|ASTM D-882 2009", "ASTM D-882|ASTM D-2103", True),
    ("Image", "https://a", "https://a|https://b", True),
    ("Lettering", "Caution Buried Water Line Below", "Caution Buried Reclaimed Water Line Below", False),
])
def test_same(column, a, b, expected):
    assert merge.same(column, a, b) is expected


def cell(v, t="catalog"):
    return Cell(v, t, "high", "s")


def test_live_wins_and_differences_are_noted():
    result = RunResult("r", "e.eml", "live")
    item = Item(0, "5106912")
    cells = merge.live_over_catalog(item, {"Length": cell("1000 ft", "ferguson_page"),
                                           "OSHA": cell("OSHA 1910.144", "ferguson_page")},
                                    {"Length": cell("1000"), "OSHA": cell("OSHA 1910.144;OSHA 1926-956"),
                                     "Weight": cell("14.25 lb")}, result)
    assert cells["Length"].source_type == "ferguson_page" and cells["Weight"].value == "14.25 lb"
    assert [n.text.split(":")[0] for n in result.notes] == ["OSHA"]


def test_spec_fills_blanks_only():
    result = RunResult("r", "e.eml", "no-browser")
    item = Item(0, "9677514", cells={"Thickness": cell("4 mil"), "Material": cell("Plastic")})
    filled = merge.fill_from_spec(item, {"Thickness": cell("3 mil", "spec_sheet"),
                                         "Material": cell("Polyethylene Film", "spec_sheet"),
                                         "ASTM": cell("ASTM D-2103", "spec_sheet")}, result)
    assert filled == 1 and item.cells["ASTM"].source_type == "spec_sheet"
    assert item.cells["Thickness"].value == "4 mil"
    assert [n.text.split(":")[0] for n in result.notes] == ["Thickness"]  # Material wording is not a conflict


def test_spec_reader_on_bundled_pdf():
    index = json.loads((config.SPEC_CACHE / "index.json").read_text(encoding="utf-8"))
    values = read_values((config.SPEC_CACHE / index["4570880"]).read_bytes())
    assert values["Thickness"][0] == "5 mil"
    assert "ASTM D-2103" in values["ASTM"][0].split("|")
    assert values["ASTM"][1] >= 1 and values["ASTM"][2]  # page number and snippet kept


def test_spec_source_uses_bundled_copy_and_drops_bad_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SPEC_DOWNLOAD", False)
    (tmp_path / "4570880.pdf").write_bytes(b"<html>half written</html>")
    spec = SpecSheetSource(tmp_path)
    cells = spec.lookup("4570880")
    assert spec.last_origin == "bundled" and not (tmp_path / "4570880.pdf").exists()
    assert cells["ASTM"].source_type == "spec_sheet" and cells["ASTM"].confidence == "medium"
    assert "(page " in cells["ASTM"].source
    assert spec.lookup("5106912999") == {} and spec.last_problem == "no spec sheet link"


def test_catalog_near_misses():
    catalog = CatalogSource()
    assert "9677531" in catalog.nearest_ids("9677533")
    assert catalog.nearest_ids("1234567") == []
