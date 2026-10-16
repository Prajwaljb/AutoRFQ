"""The product database: every product the flow has looked up, in one place (SQLite).

- Live runs read a product from here when it was fetched from ferguson.com within RFQ_DB_TTL_HOURS
  (default 24) instead of opening the page again, so a second RFQ for the same items needs no browser.
- Every found product is written back with its cells, sources, price and stock, which source it came from
  and when. That makes the database the shared product store for the web app, the bot and later
  scaling (swap SQLite for a server database behind the same functions).
- Offline and no-browser runs never read from it, so they stay repeatable (the reference test is offline).

Location: RFQ_PRODUCTS_DB, else out/db/products.db (on Azure Functions /tmp/autorfq/products.db).
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from rfq import config
from rfq.models import Cell

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    product_id   TEXT PRIMARY KEY,
    description  TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL,            -- live / catalog / spec / human_review
    url          TEXT NOT NULL DEFAULT '',
    cells        TEXT NOT NULL,            -- {column: {value, source_type, confidence, source}}
    extra        TEXT NOT NULL DEFAULT '{}',
    fetched_at   REAL NOT NULL,            -- unix time of the lookup that produced this row
    updated_at   REAL NOT NULL,
    hits         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS products_source ON products(source);
CREATE TABLE IF NOT EXISTS crossrefs (
    code         TEXT PRIMARY KEY,         -- competitor / customer code, upper case
    brand        TEXT NOT NULL DEFAULT '',
    info         TEXT,                     -- JSON from the competitor finder; NULL = the web knows nothing
    confirmed    TEXT NOT NULL DEFAULT '', -- Ferguson item a reviewer chose for it
    confirmed_by TEXT NOT NULL DEFAULT '',
    updated_at   REAL NOT NULL
);
"""
CROSSREF_DAYS = 30
_lock = threading.Lock()


def default_path():
    value = os.environ.get("RFQ_PRODUCTS_DB", "").strip()
    if value:
        return Path(value)
    out = os.environ.get("RFQ_OUT_DIR", "").strip()
    return (Path(out) if out else config.ROOT / "out") / "db" / "products.db"


def ttl_hours():
    try:
        return float(os.environ.get("RFQ_DB_TTL_HOURS", "24"))
    except ValueError:
        return 24.0


