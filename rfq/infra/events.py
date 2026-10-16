"""Pipeline progress events: an in-process callback and lines in out/<run>/events.jsonl.

Events: email_read, item_found, lookup_start, lookup_done, spec_pdf_read, quality_flag, excel_saved,
reply_saved, run_done. The web app's stepper is driven by them; they are never part of RFQ.xlsx.
"""
import json
import time


class Events:
    def __init__(self, path=None, callback=None):
        self.path = path
        self.callback = callback
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def emit(self, event_type, **data):
        event = {"type": event_type, "ts": round(time.time(), 3), **data}
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        if self.callback is not None:
            try:
                self.callback(event)
            except Exception:  # a broken listener must not break the run
                pass
