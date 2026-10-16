"""The data model shared by every stage, run.json and the web API."""
from dataclasses import asdict, dataclass, field
from enum import Enum

from rfq.config import FOUND, NOT_FOUND

FERGUSON, CODE = "ferguson", "code"  # Item.kind: a Ferguson product ID, or any other part code
# Note stages, in the order notes are sorted within one item.
STAGES = ("extract", "lookup", "spec", "quality", "output")


class RunStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    FALLBACK_SENT = "fallback_sent"


@dataclass
class Cell:
    """One filled value and where it came from."""
    value: str
    source_type: str
    confidence: str
    source: str


@dataclass
class Item:
    """One requested item, in email order."""
    index: int
    product_id: str
    kind: str = FERGUSON
    line: str = ""        # the email line or sheet row it was found on
    brand: str = ""       # brand named next to a competitor code
    qty: str = ""
    cells: dict = field(default_factory=dict)   # RFQ column -> Cell
    extra: dict = field(default_factory=dict)   # price, availability, URLs: for the reply and the web app
    lookup_status: str = NOT_FOUND
    found_via: str = ""   # live / spec / catalog
    reason: str = ""      # why it is Not found, in buyer words

    @property
    def found(self):
        return self.lookup_status == FOUND


@dataclass
class Note:
    product_id: str
    stage: str
    text: str
    item_index: int = -1  # -1: about the whole email


@dataclass
class Flag:
    """A quality finding. Rule flags decide the status; AI flags are advisory only."""
    id: str
    product_id: str
    column: str
    value: str
    issue: str
    rule: str
    severity: str  # high / medium / low
    origin: str = "rule"  # rule / ai
    resolved: bool = False


@dataclass
class RunResult:
    run_id: str
    email_file: str
    mode: str
    sender: str = ""
    sender_name: str = ""
    subject: str = ""
    message_id: str = ""
    received: str = ""
    items: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    ai_suggestions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    status: RunStatus = RunStatus.PROCESSING
    quality_ran: bool = False
    units_converted: int = 0
    xlsx_name: str = "RFQ.xlsx"

    def add_note(self, item, stage, text):
        """Adds a Notes row. item is an Item, or None for the whole email."""
        if item is None:
            self.notes.append(Note("", stage, text))
        else:
            self.notes.append(Note(item.product_id, stage, text, item.index))

    def sorted_notes(self):
        """Notes in email order, then by stage: never in the order lookups finished."""
        def key(note):
            return (note.item_index, STAGES.index(note.stage) if note.stage in STAGES else len(STAGES))
        return sorted(self.notes, key=key)  # sort is stable: same-key notes keep their order

    def counts(self):
        found = [i for i in self.items if i.found]
        by_source = {"live": 0, "spec": 0, "catalog": 0}
        for item in found:
            if item.found_via in by_source:
                by_source[item.found_via] += 1
        return {
            "items": len(self.items),
            "found": len(found),
            "not_found": len(self.items) - len(found),
            "by_source": by_source,
            "flags": len([f for f in self.flags if not f.resolved]),
            "warnings": len(self.warnings),
        }

    def to_dict(self):
        """What goes into run.json (no timings)."""
        return {
            "run_id": self.run_id,
            "email_file": self.email_file,
            "mode": self.mode,
            "sender": self.sender,
            "sender_name": self.sender_name,
            "subject": self.subject,
            "message_id": self.message_id,
            "received": self.received,
            "status": self.status.value,
            "counts": self.counts(),
            "quality_ran": self.quality_ran,
            "units_converted": self.units_converted,
            "xlsx": self.xlsx_name,
            "items": [
                {
                    "index": i.index, "product_id": i.product_id, "kind": i.kind, "brand": i.brand,
                    "qty": i.qty, "line": i.line, "lookup_status": i.lookup_status,
                    "found_via": i.found_via, "reason": i.reason,
                    "description": i.cells["Description"].value if "Description" in i.cells else "",
                    "cells": {c: asdict(cell) for c, cell in i.cells.items()},
                    "extra": i.extra,
                }
                for i in self.items
            ],
            "notes": [asdict(n) for n in self.sorted_notes()],
            "flags": [asdict(f) for f in self.flags],
            "ai_suggestions": [asdict(f) for f in self.ai_suggestions],
            "warnings": list(self.warnings),
        }