class ProductDB:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    # reads ------------------------------------------------------------------------------------------
    def get(self, product_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM products WHERE product_id = ?", (product_id,)).fetchone()
        return _row(row) if row else None

    def fresh_live(self, product_id, max_age_hours=None):
        """A product fetched live within the TTL, as (cells, extra, record), or None."""
        record = self.get(product_id)
        hours = ttl_hours() if max_age_hours is None else max_age_hours
        if not record or record["source"] != "live" or time.time() - record["fetched_at"] > hours * 3600:
            return None
        with _lock, self._connect() as db:
            db.execute("UPDATE products SET hits = hits + 1 WHERE product_id = ?", (product_id,))
        cells = {c: Cell(**v) for c, v in record["cells"].items()}
        return cells, dict(record["extra"]), record

    def list(self, query="", limit=200):
        sql, args = "SELECT * FROM products", []
        if query:
            sql += " WHERE product_id LIKE ? OR description LIKE ?"
            args = [f"%{query}%", f"%{query}%"]
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(int(limit))
        with self._connect() as db:
            return [_row(r) for r in db.execute(sql, args).fetchall()]

    def stats(self):
        with self._connect() as db:
            total = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            by_source = dict(db.execute("SELECT source, COUNT(*) FROM products GROUP BY source").fetchall())
            hits = db.execute("SELECT COALESCE(SUM(hits), 0) FROM products").fetchone()[0]
            last = db.execute("SELECT MAX(updated_at) FROM products").fetchone()[0]
            crossrefs = db.execute("SELECT COUNT(*) FROM crossrefs").fetchone()[0]
        return {"products": total, "by_source": by_source, "reused": hits, "last_updated": last, "crossrefs": crossrefs,
                "path": str(self.path), "ttl_hours": ttl_hours()}

    # writes -----------------------------------------------------------------------------------------
    def upsert(self, product_id, cells, extra, source, url="", fetched_at=None):
        now = time.time()
        description = cells["Description"].value if "Description" in cells else ""
        payload = json.dumps({c: vars(cell) for c, cell in cells.items()}, ensure_ascii=False)
        extra = {k: v for k, v in (extra or {}).items() if isinstance(v, (str, int, float))}
        with _lock, self._connect() as db:
            db.execute(
                "INSERT INTO products (product_id, description, source, url, cells, extra, fetched_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(product_id) DO UPDATE SET "
                "description = excluded.description, source = excluded.source, url = excluded.url, "
                "cells = excluded.cells, extra = excluded.extra, fetched_at = excluded.fetched_at, "
                "updated_at = excluded.updated_at",
                (product_id, description, source, url, payload, json.dumps(extra, ensure_ascii=False),
                 fetched_at or now, now))

    def save_item(self, item, url=""):
        """Stores a found item (after merging) under the source it came from."""
        if item.found and item.cells:
            source = item.found_via or "catalog"
            if item.extra.get("from_db"):
                return  # read from here: keep the original fetch time
            self.upsert(item.product_id, item.cells, item.extra, source, url or item.extra.get("Ferguson URL", ""))

    def seed_from_catalog(self, catalog):
        """Loads every backup-catalog product (never replaces a live one). Returns how many were added."""
        added = 0
        for pid in catalog.products:
            record = self.get(pid)
            if record and record["source"] == "live":
                continue
            self.upsert(pid, catalog.lookup(pid), catalog.extra(pid), "catalog",
                        catalog.extra(pid).get("Ferguson URL", ""))
            added += 1
        return added

    # competitor cross-references -----------------------------------------------------------------------
    def get_crossref(self, code, max_age_days=CROSSREF_DAYS):
        """The saved finding for a code (dict with "confirmed"), {} when the web knew nothing, None if unseen."""
        with self._connect() as db:
            row = db.execute("SELECT * FROM crossrefs WHERE code = ?", (code.upper(),)).fetchone()
        if not row or (not row["confirmed"] and time.time() - row["updated_at"] > max_age_days * 86400):
            return None
        info = json.loads(row["info"]) if row["info"] else {}
        if row["confirmed"]:
            info = {**info, "confirmed": row["confirmed"], "confirmed_by": row["confirmed_by"]}
        return info

    def save_crossref(self, code, brand, info):
        with _lock, self._connect() as db:
            db.execute("INSERT INTO crossrefs (code, brand, info, updated_at) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT(code) DO UPDATE SET brand = excluded.brand, info = excluded.info, "
                       "updated_at = excluded.updated_at",
                       (code.upper(), brand or "", json.dumps(info, ensure_ascii=False) if info else None, time.time()))

    def confirm_crossref(self, code, ferguson_id, reviewer):
        """A reviewer chose a Ferguson item for a competitor code: suggested first next time."""
        with _lock, self._connect() as db:
            db.execute("INSERT INTO crossrefs (code, confirmed, confirmed_by, updated_at) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT(code) DO UPDATE SET confirmed = excluded.confirmed, "
                       "confirmed_by = excluded.confirmed_by, updated_at = excluded.updated_at",
                       (code.upper(), ferguson_id, reviewer, time.time()))

    def list_crossrefs(self):
        with self._connect() as db:
            rows = db.execute("SELECT * FROM crossrefs ORDER BY updated_at DESC").fetchall()
        out = []
        for r in rows:
            info = json.loads(r["info"]) if r["info"] else {}
            out.append({"code": r["code"], "brand": r["brand"], "description": info.get("description", ""),
                        "sources": info.get("sources", []), "known": bool(info), "confirmed": r["confirmed"],
                        "confirmed_by": r["confirmed_by"], "updated_at": r["updated_at"]})
        return out

    def clear(self):
        with _lock, self._connect() as db:
            n = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            db.execute("DELETE FROM products")
            db.execute("DELETE FROM crossrefs")
        return n


def _row(row):
    record = dict(row)
    record["cells"] = json.loads(record["cells"])
    record["extra"] = json.loads(record["extra"] or "{}")
    return record
