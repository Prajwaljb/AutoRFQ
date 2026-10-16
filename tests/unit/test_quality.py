import json
from types import SimpleNamespace

import pytest

from conftest import EMAILS
from rfq import config
from rfq.models import Cell, Item, RunResult, RunStatus
from rfq.quality import llm, rules, summary, units
import rfq.quality as quality


@pytest.mark.parametrize("column,value,expected", [
    ("Length", "1000", ("1000 ft", "unit added")),
    ("Length", "1000 ft", ("1000 ft", None)),
    ("Length", "300 in", ("25 ft", "converted")),
    ("Width", "6", ("6 in", "unit added")),
    ("Width", "76.2 mm", ("3 in", "converted")),
    ("Thickness", "0.004 in", ("4 mil", "converted")),
    ("Weight", "14.25", ("14.25 lb", "unit added")),
    ("Weight", "about 3 kg", ("about 3 kg", None)),
    ("Length", "333.33 yds.", ("1000 ft", "converted")),
])
def test_standardise(column, value, expected):
    assert units.standardise(column, value) == expected


def test_never_a_quiet_fix():
    """"300 in" on a 300 ft tape is a typo: left unchanged, and flagged by the rules."""
    assert units.standardise("Length", "300 in", "6 in. x 300 ft. Detectable Sewer Tape") == ("300 in", None)
    assert units.standardise("Length", "9000 m") == ("9000 m", None)  # implausible after conversion
    it = item(Description="6 in. x 300 ft. Detectable Sewer Tape", Length="300 in", Width="6 in",
              Thickness="5 mil", Material="Plastic", Color_Finish="Green")
    found = {(f.column, f.rule, f.severity) for f in rules.check_item(it)}
    assert ("Length", "wrong_unit", "high") in found


def cell(v):
    return Cell(v, "catalog", "high", "src")


def item(**cells):
    it = Item(0, "5106912", cells={k.replace("_", " "): cell(v) for k, v in cells.items()},
              lookup_status=config.FOUND)
    return it


def rules_of(it):
    """Rule flags other than blanks (every blank is a low "missing" flag)."""
    return {(f.column, f.rule, f.severity) for f in rules.check_item(it) if f.rule != "missing"}


def test_normalise_keeps_the_source_and_notes_it():
    r = RunResult("r", "e.eml", "offline")
    it = item(Description="x", Length="1000", Width="3")
    assert units.normalise(it, r) == 2
    assert it.cells["Length"].value == "1000 ft" and it.cells["Length"].source_type == "catalog"
    assert "unit normalised by the quality agent" in it.cells["Length"].source
    assert len(r.notes) == 2


def test_rule_flags():
    clean = item(Description='6 in x 1000 ft Blue Detector Tape', Length="1000 ft", Width="6 in",
                 Thickness="5 mil", Material="Plastic", Color_Finish="Blue")
    assert rules_of(clean) == set()
    wrong = item(Description='6 in x 1000 ft Blue Detector Tape', Length="1000 ft", Width="3 in",
                 Thickness="5 mil", Material="Plastic", Color_Finish="Red", Product_details="[]")
    assert ("Lettering", "missing", "low") in {(f.column, f.rule, f.severity) for f in rules.check_item(wrong)}
    assert rules_of(wrong) == {("Width", "description_mismatch", "high"),
                               ("Color Finish", "description_mismatch", "medium"),
                               ("Product details", "placeholder", "medium")}
    assert ("Length", "missing_key_value", "high") in rules_of(item(Description="tape", Width="6 in"))
    assert ("Width", "out_of_range", "high") in rules_of(item(Description="tape", Length="1000 ft",
                                                              Width="60 in"))
    clash = item(Description="6 in x 1000 ft Green Detector Tape", Length="1000 ft", Width="6 in",
                 Application="Water|Marking|Underground", Lettering="Caution Buried Sewer Line Below",
                 Color_Finish="Green")
    assert ("Application", "application_mismatch", "medium") in rules_of(clash)


