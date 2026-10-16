from pathlib import Path

import openpyxl
import pytest

from conftest import EMAILS, make_email
from rfq.extract import extract_items, read_email
from rfq.extract.attachments import cell_text, read_attachment
from rfq.extract.patterns import find_items
from rfq.models import CODE, FERGUSON, RunResult

EXPECTED = {
    "email-1-ids-in-body": ["5106912", "5106935", "5106914", "5106966", "5106891", "5106880"],
    "email-2-ids-in-attachment": ["1376044", "1432040", "233900", "4742155", "5106899", "9677514",
                                  "7099537", "225123"],
    "email-3-mixed-ferguson-and-competitor": ["5106878", "5106907", "4570880", "9677531",
                                              "17783-79-3000", "31-024", "MTX-4409-XQ"],
    "email-4-messy-forward": ["5106926", "8067331", "1844552", "4783795", "5106888", "9677533",
                              "17774-79-3000"],
}


def extract(path):
    result = RunResult("t", path.name, "offline")
    extract_items(read_email(path), result)
    return result


@pytest.mark.parametrize("name", EXPECTED)
def test_sample_emails(name):
    result = extract(EMAILS / f"{name}.eml")
    assert [i.product_id for i in result.items] == EXPECTED[name]


def test_competitor_brand_and_duplicate_notes():
    r3 = extract(EMAILS / "email-3-mixed-ferguson-and-competitor.eml")
    brands = {i.product_id: i.brand for i in r3.items if i.kind == CODE}
    assert brands == {"17783-79-3000": "Mutual Industries", "31-024": "Empire", "MTX-4409-XQ": ""}
    r4 = extract(EMAILS / "email-4-messy-forward.eml")
    notes = [(n.product_id, n.text) for n in r4.sorted_notes()]
    assert ("5106926", "Listed twice in the request; kept once.") in notes
    assert {i.product_id: i.qty for i in r4.items}["5106926"] == "40 rolls"


def test_attachment_quantities():
    r2 = extract(EMAILS / "email-2-ids-in-attachment.eml")
    assert r2.items[0].qty == "10 rolls"
    assert r2.items[0].line == "rfq_items.xlsx row 2"


@pytest.mark.parametrize("text,expected", [
    ("Call +91 20 4110012 or tel: 5106913. Item 5106912", ["5106912"]),
    ("Ship to pin 411001, PO 123456, order #554433, invoice no. 778899: 5106880", ["5106880"]),
    ("Qty: 120000 rolls of 9677531", ["9677531"]),
    ("See https://www.ferguson.com/product/tape-pb3104y3/5106880.html please", []),
    ("price 1234.50 on 2026-10-16, phone 555-123-4567, ASTM D-2103", []),
    ("#5106926, 1844552 , 4783795", ["5106926", "1844552", "4783795"]),
    ("3 inch x 40 rolls of 17783-79-3000 and mtx-4409-xq", ["17783-79-3000", "mtx-4409-xq"]),
])
def test_find_items_filters(text, expected):
    assert [h["value"] for h in find_items(text)] == expected


def test_cell_text_normalises_numbers():
    assert cell_text(1376044.0) == "1376044"
    assert cell_text(" #5106912 ") == "5106912"
    assert cell_text("1376044.0") == "1376044"


def _xlsx_bytes(rows, tmp_path):
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    path = tmp_path / "x.xlsx"
    wb.save(path)
    return path.read_bytes()


def test_xlsx_without_header_scans_cells(tmp_path):
    values, notes = read_attachment("list.xlsx", _xlsx_bytes([[5106912.0, "x"], [None, "5106935"]], tmp_path))
    assert [v[0] for v in values] == ["5106912", "x", "5106935"] and not notes


def test_bad_attachments_give_notes():
    assert "resend" in read_attachment("old.xls", b"\xd0\xcf\x11\xe0")[1][0]
    assert "resend" in read_attachment("broken.xlsx", b"not a zip")[1][0]
    values, notes = read_attachment("items.csv", "Part number,Qty\n5106912,4\n".encode("utf-8-sig"))
    assert values == [("5106912", "items.csv row 2", "4")] and not notes


def test_html_only_and_forwarded_email(tmp_path):
    html = make_email(tmp_path / "h.eml", html="<p>Items:<br>5106912</p><div>#5106935</div>")
    assert [i.product_id for i in extract(html).items] == ["5106912", "5106935"]
    inner = make_email(tmp_path / "inner.eml", body="Inner list: 5106914")
    outer = make_email(tmp_path / "outer.eml", body="See attached email. 5106912",
                       attachments=[("fwd.eml", inner.read_bytes(), "message", "rfc822")])
    assert [i.product_id for i in extract(outer).items] == ["5106912", "5106914"]


def test_item_cap(tmp_path):
    body = "\n".join(str(1000000 + n) for n in range(400))
    result = extract(make_email(tmp_path / "many.eml", body=body))
    assert len(result.items) == 300
    assert any("not processed" in n.text for n in result.notes)
    assert all(i.kind == FERGUSON for i in result.items)


def test_reply_reads_its_own_words_not_the_quote(tmp_path):
    body = ("use 9677539 instead please\n\nOn Thu, 15 Oct 2026 at 10:00, RFQ Agent <bot@example.com> wrote:\n"
            "> Closest Ferguson match: 9677539. Also similar: 5106914, 5106918.\n> 5106926\n")
    assert [i.product_id for i in extract(make_email(tmp_path / "r.eml", body=body)).items] == ["9677539"]
    only_quote = "Please quote these.\n\nOn Thu, 15 Oct 2026, Priya <p@example.com> wrote:\n> 5106912\n> 5106935\n"
    assert [i.product_id for i in extract(make_email(tmp_path / "q.eml", body=only_quote)).items] == \
        ["5106912", "5106935"]


def test_alternatives_for_not_found_items():
    from rfq.models import Item
    from rfq.sources.alternatives import Alternatives
    from rfq.sources.catalog import CatalogSource
    alt = Alternatives(CatalogSource())
    first = lambda pid, line="": [o["product_id"] for o in alt.suggest(Item(0, pid, kind="code", line=line))[2]][:1]
    assert first("225123") == ["5106912"]            # old listing: 6 in blue water detectable tape
    assert first("9677533") == ["9677539"]           # old listing: red marking tape
    assert first("17774-79-3000", "the Mutual detectable electric tape, part 17774-79-3000") == ["5106914"]
    assert first("31-024", "Empire 31-024") == []    # nothing known about it: no guess
