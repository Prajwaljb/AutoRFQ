"""A bad input makes the RFQ smaller, never the run fail (spec.md: Failure handling, exit codes)."""
import email
import email.policy
import json
import os

import openpyxl
import pytest

from conftest import ROOT, make_email, run_build, sheet_rows

import rfq.infra.io as rio
import rfq.pipeline as pipeline


def built(out, eml):
    folder = out / eml.stem
    assert (folder / "RFQ.xlsx").exists() and (folder / "reply.eml").exists()
    return folder


def notes_of(folder):
    return [r[1] for r in sheet_rows(folder / "RFQ.xlsx", "Notes")]


def test_no_items(tmp_path):
    eml = make_email(tmp_path / "empty.eml", body="Hi, please quote the usual tapes. Thanks")
    proc = run_build(eml, tmp_path / "out", "--offline")
    assert proc.returncode == 0, proc.stderr
    folder = built(tmp_path / "out", eml)
    assert "No item numbers were found in the request." in notes_of(folder)
    assert "could not find any item numbers" in (folder / "reply.eml").read_text(encoding="utf-8")
    assert json.loads((folder / "run.json").read_text(encoding="utf-8"))["status"] == "ready"


def test_html_only(tmp_path):
    eml = make_email(tmp_path / "html.eml", html="<html><body><p>5106912</p><p>5106935</p></body></html>")
    assert run_build(eml, tmp_path / "out", "--offline").returncode == 0
    assert [r[0] for r in sheet_rows(built(tmp_path / "out", eml) / "RFQ.xlsx", "RFQ")] == ["5106912", "5106935"]


def test_bad_charset(tmp_path):
    raw = (b"From: Buyer <buyer@example.com>\r\nSubject: RFQ\r\nMIME-Version: 1.0\r\n"
           b"Content-Type: text/plain; charset=x-made-up\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
           b"Items \xff\xfe: 5106912\r\n")
    eml = make_email(tmp_path / "charset.eml", raw_body=raw)
    assert run_build(eml, tmp_path / "out", "--offline").returncode == 0
    assert [r[0] for r in sheet_rows(built(tmp_path / "out", eml) / "RFQ.xlsx", "RFQ")] == ["5106912"]


def test_phone_and_pin_next_to_ids(tmp_path):
    eml = make_email(tmp_path / "phone.eml", body="Call +91 20 4110012 (tel 5106913), pin 411001.\n5106912\n")
    assert run_build(eml, tmp_path / "out", "--offline").returncode == 0
    assert [r[0] for r in sheet_rows(built(tmp_path / "out", eml) / "RFQ.xlsx", "RFQ")] == ["5106912"]


