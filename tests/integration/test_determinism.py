"""Same email in, same values out: twice in a row, and whatever order the lookups finish in."""
import re

from conftest import EMAILS, all_values, run_build

import rfq.pipeline as pipeline


def test_two_builds_give_the_same_values(offline_builds, tmp_path):
    for eml in sorted(EMAILS.glob("*.eml")):
        assert run_build(eml, tmp_path, "--offline").returncode == 0
        assert all_values(tmp_path / eml.stem / "RFQ.xlsx") == all_values(offline_builds / eml.stem / "RFQ.xlsx")


def test_lookup_order_does_not_change_the_output(tmp_path, monkeypatch):
    eml = EMAILS / "email-4-messy-forward.eml"
    pipeline.run(eml, tmp_path / "a", mode="offline")
    monkeypatch.setattr(pipeline, "lookup_order", lambda items: list(reversed(items)))
    pipeline.run(eml, tmp_path / "b", mode="offline")
    a = all_values(tmp_path / "a" / eml.stem / "RFQ.xlsx")
    b = all_values(tmp_path / "b" / eml.stem / "RFQ.xlsx")
    assert a == b


def test_no_timings_in_outputs(offline_builds):
    timing = re.compile(r"\b\d+(\.\d+)?\s?(s|sec|secs|seconds|ms|min|minutes)\b(?!\w)", re.IGNORECASE)
    for folder in offline_builds.iterdir():
        if not (folder / "RFQ.xlsx").exists():
            continue
        for sheet in all_values(folder / "RFQ.xlsx").values():
            for row in sheet:
                for v in row:
                    assert not (isinstance(v, str) and timing.search(v) and "processed in" in v.lower())
        reply = (folder / "reply.eml").read_text(encoding="utf-8", errors="replace").lower()
        assert "processed in" not in reply and "seconds" not in reply
