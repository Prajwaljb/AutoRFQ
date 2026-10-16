"""Settings for the web app, from the environment (.env locally, App Settings on Azure)."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mailbot  # noqa: E402  (loads .env into the environment, and is reused to send replies)

from rfq import config  # noqa: E402

OUT = Path(os.environ.get("RFQ_OUT_DIR", "").strip() or ROOT / "out").resolve()
UPLOADS = OUT / "uploads"
INBOX = OUT / "inbox"
CACHE = OUT / ".cache"
WEB_DIST = ROOT / "web" / "dist"
CDP = os.environ.get("RFQ_CDP", "").strip() or config.DEFAULT_CDP
FORCED_MODE = os.environ.get("RFQ_MODE", "").strip().lower()  # "no-browser" on Azure
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
BUILD_TIMEOUT = 900
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ ()-]{0,120}$")
NOT_RUNS = {"inbox", "uploads", "verify", "selfcheck"}


API_VERSION = 3  # the web UI warns when the server it talks to is older than itself


def refresh():
    """Picks up .env edits (no restart needed) and hands the mail settings to mailbot."""
    from rfq.infra import env
    env.reload()
    mailbot.BOT_EMAIL = os.environ.get("BOT_EMAIL", "").strip()
    mailbot.BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "").replace(" ", "")
    mailbot.REVIEW_NOTIFY_EMAIL = os.environ.get("REVIEW_NOTIFY_EMAIL", "").strip()
    mailbot.DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip()


def mail_configured():
    return bool(mailbot.BOT_EMAIL and mailbot.BOT_PASSWORD)


def default_mode():
    return FORCED_MODE if FORCED_MODE in config.MODES else config.LIVE