def test_email1_is_ready_and_unchanged():
    from rfq import pipeline
    from conftest import sheet_rows
    import tempfile
    from pathlib import Path
    out = Path(tempfile.mkdtemp())
    result, folder = pipeline.run(EMAILS / "email-1-ids-in-body.eml", out, mode="offline")
    assert result.status == RunStatus.READY and result.units_converted == 0
    assert [f for f in result.flags if f.severity == "high"] == []
    ref = config.REFERENCE
    assert sheet_rows(folder / "RFQ.xlsx", "RFQ") == sheet_rows(ref, "RFQ")


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        content = json.dumps(self.reply) if not isinstance(self.reply, str) else self.reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def found_result():
    r = RunResult("r", "e.eml", "offline")
    r.items.append(item(Description="6 in x 1000 ft Detector Tape", Length="1000 ft", Width="6 in",
                        Thickness="5 mil", Material="Plastic", Color_Finish="Blue",
                        Lettering="Caution Buried Gas Line Below"))
    return r


def test_ai_is_advisory_grounded_and_verified(monkeypatch):
    r = found_result()
    fake = FakeLLM({"flags": [
        # a real contradiction (gas lettering on blue tape): kept, as advisory
        {"column": "Lettering", "issue": "Gas lettering on blue tape", "severity": "high",
         "quoted_value": "Caution Buried Gas Line Below", "conflicts_with": "Color Finish"},
        # not grounded: the quoted value is not the cell's value
        {"column": "Width", "issue": "invented", "severity": "high", "quoted_value": "4 in", "conflicts_with": "Description"},
        # code verifies and rejects: blue is named in the colour itself
        {"column": "Color Finish", "issue": "odd", "severity": "high", "quoted_value": "Blue", "conflicts_with": "Color Finish"},
        # hedged, and about a descriptive column: dropped
        {"column": "Material", "issue": "may be wrong", "severity": "medium", "quoted_value": "Plastic", "conflicts_with": "Description"},
    ]})
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: fake)
    quality.run(r)
    assert r.status == RunStatus.READY  # a model flag never holds the RFQ
    assert [(f.column, f.origin, f.severity) for f in r.ai_suggestions] == [("Lettering", "ai", "medium")]
    assert r.items[0].cells["Lettering"].value == "Caution Buried Gas Line Below"
    sent = json.loads(fake.calls[0]["messages"][1]["content"])
    assert set(sent) == {"product_id", "row"}  # product data only, never the email


def test_model_claim_that_code_disproves_is_dropped():
    it = item(Description="6 in x 1000 ft Purple Detector Tape", Lettering="Caution Buried Reclaimed Water Line Below",
              Color_Finish="Purple", Application="Reclaimed Water|Marking")
    assert not llm.verified(it, "Lettering", "Color Finish", set())  # purple IS reclaimed water (APWA)
    assert not llm.verified(it, "Lettering", "Application", set())   # both say reclaimed


@pytest.mark.parametrize("fake", [FakeLLM(error=TimeoutError("slow")), FakeLLM(reply="not json")])
def test_ai_failures_are_skipped(monkeypatch, fake):
    r = found_result()
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: fake)
    quality.run(r)
    assert r.ai_suggestions == [] and "skipped" in r.ai_status and r.status == RunStatus.READY


def test_ai_not_configured(monkeypatch):
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(name, raising=False)
    r = found_result()
    quality.run(r)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = found_result()
    quality.run(r)
    assert r.ai_status == "LLM check skipped: no OpenAI or Azure OpenAI key set"


def test_fill_rate_and_request_lines():
    r = found_result()
    r.items[0].qty = "10 rolls"
    r.items[0].extra = {"Price (USD)": "139.02", "Availability": "OutOfStock"}
    overall, by_column = summary.fill_rates(r)
    assert overall == round(100 * 7 / len(summary.FILL_COLUMNS), 1)
    assert summary.product_fill(r)[0][2:4] == (7, len(summary.FILL_COLUMNS))
    lines, total = summary.request_lines(r)
    assert lines[0][4] == 1390.2 and total == 1390.2
    assert any("Out of stock" in a for _, a in summary.alerts(r))


def test_openai_key_is_enough(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    assert llm.enabled() and llm.model_name() == "gpt-test" and llm.settings()[0] == "openai"
