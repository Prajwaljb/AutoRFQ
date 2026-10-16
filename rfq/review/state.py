"""Human review of a held RFQ: review.json next to run.json.

Each decision is keep / edit / clear for one flag. Writes are atomic and versioned: a decision made on an
old version (another reviewer got there first) is rejected. finalise() applies the decisions, rebuilds
RFQ.xlsx and the reply without review marks, and sets the status to approved. Sending is separate
(app/services/mailer.py), so a failed send never loses the review.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from rfq.infra.io import write_text_atomic
from rfq.models import Cell, RunResult, RunStatus

ACTIONS = ("keep", "edit", "clear")
_lock = threading.Lock()


class ReviewError(Exception):
    """A decision that can't be applied (unknown flag, bad action, nothing to approve)."""


class Stale(ReviewError):
    """The review changed since the client loaded it: reload and try again."""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_run(run_dir):
    return json.loads((Path(run_dir) / "run.json").read_text(encoding="utf-8"))


def load(run_dir):
    path = Path(run_dir) / "review.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 0, "decisions": []}


def _save(run_dir, review):
    write_text_atomic(Path(run_dir) / "review.json", json.dumps(review, indent=2, ensure_ascii=False))


def latest(review):
    """flag id -> its latest decision."""
    out = {}
    for d in review["decisions"]:
        out[d["flag_id"]] = d
    return out


def view(run_dir):
    """The review as the UI needs it: flags with their decision, progress and whether approval is allowed."""
    run = load_run(run_dir)
    review = load(run_dir)
    decided = latest(review)
    flags = [dict(f, decision=decided.get(f["id"])) for f in run.get("flags", []) if f["severity"] != "info"]
    ai = [dict(f, decision=decided.get(f["id"])) for f in run.get("ai_suggestions", [])]
    high_open = [f for f in flags if f["severity"] == "high" and not f["decision"] and not f.get("resolved")]
    can_approve = run.get("status") in ("needs_review", "ready") and not high_open
    if run.get("status") not in ("needs_review", "ready"):
        reason = f"This RFQ is already {run.get('status')}."
    elif high_open:
        reason = f"Resolve {len(high_open)} high-severity flag{'s' if len(high_open) != 1 else ''} first."
    else:
        reason = ""
    return {"version": review["version"], "flags": flags, "ai_suggestions": ai,
            "resolved": sum(1 for f in flags if f["decision"] or f.get("resolved")), "total": len(flags),
            "can_approve": can_approve, "approve_blocked_reason": reason, "decisions": review["decisions"]}


def decide(run_dir, flag_id, action, reviewer, value=None, expected_version=None):
    if action not in ACTIONS:
        raise ReviewError(f"Unknown action {action!r}.")
    if not (reviewer or "").strip():
        raise ReviewError("A reviewer name is required.")
    with _lock:
        run = load_run(run_dir)
        flag = next((f for f in run.get("flags", []) + run.get("ai_suggestions", []) if f["id"] == flag_id), None)
        if flag is None:
            raise ReviewError(f"No flag {flag_id!r} on this RFQ.")
        if run.get("status") not in ("needs_review", "ready"):
            raise ReviewError(f"This RFQ is already {run.get('status')}.")
        if action == "edit" and not str(value or "").strip():
            raise ReviewError("An edit needs a value (use clear to leave the cell blank).")
        review = load(run_dir)
        if expected_version is not None and int(expected_version) != review["version"]:
            raise Stale("The review changed since you loaded it. Reload and try again.")
        review["decisions"].append({"flag_id": flag_id, "action": action,
                                    "value": str(value).strip() if action == "edit" else None,
                                    "reviewer": reviewer.strip(), "at": _now()})
        review["version"] += 1
        _save(run_dir, review)
        return review


def undo(run_dir, expected_version=None):
    with _lock:
        review = load(run_dir)
        if expected_version is not None and int(expected_version) != review["version"]:
            raise Stale("The review changed since you loaded it. Reload and try again.")
        if not review["decisions"]:
            raise ReviewError("Nothing to undo.")
        review["decisions"].pop()
        review["version"] += 1
        _save(run_dir, review)
        return review