@pytest.mark.parametrize("name,data,subtype", [
    ("broken.xlsx", b"not a zip file", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("old.xls", b"\xd0\xcf\x11\xe0 old excel", "vnd.ms-excel"),
])
def test_unreadable_attachment(tmp_path, name, data, subtype):
    eml = make_email(tmp_path / "att.eml", body="List attached, plus 5106912",
                     attachments=[(name, data, "application", subtype)])
    proc = run_build(eml, tmp_path / "out", "--offline")
    assert proc.returncode == 0, proc.stderr
    folder = built(tmp_path / "out", eml)
    assert any(name in n and "resend" in n for n in notes_of(folder))


def test_csv_attachment(tmp_path):
    eml = make_email(tmp_path / "csv.eml", body="See the csv",
                     attachments=[("items.csv", b"Item,Qty\n5106912,3\n1376044.0,2\n", "text", "csv")])
    assert run_build(eml, tmp_path / "out", "--offline").returncode == 0
    assert [r[0] for r in sheet_rows(built(tmp_path / "out", eml) / "RFQ.xlsx", "RFQ")] == ["5106912", "1376044"]


def test_formula_like_text_stays_text(tmp_path, monkeypatch):
    from rfq.sources.catalog import CatalogSource
    original = CatalogSource.lookup

    def poisoned(self, product_id):
        cells = original(self, product_id)
        cells["Lettering"].value = '=HYPERLINK("http://evil.example","click")'
        return cells
    monkeypatch.setattr(CatalogSource, "lookup", poisoned)
    eml = make_email(tmp_path / "f.eml", body="5106912")
    pipeline.run(eml, tmp_path / "out", mode="offline")
    ws = openpyxl.load_workbook(tmp_path / "out" / "f" / "RFQ.xlsx")["RFQ"]
    cell = ws.cell(row=2, column=7)
    assert cell.value.startswith("=HYPERLINK") and cell.data_type == "s"


def test_missing_template_exits_1(tmp_path):
    env = dict(os.environ, RFQ_TEMPLATE=str(tmp_path / "nope.xlsx"))
    proc = run_build(ROOT / "emails" / "email-1-ids-in-body.eml", tmp_path / "out", "--offline", env=env)
    assert proc.returncode == 1 and "nope.xlsx" in proc.stderr


def test_missing_email_exits_2(tmp_path):
    proc = run_build(tmp_path / "missing.eml", tmp_path / "out", "--offline")
    assert proc.returncode == 2


def test_locked_rfq_saves_a_copy(tmp_path, monkeypatch):
    real_replace = os.replace

    def locked(src, dst):
        if str(dst).endswith("RFQ.xlsx"):
            raise PermissionError("locked by Excel")
        return real_replace(src, dst)
    monkeypatch.setattr(rio.os, "replace", locked)
    monkeypatch.setattr(rio.time, "sleep", lambda s: None)
    result, folder = pipeline.run(ROOT / "emails" / "email-1-ids-in-body.eml", tmp_path, mode="offline")
    assert result.xlsx_name == "RFQ (2).xlsx" and (folder / "RFQ (2).xlsx").exists()
    assert any("Close RFQ.xlsx" in w for w in result.warnings)


def test_unexpected_error_still_replies(tmp_path, monkeypatch):
    """The last-resort guard: error.txt, a minimal RFQ and a follow-up reply, exit 0."""
    import rfq.build as build

    def boom(*a, **k):
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(pipeline, "run", boom)
    code = build.main([str(ROOT / "emails" / "email-1-ids-in-body.eml"), "--out", str(tmp_path), "--offline"])
    folder = tmp_path / "email-1-ids-in-body"
    assert code == 0
    assert "simulated crash" in (folder / "error.txt").read_text(encoding="utf-8")
    msg = email.message_from_bytes((folder / "reply.eml").read_bytes(), policy=email.policy.default)
    assert "a person from our team will follow up" in msg.get_body(("plain",)).get_content()
    assert [p.get_filename() for p in msg.iter_attachments()] == ["RFQ.xlsx"]
    rows = sheet_rows(folder / "RFQ.xlsx", "RFQ")
    assert len(rows) == 6 and all(r[-1] == "Not found" for r in rows)


def test_chrome_closed_falls_back_with_one_warning(tmp_path):
    """Default (live) mode with nothing listening: catalog + spec sheets, one warning, exit 0."""
    proc = run_build(ROOT / "emails" / "email-1-ids-in-body.eml", tmp_path, "--cdp", "http://127.0.0.1:9")
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.count("Chrome is not open") == 1
    run = json.loads((tmp_path / "email-1-ids-in-body" / "run.json").read_text(encoding="utf-8"))
    assert run["mode"] == "no-browser" and run["counts"]["found"] == 6
    assert sheet_rows(tmp_path / "email-1-ids-in-body" / "RFQ.xlsx", "RFQ") == \
        sheet_rows(ROOT / "reference" / "email-1 reference output.xlsx", "RFQ")


def test_no_browser_mode_still_finishes(tmp_path):
    proc = run_build(ROOT / "emails" / "email-1-ids-in-body.eml", tmp_path, "--no-browser")
    assert proc.returncode == 0, proc.stderr
    assert len(sheet_rows(tmp_path / "email-1-ids-in-body" / "RFQ.xlsx", "RFQ")) == 6


def test_second_live_run_reuses_the_product_database(tmp_path, monkeypatch):
    """All items fetched live recently: the live run needs no Chrome at all."""
    from rfq.infra.productdb import ProductDB
    from rfq.sources.catalog import CatalogSource
    db_path = tmp_path / "products.db"
    monkeypatch.setenv("RFQ_PRODUCTS_DB", str(db_path))
    db, catalog = ProductDB(db_path), CatalogSource()
    for pid in ("5106912", "5106935", "5106914", "5106966", "5106891", "5106880"):
        cells = {c: type(v)(v.value, "ferguson_page", "high", "https://www.ferguson.com/x (read today)")
                 for c, v in catalog.lookup(pid).items()}
        db.upsert(pid, cells, catalog.extra(pid), "live")
    proc = run_build(ROOT / "emails" / "email-1-ids-in-body.eml", tmp_path / "out", "--cdp", "http://127.0.0.1:9",
                     env=dict(os.environ, RFQ_PRODUCTS_DB=str(db_path)))
    assert proc.returncode == 0, proc.stderr
    assert "Chrome is not open" not in proc.stderr  # no browser was needed
    run = json.loads((tmp_path / "out" / "email-1-ids-in-body" / "run.json").read_text(encoding="utf-8"))
    assert run["mode"] == "live" and run["counts"]["by_source"]["live"] == 6
    assert sum("Read from the product database" in n["text"] for n in run["notes"]) == 6
    assert sheet_rows(tmp_path / "out" / "email-1-ids-in-body" / "RFQ.xlsx", "RFQ") == \
        sheet_rows(ROOT / "reference" / "email-1 reference output.xlsx", "RFQ")
