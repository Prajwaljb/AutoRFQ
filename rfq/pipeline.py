"""run(): one email in, RFQ.xlsx + reply.eml + run.json out. The stage order is fixed:

read -> extract -> look up -> fill -> quality -> save -> reply
"""
import json
from pathlib import Path

from rfq import config
from rfq.extract import extract_items, read_email
from rfq.infra import log as runlog
from rfq.infra.events import Events
from rfq.infra.io import safe_folder_name, write_bytes_atomic, write_text_atomic
from rfq.models import CODE, RunResult, RunStatus
from rfq.output import reply as reply_out
from rfq.output import workbook
from rfq.sources.catalog import CatalogSource


def lookup_order(items):
    """The order lookups run in. Results are always written in email order whatever this returns
    (tests shuffle it to prove that)."""
    return list(items)


def _not_found_reason(item, mode, catalog):
    if item.kind == CODE:
        who = f"a {item.brand} part number" if item.brand else "not a Ferguson item number"
        return f"This is {who}; we only quote Ferguson item numbers."
    where = "in our catalog" if mode == config.OFFLINE else "on ferguson.com or in our catalog"
    reason = f"We could not find item {item.product_id} {where}."
    near = catalog.nearest_ids(item.product_id)
    if near:
        options = near[0] if len(near) == 1 else f"{', '.join(near[:-1])} or {near[-1]}"
        reason += f" Did you mean {options}?"
    return reason


def _lookup(result, mode, catalog, logger, events):
    if mode != config.OFFLINE:
        text = "Live ferguson.com lookup and spec sheets are not available in this build; used the catalog."
        result.warnings.append(text)
        result.add_note(None, "lookup", text)
        logger.warning(text)
    looked_up = {}
    for item in lookup_order(result.items):
        if item.kind == CODE:
            continue
        events.emit("lookup_start", product_id=item.product_id, source="catalog")
        looked_up[item.index] = (catalog.lookup(item.product_id), catalog.extra(item.product_id))
        events.emit("lookup_done", product_id=item.product_id, source="catalog",
                    found=bool(looked_up[item.index][0]))
    for item in result.items:  # always assembled in email order
        cells, extra = looked_up.get(item.index, ({}, {}))
        if cells:
            item.cells, item.extra = cells, extra
            item.lookup_status, item.found_via = config.FOUND, "catalog"
        else:
            item.lookup_status = config.NOT_FOUND
            item.reason = _not_found_reason(item, mode, catalog)
            if item.kind != CODE:
                result.add_note(item, "lookup", item.reason)


def run(eml_path, out_root, mode=config.OFFLINE, quality=True, on_event=None, cdp=config.DEFAULT_CDP,
        replay=False):
    """Builds the RFQ for one email. Returns (RunResult, run folder).

    Raises KitBroken if the template or catalog is unusable, OSError if the email can't be read.
    """
    eml_path = Path(eml_path)
    run_id = safe_folder_name(eml_path.stem)
    run_dir = Path(out_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = runlog.setup(run_dir)
    events = Events(run_dir / "events.jsonl", on_event)
    try:
        workbook.load_template()  # fail fast, naming the file, before any work
        catalog = CatalogSource()

        data = read_email(eml_path)
        result = RunResult(run_id=run_id, email_file=eml_path.name, mode=mode, sender=data.sender,
                           sender_name=data.sender_name, subject=data.subject, message_id=data.message_id,
                           received=data.date)
        logger.info("run %s mode=%s", run_id, mode)
        events.emit("email_read", subject=result.subject, sender=result.sender, texts=len(data.texts),
                    attachments=len(data.attachments))

        extract_items(data, result)
        for item in result.items:
            events.emit("item_found", product_id=item.product_id, kind=item.kind, index=item.index)
        logger.info("items: %d", len(result.items))

        _lookup(result, mode, catalog, logger, events)

        result.status = RunStatus.READY
        wb = workbook.build(result)
        xlsx = workbook.save(wb, run_dir / "RFQ.xlsx")
        result.xlsx_name = xlsx.name
        if xlsx.name != "RFQ.xlsx":
            text = f"RFQ.xlsx was open in another program; saved as {xlsx.name}. Close RFQ.xlsx in Excel."
            result.warnings.append(text)
            logger.warning(text)
        events.emit("excel_saved", file=xlsx.name)

        msg = reply_out.build(result, xlsx, data.raw)
        write_bytes_atomic(run_dir / "reply.eml", msg.as_bytes())
        events.emit("reply_saved", file="reply.eml")

        write_text_atomic(run_dir / "run.json", json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        for w in result.warnings:
            logger.info("warning recorded: %s", w)
        events.emit("run_done", status=result.status.value, counts=result.counts())
        return result, run_dir
    finally:
        runlog.close(logger)
