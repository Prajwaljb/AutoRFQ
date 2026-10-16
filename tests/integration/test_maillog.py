"""The log of sent emails (SQLite), the out/ layout migration and the /api/mail-log route."""
import json
from email.message import EmailMessage

import pytest

from rfq.infra import layout, maillog


def message(to="buyer@example.org", subject="Re: RFQ", attach=True):
    m = EmailMessage()
    m["To"], m["Subject"], m["Message-ID"], m["In-Reply-To"] = to, subject, "<new@x>", "<orig@x>"
    m.set_content("hello")
    if attach:
        m.add_attachment(b"x", maintype="application", subtype="octet-stream", filename="RFQ.xlsx")
    return m


def test_record_and_filter(tmp_path):
    db = tmp_path / "db" / "mail.db"
    maillog.record(message(), "reply", "run-a", by="web app", path=db)
    maillog.record(message("b@example.org"), "rfq_email", "run-b", "failed", "SMTPException: nope", "dashboard", db)
    rows = maillog.recent(path=db)
    assert [r["run_id"] for r in rows] == ["run-b", "run-a"]  # newest first
    assert rows[1]["attachments"] == "RFQ.xlsx" and rows[1]["in_reply_to"] == "<orig@x>"
    assert rows[0]["status"] == "failed" and "nope" in rows[0]["error"]
    assert [r["run_id"] for r in maillog.recent(run_id="run-a", path=db)] == ["run-a"]
    assert [r["kind"] for r in maillog.recent(status="failed", path=db)] == ["rfq_email"]
    assert maillog.counts(db) == {"sent": 1, "failed": 1}


def test_a_broken_log_never_raises(tmp_path):
    maillog.record(message(), "reply", path=tmp_path)  # a folder, not a database file


def test_backfill_imports_old_sent_to_once(tmp_path):
    run = tmp_path / "runs" / "old-run"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"subject": "RFQ x", "sent_to": [
        {"to": "a@example.org", "at": "2026-10-16 12:30"}]}), encoding="utf-8")
    db = tmp_path / "mail.db"
    assert maillog.backfill(tmp_path / "runs", db) == 1
    assert maillog.backfill(tmp_path / "runs", db) == 0  # only into an empty log
    [row] = maillog.recent(path=db)
    assert row["run_id"] == "old-run" and row["to_addr"] == "a@example.org" and row["at_text"].startswith("2026-10-16 12:30")


def test_layout_migration_moves_runs_and_database(tmp_path):
    (tmp_path / "email-1-20261016").mkdir()
    (tmp_path / "email-1-20261016" / "run.json").write_text("{}")
    (tmp_path / "inbox").mkdir()
    (tmp_path / "products.db").write_bytes(b"db")
    (tmp_path / "notes").mkdir()  # not a run: left alone
    assert layout.migrate(tmp_path) == 2
    assert (tmp_path / "runs" / "email-1-20261016" / "run.json").exists()
    assert (tmp_path / "db" / "products.db").read_bytes() == b"db" and not (tmp_path / "products.db").exists()
    assert (tmp_path / "inbox").is_dir() and (tmp_path / "notes").is_dir()
    assert layout.migrate(tmp_path) == 0  # idempotent


def test_mailbot_send_logs_success_and_failure(monkeypatch, tmp_path):
    import mailbot
    db = tmp_path / "mail.db"
    monkeypatch.setenv("RFQ_MAIL_DB", str(db))

    class Smtp:
        fail = False

        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

        def login(self, *a):
            if Smtp.fail:
                raise OSError("connection refused")

        def send_message(self, m):
            pass

    monkeypatch.setattr(mailbot.smtplib, "SMTP_SSL", Smtp)
    mailbot.send(message(), "reply", "run-1", "web app")
    Smtp.fail = True
    with pytest.raises(OSError):
        mailbot.send(message(), "fallback", "run-2", "mailbot.py")
    rows = {r["run_id"]: r for r in maillog.recent(path=db)}
    assert rows["run-1"]["status"] == "sent" and rows["run-1"]["sent_by"] == "web app"
    assert rows["run-2"]["status"] == "failed" and "connection refused" in rows["run-2"]["error"]


def test_mail_log_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("RFQ_MAIL_DB", str(tmp_path / "mail.db"))
    maillog.record(message(), "reply", "run-z", by="web app")
    from app.main import app
    data = TestClient(app).get("/api/mail-log", params={"run_id": "run-z"}).json()
    assert [e["to_addr"] for e in data["entries"]] == ["buyer@example.org"]
    assert data["counts"]["sent"] >= 1 and "reply" in data["kinds"]
