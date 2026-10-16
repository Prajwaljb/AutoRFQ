"""One-off: downloads the spec sheet PDFs in data/spec_sheet_links.csv into data/spec_cache/.

The flow falls back to these bundled copies when a download fails, so --no-browser runs are repeatable.
Identical PDFs (one family sheet for many products) are stored once; index.json maps product_id -> file.

    python scripts/fetch_specs.py [--force]
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rfq import config  # noqa: E402
from rfq.sources.spec_sheet import download_pdf  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="download again even if a copy exists")
    args = ap.parse_args()
    cache = config.SPEC_CACHE
    cache.mkdir(parents=True, exist_ok=True)
    index_path = cache / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    with config.SPEC_LINKS.open(encoding="utf-8-sig", newline="") as f:
        links = list(csv.DictReader(f))
    failed = []
    for row in links:
        pid, url = row["product_id"], row["spec_sheet_url"]
        if pid in index and (cache / index[pid]).exists() and not args.force:
            continue
        try:
            data = download_pdf(url)
        except Exception as e:
            failed.append(pid)
            print(f"{pid}: failed ({e})")
            continue
        name = hashlib.sha1(data).hexdigest()[:16] + ".pdf"
        (cache / name).write_bytes(data)
        index[pid] = name
        print(f"{pid}: {name} ({len(data) // 1024} KB)")
    index_path.write_text(json.dumps(dict(sorted(index.items())), indent=1) + "\n", encoding="utf-8")
    print(f"{len(index)} products, {len(set(index.values()))} files, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
