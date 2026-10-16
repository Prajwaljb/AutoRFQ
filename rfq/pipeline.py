"""run(): one email in, RFQ.xlsx + reply.eml + run.json out. The stage order is fixed:

read -> extract -> look up -> fill -> quality -> save -> reply
"""
import json
import time
from pathlib import Path

from rfq import config
from rfq.extract import extract_items, read_email
from rfq.infra import chrome as chrome_launcher
from rfq.infra import log as runlog
from rfq.infra.events import Events
from rfq.infra.io import safe_folder_name, write_bytes_atomic, write_text_atomic
from rfq.models import CODE, RunResult, RunStatus
from rfq.output import reply as reply_out
from rfq.output import style, workbook
from rfq import quality as quality_agent
from rfq.quality import summary
from rfq.sources import merge
from rfq.sources.alternatives import Alternatives
from rfq.sources.base import SourceUnavailable
from rfq.sources.catalog import CatalogSource
from rfq.sources.ferguson_live import LiveSource, chrome_available
from rfq.sources.spec_sheet import SpecSheetSource


def lookup_order(items):
    """The order lookups run in. Results are always written in email order whatever this returns
    (tests shuffle it to prove that)."""
    return list(items)


def _not_found_reason(item, mode, catalog):
    if item.kind == CODE:
        who = f"a {item.brand} part number" if item.brand else "not a Ferguson item number"
        return f"This is {who}; we only quote Ferguson item numbers."
    where = "on ferguson.com or in our catalog" if mode == config.LIVE else "in our catalog"
    reason = f"We could not find item {item.product_id} {where}."
    near = catalog.nearest_ids(item.product_id)
    if near:
        options = near[0] if len(near) == 1 else f"{', '.join(near[:-1])} or {near[-1]}"
        reason += f" Did you mean {options}?"
    return reason


def suggest_alternatives(result, catalog, mode, logger=None, events=None):
    """Closest Ferguson products for every Not found item. Suggestions only: the RFQ row stays Not found."""
    finder = Alternatives(catalog, web=mode != config.OFFLINE, logger=logger)
    for item in result.items:
        if item.found:
            continue
        text, origin, options = finder.suggest(item)
        if text:
            item.extra["described_as"], item.extra["described_from"] = text, origin
        if origin.startswith("Ferguson's earlier listing"):
            item.reason = f"Item {item.product_id} ({text}) is no longer listed by Ferguson."
            result.add_note(item, "lookup", f"Ferguson listed this item earlier as \"{text}\"; it is no longer listed.")
        elif item.kind == CODE and not text:
            item.reason += " The request gives no size or colour for it."
        if not options:
            continue
        item.extra["alternatives"] = options
        listed = "; ".join(f"{o['product_id']} ({o['description']}; matches {', '.join(o['matched'])})"
                           for o in options)
        result.add_note(item, "lookup", f"Possible Ferguson alternatives, not added to the RFQ: {listed}.")
        if events is not None:
            events.emit("alternatives", product_id=item.product_id, options=[o["product_id"] for o in options])


def _warn(result, logger, text):
    result.warnings.append(text)
    result.add_note(None, "lookup", text)
    logger.warning(text)


def _live_lookups(result, live, catalog, logger, events):
    """{item index: (cells, extra)} from ferguson.com, within the time budget. Notes every fallback."""
    found = {}
    started = time.monotonic()
    blocks_in_a_row = 0
    stopped = ""
    for item in lookup_order(result.items):
        if item.kind == CODE:
            continue
        if not stopped and time.monotonic() - started > config.LIVE_BUDGET_SECONDS:
            stopped = "the live lookup time budget (8 minutes) was used up"
        if stopped:
            result.add_note(item, "lookup", f"Not read from ferguson.com: {stopped}; used the catalog.")
            continue
        url = catalog.extra(item.product_id).get("Ferguson URL")
        events.emit("lookup_start", product_id=item.product_id, source="live")
        try:
            cells = live.lookup(item.product_id, url)
            blocks_in_a_row = 0
        except SourceUnavailable as e:
            reason = str(e)
            result.add_note(item, "lookup", f"ferguson.com page not read ({reason}); used the catalog.")
            logger.warning("%s: live lookup failed: %s", item.product_id, reason)
            events.emit("lookup_done", product_id=item.product_id, source="live", found=False, error=reason)
            if "closed" in reason or "not attached" in reason or "not installed" in reason:
                stopped = "the Chrome window is no longer available"
                _warn(result, logger, f"Live lookup stopped: {stopped}; the rest used the catalog.")
            else:
                blocks_in_a_row += 1
                if blocks_in_a_row >= 3:
                    stopped = "ferguson.com blocked 3 pages in a row"
                    _warn(result, logger, f"Live lookup stopped: {stopped}; the rest used the catalog.")
            continue
        if cells:
            found[item.index] = (cells, dict(live.last_extra))
        else:
            result.add_note(item, "lookup", "Not found on ferguson.com.")
        events.emit("lookup_done", product_id=item.product_id, source="live", found=bool(cells),
                    screenshot=live.last_screenshot)
    return found


