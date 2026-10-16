"""The web API: start runs, read them, review, approve, and refuse what it should refuse."""
import os
import time

import pytest
from fastapi.testclient import TestClient

from conftest import EMAILS


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import settings
    monkeypatch.setattr(settings, "OUT", tmp_path)
    monkeypatch.setattr(settings, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(settings, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(settings, "INBOX", tmp_path / "inbox")
    monkeypatch.setattr(settings, "CACHE", tmp_path / ".cache")
    monkeypatch.setattr(settings.mailbot, "OUT", tmp_path)
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
    _, folder = pipeline.run(EMAILS / "email-1-ids-in-body.eml", settings_runs(tmp_path), mode="offline")
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


def test_upload_page(client):
    assert "Build the RFQ" in client.get("/rfq").text
    r = client.post("/rfq", files={"file": ("email-2.eml", (EMAILS / "email-2-ids-in-attachment.eml").read_bytes(),
                                            "message/rfc822")})
    assert r.status_code == 200 and "Download RFQ.xlsx" in r.text and "Quality agent" in r.text
    import re
    href = re.search(r'href="(/api/runs/[^"]+/files/RFQ\.xlsx)"', r.text).group(1)
    assert client.get(href).status_code == 200
    assert client.post("/rfq", files={"file": ("x.txt", b"5106912", "text/plain")}).status_code == 400


def test_health_lists_settings_without_values(client):
    settings = client.get("/api/health").json()["settings"]
    assert set(settings) == {"mail", "ai", "search", "run"}
    assert all(isinstance(v, bool) for group in settings.values() for v in group.values())


def test_function_app_wraps_the_api(monkeypatch):
    pytest.importorskip("azure.functions")
    for name in ("RFQ_MODE", "RFQ_OUT_DIR", "RFQ_AUTO_BROWSER"):  # function_app sets cloud defaults:
        monkeypatch.setenv(name, os.environ.get(name, ""))      # restore them after this test
    import function_app
    assert os.environ["RFQ_MODE"] in ("", "no-browser")
    fns = {f.get_function_name(): f for f in function_app.app.get_functions()}
    http = [f for f in fns.values() if getattr(f.get_bindings()[0], "route", None) == "/{*route}"]
    assert len(http) == 1 and "inbox_timer" in fns  # the API, plus the inbox check every minute


def test_inbox_status_reports_the_heartbeat(client):
    import json
    import time
    from app import settings
    beat = settings.mailbot.OUT / ".mailbot.json"
    beat.write_text(json.dumps({"email": "bot@x", "at": time.time(), "by": "web app", "error": ""}))
    try:
        info = client.get("/api/health").json()["inbox_info"]
        assert info["watching"] and info["by"] == "web app"
        beat.write_text(json.dumps({"email": "bot@x", "at": time.time(), "by": "web app", "error": "login failed"}))
        assert client.get("/api/health").json()["inbox"] is False
    finally:
        beat.unlink()


def test_mail_test_without_credentials(client):
    r = client.post("/api/mail/test").json()
    assert r["ok"] is False and "not set" in r["detail"]


def test_admin_product_database(client, tmp_path, monkeypatch):
    monkeypatch.setenv("RFQ_PRODUCTS_DB", str(tmp_path / "admin.db"))
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert client.get("/api/admin/products").json()["stats"]["products"] == 0
    assert client.post("/api/admin/seed").json()["added"] == 56
    listing = client.get("/api/admin/products", params={"q": "Purple"}).json()
    assert listing["products"] and all("purple" in p["description"].lower() for p in listing["products"])
    assert client.get("/api/admin/products/5106912").json()["source"] == "catalog"
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    assert client.post("/api/admin/clear-db").status_code == 403
    assert client.post("/api/admin/clear-db", headers={"X-Admin-Token": "s3cret"}).json()["cleared"] == 56
    assert client.get("/api/admin/products/5106912").status_code == 404


def test_send_rules(client, monkeypatch):
    """Uploaded RFQs never reply to their (sample) sender; a typed address is checked; held RFQs wait."""
    from app.services import mailer
    from app.settings import mailbot
    sent = []
    monkeypatch.setattr(mailbot, "BOT_EMAIL", "bot@example.com")
    monkeypatch.setattr(mailbot, "BOT_PASSWORD", "x")
    monkeypatch.setattr(mailer.settings, "refresh", lambda: None)
    monkeypatch.setattr(mailbot, "send", lambda msg, *a, **k: sent.append(msg))
    run_id = client.post("/api/runs", data={"sample": "email-1-ids-in-body", "mode": "offline"}).json()["id"]
    assert wait_done(client, run_id)["status"] == "ready"
    r = client.post(f"/api/runs/{run_id}/send", json={})
    assert r.status_code == 400 and "uploaded" in r.json()["detail"] and sent == []
    assert client.post(f"/api/runs/{run_id}/send", json={"to": "nope"}).status_code == 400
    r = client.post(f"/api/runs/{run_id}/send", json={"to": "buyer@example.org"})
    assert r.status_code == 200 and sent[0]["To"] == "buyer@example.org"
    assert [p.get_filename() for p in sent[0].iter_attachments()] == ["RFQ.xlsx"]
    assert client.get(f"/api/runs/{run_id}").json()["run"]["sent_to"][0]["to"] == "buyer@example.org"


def settings_runs(out):
    """Where the app looks for runs under an output folder (out/runs)."""
    return out / "runs"
