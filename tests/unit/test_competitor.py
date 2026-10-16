"""Competitor Product Finder on recorded search results (no network)."""
from rfq.infra.productdb import ProductDB
from rfq.models import Item
from rfq.sources import competitor
from rfq.sources.alternatives import Alternatives
from rfq.sources.catalog import CatalogSource

MUTUAL = [
    {"link": "https://www.mutualindustries.com/product/non-detectable-underground-marking-tape",
     "title": "Non-Detectable Underground Marking Tape",
     "snippet": "17783-79-3000. 17783-79-6000. Part# 17783-25-3000. extra heavy 4.5 mil polyethylene tape"},
    {"link": "https://www.staples.com/mutual-industries-electric-line-underground-marking-tape",
     "title": 'Mutual Industries "Electric Line" Underground Marking ...',
     "snippet": '"Electric Line" Underground Marking Tape, 3" x 333.33 yds., Red (17783-79-3000). Price is $59.49'},
    {"link": "https://www.mutualindustries.com/product/3mil-barricade-tape", "title": "3Mil Barricade Tape",
     "snippet": "Designed to protect and identify above ground hazardous areas"},  # doesn't name the code
]
EMPIRE = [
    {"link": "https://www.porterpipe.com/1092014/product/empire-31-024", "title": "Empire® 31-024 Detectable Tape",
     "snippet": "31-024 Multi-Layer Premium Detectable Tape, Black/Blue/Silver, 1000 ft L x 6 in W x 5 mil."},
    {"link": "https://htosupply.com/product/empire-31-024", "title": "Empire Level 31-024 MAGNATEC",
     "snippet": 'Premium Detectable Tape Water Line 6" x 1000\''},
]
OTHER = [{"link": "https://www.3m.com/x", "title": "Double Sided Tape", "snippet": "3M VHB tape"}]


def test_specs_cite_their_page_and_yards_become_feet():
    found = competitor.extract_specs(MUTUAL, "17783-79-3000")
    s = found["specs"]
    assert s["Length"]["value"] == "1000 ft (given as 333.33 yds)"  # the deck's "333.33 yds." -> "1000 ft"
    assert s["Width"]["value"] == "3 in" and s["Color"]["value"] == "Red" and s["Utility"]["value"] == "Electric"
    assert s["Detectable"]["value"] == "No" and s["Thickness"]["value"] == "4.5 mil"
    assert s["Color"]["source"].startswith("https://www.staples.com/")
    assert len(found["sources"]) == 2  # the barricade page doesn't name the code: not used


def _finder(monkeypatch, results, tmp_path):
    monkeypatch.setattr(competitor, "search", lambda q, logger=None: results)
    monkeypatch.setenv("SERPAPI_API_KEY", "test")
    return Alternatives(CatalogSource(), web=True, db=ProductDB(tmp_path / "p.db"))


def test_mutual_gets_the_red_marking_tape(monkeypatch, tmp_path):
    item = Item(0, "17783-79-3000", kind="code", brand="Mutual Industries", line="Mutual Industries 17783-79-3000")
    _, origin, options = _finder(monkeypatch, MUTUAL, tmp_path).suggest(item)
    assert options[0]["product_id"] == "9677539" and options[0]["confidence"] == "strong"
    assert origin.startswith("web: https://") and item.extra["competitor"]["brand"] == "Mutual Industries"


def test_empire_gets_the_blue_water_detector_tape(monkeypatch, tmp_path):
    item = Item(0, "31-024", kind="code", brand="Empire", line="Empire 31-024")
    _, _, options = _finder(monkeypatch, EMPIRE, tmp_path).suggest(item)
    assert options[0]["product_id"] == "5106912" and options[0]["confidence"] == "strong"


def test_unknown_code_is_never_guessed_and_is_remembered(monkeypatch, tmp_path):
    finder = _finder(monkeypatch, OTHER, tmp_path)
    item = Item(0, "MTX-4409-XQ", kind="code", line="MTX-4409-XQ (customer's own code)")
    assert finder.suggest(item)[2] == []
    assert finder.db.get_crossref("MTX-4409-XQ") == {}  # searched once: "nothing known" is saved too
    monkeypatch.setattr(competitor, "search", lambda q, logger=None: (_ for _ in ()).throw(AssertionError("searched again")))
    assert finder.suggest(Item(0, "MTX-4409-XQ", kind="code"))[2] == []


def test_reviewer_choice_comes_first_next_time(monkeypatch, tmp_path):
    finder = _finder(monkeypatch, MUTUAL, tmp_path)
    finder.suggest(Item(0, "17783-79-3000", kind="code", brand="Mutual Industries"))
    finder.db.confirm_crossref("17783-79-3000", "5106978", "Asha")
    _, _, options = finder.suggest(Item(0, "17783-79-3000", kind="code", brand="Mutual Industries"))
    assert options[0]["product_id"] == "5106978" and options[0]["confidence"] == "confirmed"
    assert "confirmed by Asha" in options[0]["matched"]
