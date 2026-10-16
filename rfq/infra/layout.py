"""The folder layout of the output directory (RFQ_OUT_DIR, default out/), and the move from the old flat one.

    out/
      runs/<run id>/     RFQ.xlsx, reply.eml, run.json, run.log, events.jsonl, review.json (one folder per RFQ)
      inbox/             emails received by the bot (.eml)
      uploads/           emails uploaded in the dashboard (.eml)
      db/                products.db (cache, Admin can clear it), mail.db (log of sent emails, kept)
      .cache/            saved ferguson.com pages and spec sheet PDFs (for --replay)
      .mailbot.json      heartbeat: who last checked the inbox
"""
import shutil
from pathlib import Path

RESERVED = {"runs", "inbox", "uploads", "db", "selfcheck", "verify", "alt"}


def runs_dir(out):
    return Path(out) / "runs"


def migrate(out):
    """Moves run folders and products.db from the old flat layout into runs/ and db/. Safe to run every time.
    Returns how many things moved."""
    out = Path(out)
    if not out.is_dir():
        return 0
    moved = 0
    runs = runs_dir(out)
    for folder in sorted(out.iterdir()):
        if folder.is_dir() and folder.name not in RESERVED and not folder.name.startswith(".") \
                and ((folder / "run.json").exists() or (folder / "events.jsonl").exists()):
            runs.mkdir(exist_ok=True)
            if not (runs / folder.name).exists():
                shutil.move(str(folder), str(runs / folder.name))
                moved += 1
    old_db = out / "products.db"
    new_db = out / "db" / "products.db"
    if old_db.exists() and not new_db.exists():
        new_db.parent.mkdir(exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            if Path(str(old_db) + suffix).exists():
                shutil.move(str(old_db) + suffix, str(new_db) + suffix)
        moved += 1
    return moved
