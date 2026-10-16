"""Opens the Chrome window for live ferguson.com lookups (remote debugging on port 9333).

    python rfq/chrome.py [--port 9333] [--browser PATH]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(ROOT))

from rfq.infra.chrome import launch  # noqa: E402


def main():
    ap = argparse.ArgumentParser(prog="rfq/chrome.py", description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--browser", help="path to chrome / msedge / chromium (default: search)")
    args = ap.parse_args()
    ok, message = launch(args.port, args.browser)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
