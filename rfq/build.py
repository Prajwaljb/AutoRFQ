"""Builds the RFQ for one request email.

    python rfq/build.py <email.eml> --out out [--offline | --no-browser] [--no-quality] [--cdp URL]
                        [--replay] [--keep-browser]

Live mode (the default) opens the scraping Chrome window if it isn't running, and closes it when the run
is done unless --keep-browser is given.

Writes out/<email name>/RFQ.xlsx, reply.eml, run.json and run.log, and prints one summary line.
Exit code: 0 when RFQ.xlsx and reply.eml were written (even with warnings), 2 for a usage error,
1 only when the kit itself is broken (template or catalog missing) and nothing could be written.
"""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Run as a script: import the package from the repo root, not from rfq/ itself.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(ROOT))

from rfq import config  # noqa: E402
from rfq.infra.io import safe_folder_name, write_bytes_atomic, write_text_atomic  # noqa: E402
from rfq.models import RunResult, RunStatus  # noqa: E402
from rfq.sources.catalog import KitBroken  # noqa: E402


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="rfq/build.py", description="Build the RFQ for one request email.")
    ap.add_argument("eml", help="the request email (.eml)")
    ap.add_argument("--out", default="out", help="output folder (default: out)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="catalog only, no network")
    mode.add_argument("--no-browser", action="store_true", help="catalog + spec sheet PDFs, no Chrome")
    ap.add_argument("--no-quality", action="store_true", help="skip the quality agent")
    ap.add_argument("--cdp", default=config.DEFAULT_CDP, help="Chrome DevTools address")
    ap.add_argument("--replay", action="store_true", help="use cached pages and PDFs from out/.cache")
    ap.add_argument("--keep-browser", action="store_true",
                    help="leave the scraping Chrome window open after the run (default: close it)")
    return ap.parse_args(argv)


def choose_mode(args):
    if args.offline:
        return config.OFFLINE
    if args.no_browser:
        return config.NO_BROWSER
    forced = os.environ.get("RFQ_MODE", "").strip().lower()  # Azure sets RFQ_MODE=no-browser
    return forced if forced in config.MODES else config.LIVE


def summary_line(result, path):
    c = result.counts()
    s = c["by_source"]
    return (f"{result.run_id}: {c['items']} items, {c['found']} found (live page {s['live']}, "
            f"spec sheet {s['spec']}, catalog {s['catalog']}), {c['not_found']} not found, "
            f"status {result.status.value}, flags {c['flags']}, warnings: {c['warnings']} -> {path}")


def last_resort(eml, out_root, error):
    """After an unexpected error: error.txt, plus a minimal RFQ and a follow-up reply if possible.

    Returns True if RFQ.xlsx and reply.eml were written.
    """
    run_dir = Path(out_root) / safe_folder_name(eml.stem)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_text_atomic(run_dir / "error.txt", "".join(traceback.format_exception(error)))
    try:
        from rfq.extract import extract_items, read_email
        from rfq.output import reply as reply_out
        from rfq.output import workbook

        result = RunResult(run_id=run_dir.name, email_file=eml.name, mode="fallback")
        try:
            data = read_email(eml)
            result.sender, result.sender_name = data.sender, data.sender_name
            result.subject, result.message_id = data.subject, data.message_id
            extract_items(data, result)
        except Exception:
            pass
        for item in result.items:
            item.lookup_status = config.NOT_FOUND
        result.add_note(None, "output", "Processing error: this RFQ could not be completed automatically.")
        result.status = RunStatus.FAILED
        xlsx = workbook.save(workbook.build(result), run_dir / "RFQ.xlsx")
        result.xlsx_name = xlsx.name
        msg = reply_out.fallback(result)
        msg.add_attachment(xlsx.read_bytes(), maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           filename="RFQ.xlsx")
        write_bytes_atomic(run_dir / "reply.eml", msg.as_bytes())
        write_text_atomic(run_dir / "run.json", json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return True
    except Exception:
        return False


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    args = parse_args(sys.argv[1:] if argv is None else argv)
    eml = Path(args.eml)
    if not eml.is_file():
        print(f"error: email file not found or not a file: {eml}", file=sys.stderr)
        return 2
    try:
        with eml.open("rb"):
            pass
    except OSError as e:
        print(f"error: can't read {eml}: {e.strerror}", file=sys.stderr)
        return 2

    from rfq import pipeline

    out_root = Path(args.out)
    try:
        result, run_dir = pipeline.run(eml, out_root, mode=choose_mode(args), quality=not args.no_quality,
                                       cdp=args.cdp, replay=args.replay, keep_browser=args.keep_browser)
    except KitBroken as e:
        print(f"error: the kit is broken: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        if e.filename and str(out_root) in str(e.filename):
            print(f"error: can't write to {e.filename}: {e.strerror}", file=sys.stderr)
            return 1
        return 0 if last_resort(eml, out_root, e) else 1
    except Exception as e:  # anything unexpected: the sender still gets a reply
        print(f"error: unexpected {type(e).__name__}; see error.txt in the output folder", file=sys.stderr)
        return 0 if last_resort(eml, out_root, e) else 1
    print(summary_line(result, run_dir / result.xlsx_name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
