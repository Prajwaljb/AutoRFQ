"""Reads runs from out/<run>/ (run.json, events.jsonl): web runs and mailbot runs alike."""
import json
import time
from pathlib import Path

from app import settings
from app.services import runner


class NotFound(Exception):
    pass


def run_dir(run_id):
    """The folder of a run, refusing anything outside out/."""
    if not settings.RUN_ID_RE.match(run_id or "") or run_id in settings.NOT_RUNS:
        raise NotFound(run_id)
    folder = (settings.OUT / run_id).resolve()
    if folder.parent != settings.OUT or not folder.is_dir():
        raise NotFound(run_id)
    return folder


def source_of(email_path):
    p = Path(email_path or "")
    if settings.INBOX in p.parents:
        return "inbox"
    if settings.UPLOADS in p.parents:
        return "upload"
    return "sample"


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summary(folder):
    """One row of the runs list, or None if the folder isn't a run."""
    run = _read_json(folder / "run.json")
    job = runner.job(folder.name)
    events = folder / "events.jsonl"
    if run is None and job is None and not events.exists():
        return None
    mtime = (folder / "run.json").stat().st_mtime if run else (events.stat().st_mtime if events.exists()
                                                               else time.time())
    if job and job["state"] in ("queued", "processing"):
        status = "processing"
    elif run is None:
        status = "failed"
    else:
        status = run.get("status", "ready")
    counts = dict((run or {}).get("counts", {}))
    if run and "fill_rate" not in counts:  # runs built before fill_rate was recorded
        try:
            from rfq.models import RunResult
            counts["fill_rate"] = RunResult.from_dict(run).fill_rate()
        except Exception:
            counts["fill_rate"] = 0
    first = _first_event(events) if run is None else {}
    return {
        "id": folder.name,
        "subject": (run or {}).get("subject") or first.get("subject", ""),
        "sender": (run or {}).get("sender") or first.get("sender", ""),
        "sender_name": (run or {}).get("sender_name", ""),
        "received": (run or {}).get("received", ""),
        "status": status,
        "mode": (run or {}).get("mode") or (job or {}).get("mode", ""),
        "source": source_of((run or {}).get("email_path") or (job or {}).get("email_path", "")),
        "items": counts.get("items", 0),
        "found": counts.get("found", 0),
        "not_found": counts.get("not_found", 0),
        "flags": counts.get("flags", 0),
        "high_flags": counts.get("high_flags", 0),
        "missing": counts.get("missing", 0),
        "fill_rate": counts.get("fill_rate", 0),
        "units_converted": (run or {}).get("units_converted", 0),
        "updated": mtime,
        "error": (job or {}).get("error", ""),
    }


def _first_event(path):
    try:
        with path.open(encoding="utf-8") as f:
            return json.loads(f.readline() or "{}")
    except (OSError, ValueError):
        return {}


def list_runs():
    if not settings.OUT.exists():
        return []
    rows = []
    for folder in settings.OUT.iterdir():
        if folder.is_dir() and not folder.name.startswith(".") and folder.name not in settings.NOT_RUNS:
            row = summary(folder)
            if row:
                rows.append(row)
    return rows


def detail(run_id):
    folder = run_dir(run_id)
    row = summary(folder)
    if row is None:
        raise NotFound(run_id)
    run = _read_json(folder / "run.json") or {}
    files = [n for n in ("RFQ.xlsx", "RFQ (2).xlsx", "reply.eml", "run.log", "error.txt") if (folder / n).exists()]
    return {"summary": row, "run": run, "files": files}


def events(run_id):
    path = run_dir(run_id) / "events.jsonl"
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def screenshot(product_id):
    if not product_id.replace("-", "").isalnum():
        raise NotFound(product_id)
    path = settings.CACHE / "pages" / f"{product_id}.png"
    if not path.exists():
        raise NotFound(product_id)
    return path


INBOX_STALE_SECONDS = 150  # the watchers check every 30-60 s; a build can take a while


def inbox_status():
    """Who watches the inbox (web app, mailbot.py or the Azure timer), when it last checked, any problem."""
    beat = _read_json(settings.mailbot.OUT / ".mailbot.json") or {}
    age = time.time() - float(beat.get("at", 0)) if beat else None
    return {"watching": age is not None and age < INBOX_STALE_SECONDS and not beat.get("error"),
            "by": beat.get("by", ""), "email": beat.get("email", ""), "error": beat.get("error", ""),
            "seconds_ago": round(age) if age is not None else None}


def inbox_watching():
    return inbox_status()["watching"]


def file_path(run_id, name):
    folder = run_dir(run_id)
    if name not in ("RFQ.xlsx", "RFQ (2).xlsx", "reply.eml", "run.log", "error.txt"):
        raise NotFound(name)
    path = folder / name
    if not path.exists():
        raise NotFound(name)
    return path

