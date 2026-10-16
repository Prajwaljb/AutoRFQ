"""Azure Functions entry point: wraps the existing FastAPI app (app/main.py), nothing rewritten.

host.json sets routePrefix to "", so the dashboard is at /, the upload page at /rfq and the API at /api/...
The inbox_timer function answers RFQ emails every minute (the Inbox row on Diagnostics).
Settings (RFQ_MODE=no-browser, RFQ_OUT_DIR=/tmp/autorfq, keys) come from the Function App's app settings.
"""
import os

os.environ.setdefault("RFQ_MODE", "no-browser")       # no Chrome in the cloud: catalog + spec sheets
os.environ.setdefault("RFQ_OUT_DIR", "/tmp/autorfq")  # only /tmp is writable
os.environ.setdefault("RFQ_AUTO_BROWSER", "0")
os.environ.setdefault("RFQ_PRODUCTS_DB", "/tmp/autorfq/db/products.db")

import azure.functions as func  # noqa: E402

from app.main import app as fastapi_app  # noqa: E402

app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)


@app.timer_trigger(schedule="0 */1 * * * *", arg_name="timer", run_on_startup=False, use_monitor=False)
def inbox_timer(timer: func.TimerRequest) -> None:
    """Answers RFQ emails every minute (a web app thread can't live on a consumption plan between requests).
    RFQ_INBOX_WATCH=0 turns it off, e.g. when another deployment watches the same inbox."""
    from app import settings
    settings.refresh()
    if os.environ.get("RFQ_INBOX_WATCH", "1").strip() != "0" and settings.mail_configured():
        settings.mailbot.check_once(by="azure timer")
