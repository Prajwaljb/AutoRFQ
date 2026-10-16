"""Azure Functions entry point: wraps the existing FastAPI app (app/main.py), nothing rewritten.

host.json sets routePrefix to "", so the dashboard is at /, the upload page at /rfq and the API at /api/...
Settings (RFQ_MODE=no-browser, RFQ_OUT_DIR=/tmp/autorfq, keys) come from the Function App's app settings.
"""
import os

os.environ.setdefault("RFQ_MODE", "no-browser")       # no Chrome in the cloud: catalog + spec sheets
os.environ.setdefault("RFQ_OUT_DIR", "/tmp/autorfq")  # only /tmp is writable
os.environ.setdefault("RFQ_AUTO_BROWSER", "0")
os.environ.setdefault("RFQ_PRODUCTS_DB", "/tmp/autorfq/products.db")

import azure.functions as func  # noqa: E402

from app.main import app as fastapi_app  # noqa: E402

app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