def apply_decisions(result, review):
    """Applies keep / edit / clear to a RunResult. Edits are recorded as human_review Sources rows."""
    items = {i.product_id: i for i in result.items}
    for flag in result.flags + result.ai_suggestions:
        decision = latest(review).get(flag.id)
        if not decision:
            continue
        flag.resolved = True
        item = items.get(flag.product_id)
        if item is None or decision["action"] == "keep":
            if item is not None:
                result.add_note(item, "quality", f'{flag.column}: kept "{flag.value}" after review '
                                                 f'({decision["reviewer"]}).')
            continue
        old = item.cells.get(flag.column)
        if decision["action"] == "edit":
            item.cells[flag.column] = Cell(decision["value"], "human_review", "high",
                                           f'Reviewed by {decision["reviewer"]}, {decision["at"]}')
            result.add_note(item, "quality", f'{flag.column}: changed from "{old.value if old else ""}" to '
                                             f'"{decision["value"]}" by {decision["reviewer"]}.')
        else:  # clear: blank means unknown
            item.cells.pop(flag.column, None)
            if flag.column == "Image" or flag.column == "Picture":
                item.cells.pop("Image", None)
                item.cells.pop("Picture", None)
            result.add_note(item, "quality", f'{flag.column}: cleared by {decision["reviewer"]} '
                                             f'(unknown; was "{old.value if old else ""}").')
    return result


def finalise(run_dir, reviewer):
    """Applies the review and rebuilds the outputs without review marks. Returns the RunResult."""
    from rfq import pipeline  # late import: pipeline imports a lot
    with _lock:
        state = view(run_dir)
        if not state["can_approve"]:
            raise ReviewError(state["approve_blocked_reason"] or "This RFQ can't be approved.")
        result = RunResult.from_dict(load_run(run_dir))
        apply_decisions(result, load(run_dir))
        result.reviewed_by = (reviewer or "").strip() or "reviewer"
        result.reviewed_at = _now()
        result.status = RunStatus.APPROVED
        pipeline.write_outputs(result, run_dir)
        return result


def set_status(run_dir, status):
    with _lock:
        run = load_run(run_dir)
        run["status"] = status if isinstance(status, str) else status.value
        write_text_atomic(Path(run_dir) / "run.json", json.dumps(run, indent=2, ensure_ascii=False))


def substitute(run_dir, requested, alternative, reviewer):
    """Replaces a Not found item with a suggested (or any catalog) Ferguson item: a human decision.

    The row takes the Ferguson item's catalog values and sources; a Note records what was requested and
    who replaced it, and the reply asks the customer to confirm. Allowed before approval only.
    """
    from rfq import pipeline
    from rfq import quality as quality_agent
    from rfq.quality import rules, units
    from rfq.sources.catalog import CatalogSource
    if not (reviewer or "").strip():
        raise ReviewError("A reviewer name is required.")
    with _lock:
        run = load_run(run_dir)
        if run.get("status") not in ("ready", "needs_review"):
            raise ReviewError(f"This RFQ is already {run.get('status')}.")
        result = RunResult.from_dict(run)
        item = next((i for i in result.items if i.product_id == requested and not i.found), None)
        if item is None:
            raise ReviewError(f"No Not found item {requested!r} on this RFQ.")
        if any(i.product_id == alternative for i in result.items):
            raise ReviewError(f"{alternative} is already on this RFQ.")
        catalog = CatalogSource()
        cells = catalog.lookup(alternative)
        if not cells:
            raise ReviewError(f"{alternative} is not in the catalog.")
        item.product_id, item.kind, item.cells = alternative, "ferguson", cells
        item.extra = {**catalog.extra(alternative), "replaces": requested}
        item.lookup_status, item.found_via, item.reason = "Found", "catalog", ""
        result.add_note(item, "quality", f"Requested {requested}; replaced by Ferguson item {alternative} by "
                                         f"{reviewer.strip()} ({_now()}). The customer is asked to confirm.")
        if result.quality_ran:
            result.units_converted += units.normalise(item, result)
            keep = [f for f in result.flags if f.product_id != requested]
            result.flags = keep + [f for f in rules.check_item(item)]
            result.status = quality_agent.status_of(result)
        pipeline.write_outputs(result, run_dir)
        return result

