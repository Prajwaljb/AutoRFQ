"""The log of every email the system sends, in SQLite (out/db/mail.db).

One row per send attempt: when, which run, what kind, to whom, the subject, whether the mail server accepted it
and, if not, why. It is separate from the product database on purpose: "Clear DB" on the Admin page empties a
cache, never a record of what went to customers.

Kinds: reply (in the customer's thread), rfq_email (Email RFQ... to an address chosen in the dashboard),
fallback ("a person will follow up"), review_notice (a held RFQ is waiting).
"""
import os
import sqlite3
import threading
import time
from pathlib import Path

from rfq import config

KINDS = ("reply", "rfq_email", "fallback", "review_notice")
SCHEMA = """
CREATE TABLE IF NOT EXISTS mail_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          REAL NOT NULL,             -- unix time of the attempt
    run_id      TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL,
    to_addr     TEXT NOT NULL DEFAULT '',
    subject     TEXT NOT NULL DEFAULT '',
    attachments TEXT NOT NULL DEFAULT '',  -- file names, comma separated
    message_id  TEXT NOT NULL DEFAULT '',
    in_reply_to TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL,             -- sent / failed
    error       TEXT NOT NULL DEFAULT '',
    sent_by     TEXT NOT NULL DEFAULT ''   -- web app / mailbot.py / azure timer / dashboard
);
CREATE INDEX IF NOT EXISTS mail_log_run ON mail_log(run_id);
CREATE INDEX IF NOT EXISTS mail_log_at ON mail_log(at);
"""
_lock = threading.Lock()


def default_path():
    value = os.environ.get("RFQ_MAIL_DB", "").strip()
    if value:
        return Path(value)
    out = os.environ.get("RFQ_OUT_DIR", "").strip()
    return (Path(out) if out else config.ROOT / "out") / "db" / "mail.db"


def _connect(path=None):
    path = Path(path or default_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def record(message, kind, run_id="", status="sent", error="", by="", path=None):
    """Logs one send attempt. Never raises: a broken log must not stop a reply from going out."""
    try:
        attachments = ", ".join(p.get_filename() or "" for p in message.iter_attachments()) \
            if message.is_multipart() else ""
        with _lock, _connect(path) as conn:
            conn.execute(
                "INSERT INTO mail_log (at, run_id, kind, to_addr, subject, attachments, message_id, in_reply_to,"
                " status, error, sent_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), run_id, kind, str(message.get("To", "")), str(message.get("Subject", "")),
                 attachments, str(message.get("Message-ID", "")), str(message.get("In-Reply-To", "")), status,
                 str(error)[:300], by))
    except Exception:
        pass


def _entry(row):
    d = dict(row)
    d["at_text"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d["at"]))
    return d


def recent(limit=200, run_id="", status="", kind="", path=None):
    where, args = [], []
    for column, value in (("run_id", run_id), ("status", status), ("kind", kind)):
        if value:
            where.append(f"{column} = ?")
            args.append(value)
    sql = "SELECT * FROM mail_log" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    with _lock, _connect(path) as conn:
        return [_entry(r) for r in conn.execute(sql, (*args, max(1, min(int(limit), 1000))))]


def counts(path=None):
    with _lock, _connect(path) as conn:
        rows = conn.execute("SELECT status, COUNT(*) n FROM mail_log GROUP BY status").fetchall()
    out = {"sent": 0, "failed": 0}
    out.update({r["status"]: r["n"] for r in rows})
    return out


def backfill(runs_dir, path=None):
    """One-time import of the sends older versions recorded in run.json ("sent_to"). Skips what is logged."""
    import json
    try:
        with _lock, _connect(path) as conn:
            if conn.execute("SELECT COUNT(*) FROM mail_log").fetchone()[0]:
                return 0
    except Exception:
        return 0
    added = 0
    for folder in sorted(Path(runs_dir).glob("*/run.json")):
        try:
            run = json.loads(folder.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for sent in run.get("sent_to", []):
            try:
                at = time.mktime(time.strptime(sent.get("at", ""), "%Y-%m-%d %H:%M"))
            except ValueError:
                at = folder.stat().st_mtime
            with _lock, _connect(path) as conn:
                conn.execute("INSERT INTO mail_log (at, run_id, kind, to_addr, subject, status, sent_by)"
                             " VALUES (?,?,?,?,?,?,?)",
                             (at, folder.parent.name, "reply", sent.get("to", ""), run.get("subject", ""),
                              "sent", "earlier version"))
            added += 1
    return added
