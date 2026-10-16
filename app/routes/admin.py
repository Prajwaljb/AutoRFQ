"""Admin: the product database (list, search, seed from the catalog, clear for a simulation).

Writes need the ADMIN_TOKEN (header X-Admin-Token) when one is set, so a public link can't wipe the data.
"""
import os
import time

from fastapi import APIRouter, Header, HTTPException

from rfq.infra.productdb import ProductDB
from rfq.sources.catalog import CatalogSource

router = APIRouter(prefix="/api/admin")


def _guard(token):
    expected = os.environ.get("ADMIN_TOKEN", "").strip()
    if expected and token != expected:
        raise HTTPException(403, "This action needs the admin token (ADMIN_TOKEN).")


def _summary(record):
    extra = record.get("extra", {})
    return {
        "product_id": record["product_id"], "description": record["description"], "source": record["source"],
        "url": record["url"], "fetched_at": record["fetched_at"], "updated_at": record["updated_at"],
        "hits": record["hits"], "price": extra.get("Price (USD)", ""), "availability": extra.get("Availability", ""),
        "cells": len(record.get("cells", {})),
    }


@router.get("/products")
def products(q: str = "", limit: int = 200):
    db = ProductDB()
    return {"stats": {**db.stats(), "token_required": bool(os.environ.get("ADMIN_TOKEN", "").strip()),
                      "now": time.time()},
            "products": [_summary(r) for r in db.list(q.strip(), max(1, min(limit, 1000)))],
            "crossrefs": db.list_crossrefs()}


@router.get("/products/{product_id}")
def product(product_id: str):
    record = ProductDB().get(product_id)
    if not record:
        raise HTTPException(404, "Not in the product database.")
    return record


@router.post("/clear-db")
def clear_db(x_admin_token: str = Header(default="")):
    _guard(x_admin_token)
    return {"cleared": ProductDB().clear()}


@router.post("/seed")
def seed(x_admin_token: str = Header(default="")):
    _guard(x_admin_token)
    return {"added": ProductDB().seed_from_catalog(CatalogSource())}
