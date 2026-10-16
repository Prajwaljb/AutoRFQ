"""The web API: start runs, read them, review, approve, and refuse what it should refuse."""
import time

import pytest
from fastapi.testclient import TestClient

from conftest import EMAILS


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import settings
    monkeypatch.setattr(settings, "OUT", tmp_path)
    monkeypatch.setattr(settings, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(settings, "INBOX", tmp_path / "inbox")
    monkeypatch.setattr(settings, "CACHE", tmp_path / ".cache")
    monkeypatch.setattr(settings.mailbot, "BOT_EMAIL", "")
    monkeypatch.setattr(settings.mailbot, "BOT_PASSWORD", "")
    from app.main import app
    return TestClient(app)


def wait_done(client, run_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        row = [r for r in client.get("/api/runs").json()["runs"] if r["id"] == run_id][0]
        if row["status"] != "processing":
            return row
        time.sleep(0.3)
    raise AssertionError("run did not finish")


def test_sample_run_lifecycle(client):
    r = client.post("/api/runs", data={"sample": "email-4-messy-forward", "mode": "offline"})
    assert r.status_code == 200
    run_id = r.json()["id"]
    row = wait_done(client, run_id)
    assert row["status"] == "ready" and row["found"] == 5 and row["items"] == 7
    detail = client.get(f"/api/runs/{run_id}").json()
    assert {"RFQ.xlsx", "reply.eml", "run.log"} <= set(detail["files"])
    assert detail["review"]["can_approve"] and detail["mail_configured"] is False
    assert client.get(f"/api/runs/{run_id}/files/RFQ.xlsx").status_code == 200
    preview = client.get(f"/api/runs/{run_id}/preview").json()
    assert preview["attachments"] == ["RFQ.xlsx"] and "Products found: 5 of 7" in preview["text"]
    assert "5106926" in client.get(f"/api/runs/{run_id}/email").json()["texts"][0]["text"]
    events = client.get(f"/api/runs/{run_id}/events").text
    assert '"type": "run_done"' in events and '"type": "end"' in events


def test_upload_checks(client):
    bad = client.post("/api/runs", files={"file": ("list.txt", b"5106912", "text/plain")})
    assert bad.status_code == 400
    ok = client.post("/api/runs", data={"mode": "offline"},
                     files={"file": ("../../evil name.eml", (EMAILS / "email-1-ids-in-body.eml").read_bytes(),
                                     "message/rfc822")})
    assert ok.status_code == 200
    run_id = ok.json()["id"]
    assert "/" not in run_id and ".." not in run_id
    assert wait_done(client, run_id)["status"] == "ready"
    assert client.post("/api/runs", data={"sample": "../reference/x"}).status_code == 404


def test_path_traversal_is_refused(client):
    assert client.get("/api/runs/..").status_code == 404
    assert client.get("/api/runs/uploads").status_code == 404
    assert client.get("/api/runs/x/files/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/pages/..%2Fx/screenshot").status_code == 404


def test_review_and_approve_without_mail(client, tmp_path, monkeypatch):
    from rfq import pipeline
    from rfq.sources.catalog import CatalogSource
    original = CatalogSource.lookup

    def wrong(self, pid):
        cells = original(self, pid)
        if pid == "5106912":
            cells["Width"].value = "60 in"
        return cells
    monkeypatch.setattr(CatalogSource, "lookup", wrong)
    _, folder = pipeline.run(EMAILS / "email-1-ids-in-body.eml", tmp_path, mode="offline")
    monkeypatch.setattr(CatalogSource, "lookup", original)
    run_id = folder.name
    review = client.get(f"/api/runs/{run_id}").json()["review"]
    assert not review["can_approve"]
    assert client.post(f"/api/runs/{run_id}/approve", json={"reviewer": "Asha"}).status_code == 400
    high = [f for f in review["flags"] if f["severity"] == "high"]
    for n, f in enumerate(high):
        r = client.post(f"/api/runs/{run_id}/review",
                        json={"flag_id": f["id"], "action": "edit", "value": "6 in", "reviewer": "Asha", "version": n})
        assert r.status_code == 200
    stale = client.post(f"/api/runs/{run_id}/review",
                        json={"flag_id": high[0]["id"], "action": "keep", "reviewer": "Ben", "version": 0})
    assert stale.status_code == 409
    approved = client.post(f"/api/runs/{run_id}/approve", json={"reviewer": "Asha", "send": True}).json()
    assert approved["status"] == "approved" and "not set up" in approved["send_error"]
    assert client.post(f"/api/runs/{run_id}/send").status_code == 400  # mail not configured: never "sent"
    assert client.get(f"/api/runs/{run_id}").json()["summary"]["status"] == "approved"


def test_health_samples_selfcheck(client):
    health = client.get("/api/health").json()
    assert set(health) >= {"chrome", "ai", "inbox", "mail", "mode"}
    assert len(client.get("/api/samples").json()["samples"]) == 4
    check = client.post("/api/selfcheck").json()
    assert check == {**check, "ok": True, "rows": "6/6", "sources": "105/105"}