def _lookup(result, mode, catalog, logger, events, cdp, cache_dir, replay, keep_browser=False):
    live_results = {}
    wants_live = mode == config.LIVE and any(i.kind != CODE for i in result.items)
    if mode == config.LIVE and not wants_live:
        pass  # nothing to look up: don't open a browser
    elif mode == config.LIVE:
        if not replay and not chrome_available(cdp) and config.AUTO_BROWSER:
            ok, message = chrome_launcher.launch(chrome_launcher.port_of(cdp))
            logger.info("chrome: %s", message)
        if not replay and not chrome_available(cdp):
            _warn(result, logger, f"Chrome is not open for scraping at {cdp}; used the catalog and spec "
                                  "sheets (start it with: python rfq/chrome.py).")
            mode = result.mode = config.NO_BROWSER
        else:
            live = LiveSource(cdp, cache_dir, replay=replay)
            try:
                live.open()
                live_results = _live_lookups(result, live, catalog, logger, events)
            except SourceUnavailable as e:
                _warn(result, logger, f"Live lookup not available ({e}); used the catalog and spec sheets.")
            finally:
                live.close()
                if not replay and not keep_browser:  # the work is done: close the scraping window
                    closed = chrome_launcher.close_browser(cdp)
                    logger.info("chrome closed: %s", closed)

    spec = SpecSheetSource(cache_dir / "spec", replay=replay) if mode != config.OFFLINE else None
    for item in result.items:  # always assembled in email order
        if item.kind == CODE:
            item.lookup_status = config.NOT_FOUND
            item.reason = _not_found_reason(item, mode, catalog)
            continue
        cat_cells = catalog.lookup(item.product_id)
        if item.index in live_results:
            live_cells, live_extra = live_results[item.index]
            item.cells = merge.live_over_catalog(item, live_cells, cat_cells, result)
            item.extra = {**catalog.extra(item.product_id), **live_extra}
            item.found_via = "live"
        elif cat_cells:
            item.cells, item.extra, item.found_via = cat_cells, catalog.extra(item.product_id), "catalog"
            if mode == config.OFFLINE:
                events.emit("lookup_done", product_id=item.product_id, source="catalog", found=True)
        if not item.cells:
            item.lookup_status = config.NOT_FOUND
            item.reason = _not_found_reason(item, mode, catalog)
            result.add_note(item, "lookup", item.reason)
            continue
        item.lookup_status = config.FOUND
        if spec is not None and spec.url(item.product_id):
            spec_cells = spec.lookup(item.product_id)
            if spec_cells:
                filled = merge.fill_from_spec(item, spec_cells, result)
                if spec.last_origin == "bundled":
                    result.add_note(item, "spec", f"Spec sheet read from the bundled copy "
                                                  f"({spec.download_problem}).")
                events.emit("spec_pdf_read", product_id=item.product_id, filled=filled, origin=spec.last_origin)
            elif spec.last_problem:
                result.add_note(item, "spec", f"Spec sheet skipped: {spec.last_problem}.")


def render_workbook(result):
    """RFQ / Sources / Notes (+ Summary when the quality agent ran), styled."""
    wb = workbook.build(result)
    if result.quality_ran:
        summary.add_sheet(wb, result)
    return style.apply(wb, result)


def write_outputs(result, run_dir, logger=None, events=None):
    """RFQ.xlsx, reply.eml and run.json for a result (also used to rebuild after a review)."""
    events = events or Events()
    xlsx = workbook.save(render_workbook(result), Path(run_dir) / "RFQ.xlsx")
    result.xlsx_name = xlsx.name
    if xlsx.name != "RFQ.xlsx":
        text = f"RFQ.xlsx was open in another program; saved as {xlsx.name}. Close RFQ.xlsx in Excel."
        if text not in result.warnings:
            result.warnings.append(text)
        if logger:
            logger.warning(text)
    events.emit("excel_saved", file=xlsx.name)
    write_bytes_atomic(Path(run_dir) / "reply.eml", reply_out.build(result, xlsx).as_bytes())
    events.emit("reply_saved", file="reply.eml")
    write_text_atomic(Path(run_dir) / "run.json", json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return xlsx


def run(eml_path, out_root, mode=config.OFFLINE, quality=True, on_event=None, cdp=config.DEFAULT_CDP,
        replay=False, keep_browser=False):
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
                           received=data.date, email_path=str(eml_path.resolve()))
        logger.info("run %s mode=%s", run_id, mode)
        events.emit("email_read", subject=result.subject, sender=result.sender, texts=len(data.texts),
                    attachments=len(data.attachments))

        extract_items(data, result)
        for item in result.items:
            events.emit("item_found", product_id=item.product_id, kind=item.kind, index=item.index)
        logger.info("items: %d", len(result.items))

        _lookup(result, mode, catalog, logger, events, cdp, Path(out_root) / ".cache", replay, keep_browser)
        suggest_alternatives(result, catalog, config.OFFLINE if replay else result.mode, logger, events)

        if quality:
            quality_agent.run(result, logger, events)
        else:
            result.status = RunStatus.READY
        logger.info("status %s, flags %d, AI: %s", result.status.value, len(result.flags), result.ai_status)
        write_outputs(result, run_dir, logger, events)
        for w in result.warnings:
            logger.info("warning recorded: %s", w)
        events.emit("run_done", status=result.status.value, counts=result.counts())
        return result, run_dir
    finally:
        runlog.close(logger)
