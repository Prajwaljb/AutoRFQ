"""/rfq: the plain upload page from the deck. Upload a request email, get the RFQ Excel back.

Server-rendered and synchronous, so it works anywhere (Azure Functions included) without the dashboard's live
updates. The result is a page with a Download button: browsers block a file sent straight back from a form.
"""
import html
import json
import time
from pathlib import PureWindowsPath

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import HTMLResponse

from app import settings
from app.services import runner
from rfq import config
from rfq.infra.io import safe_folder_name

router = APIRouter()

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AutoRFQ · Upload an RFQ</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--navy:#00446a;--blue:#00a0dd;--mist:#e6ecf0;--steel:#b2c7d2}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;font-family:Inter,Arial,sans-serif;color:#e6ecf0;
background:radial-gradient(1200px 600px at 10% -10%,#00a0dd55,transparent 60%),
radial-gradient(900px 500px at 110% 10%,#7c3aed40,transparent 60%),#07121c;display:flex;align-items:center;
justify-content:center;padding:24px}}
.card{{width:100%;max-width:560px;background:rgba(16,34,49,.72);backdrop-filter:blur(14px);
border:1px solid rgba(178,199,210,.25);border-radius:18px;padding:32px;box-shadow:0 30px 80px -20px #00a0dd55}}
h1{{margin:0 0 4px;font-size:26px}}.brand{{letter-spacing:.2em;font-weight:700;font-size:12px;color:var(--blue)}}
p{{color:#b2c7d2;line-height:1.55}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}}
.stat{{background:rgba(0,160,221,.08);border:1px solid rgba(0,160,221,.25);border-radius:12px;padding:12px;text-align:center}}
.stat b{{display:block;font-size:26px;color:#fff}}.stat span{{font-size:12px;color:#9fb3c1}}
input[type=file]{{width:100%;padding:14px;border:1px dashed var(--steel);border-radius:12px;background:rgba(255,255,255,.03);color:#e6ecf0}}
.btn{{display:inline-flex;align-items:center;gap:8px;margin-top:16px;padding:12px 20px;border-radius:10px;border:0;
font:600 15px Inter,Arial;cursor:pointer;text-decoration:none;color:#00263b;background:linear-gradient(90deg,#00a0dd,#5eead4);
box-shadow:0 10px 30px -10px #00a0dd}}.btn:hover{{filter:brightness(1.1)}}
.ghost{{background:transparent;color:#e6ecf0;border:1px solid var(--steel);box-shadow:none;margin-left:8px}}
.q{{margin-top:12px;padding:12px;border-radius:12px;background:rgba(253,230,138,.08);border:1px solid rgba(253,230,138,.3);color:#fde68a;font-size:14px}}
.err{{color:#fda4af}}small{{color:#7f97a8}}a{{color:var(--blue)}}
</style></head><body><main class="card">{body}</main></body></html>"""

FORM = """<div class="brand">FERGUSON · AUTORFQ</div><h1>RFQ Agent</h1>
<p>Upload a request email (.eml). You get back the filled RFQ Excel, with a source for every value and the
quality agent's flags and Summary sheet.</p>
<form method="post" action="/rfq" enctype="multipart/form-data">
<input type="file" name="file" accept=".eml,message/rfc822" required>
<button class="btn" type="submit">Build the RFQ &rarr;</button></form>
{error}<p><small>{mode_note} · <a href="/">Open the dashboard</a></small></p>"""


def _mode():
    return settings.FORCED_MODE if settings.FORCED_MODE in config.MODES else config.NO_BROWSER


def _mode_note():
    if settings.FORCED_MODE:
        return "Deployed on Azure: products come from the backup catalog and spec sheets (no browser in the cloud)"
    return "Runs without a browser: backup catalog and spec sheets"


@router.get("/rfq", response_class=HTMLResponse, include_in_schema=False)
def upload_page():
    return PAGE.format(body=FORM.format(error="", mode_note=_mode_note()))


@router.post("/rfq", response_class=HTMLResponse, include_in_schema=False)
async def upload(file: UploadFile = File(...)):
    def fail(message):
        return HTMLResponse(PAGE.format(body=FORM.format(error=f'<p class="err">{html.escape(message)}</p>',
                                                         mode_note=_mode_note())), status_code=400)
    name = PureWindowsPath(file.filename or "").name
    if not name.lower().endswith(".eml"):
        return fail("Please upload an .eml file (save the email from your mail client).")
    data = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        return fail("That email is larger than 15 MB.")
    settings.UPLOADS.mkdir(parents=True, exist_ok=True)
    stem = safe_folder_name(name.rsplit(".", 1)[0].lstrip(". "), limit=50) or "upload"
    eml = settings.UPLOADS / f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}.eml"
    eml.write_bytes(data)
    proc = runner.run_sync(eml, _mode(), settings.RUNS)
    run_dir = settings.RUNS / safe_folder_name(eml.stem)
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fail("The RFQ could not be built: " + (proc.stderr or proc.stdout or "unknown error")[-300:])
    c = run["counts"]
    status = {"ready": "Your RFQ is ready", "needs_review": "Your RFQ is built and held for review",
              "failed": "We hit a problem"}.get(run["status"], "Your RFQ is ready")
    quality = ""
    if run.get("quality_ran"):
        quality = (f'<div class="q">Quality agent: {c.get("flags", 0)} value(s) to check '
                   f'({c.get("high_flags", 0)} high), {c.get("missing", 0)} blank cell(s), '
                   f'{run.get("units_converted", 0)} unit(s) standardised. {html.escape(run.get("ai_status", ""))}.'
                   f'</div>')
    run_id = html.escape(run_dir.name)
    body = (f'<div class="brand">FERGUSON · AUTORFQ</div><h1>{status}</h1>'
            f'<p>{html.escape(run.get("subject", ""))}</p>'
            f'<div class="stats"><div class="stat"><b>{c["items"]}</b><span>IDs</span></div>'
            f'<div class="stat"><b>{c["found"]}</b><span>found ({c["by_source"]["live"]} from the web)</span></div>'
            f'<div class="stat"><b>{c["not_found"]}</b><span>not found</span></div></div>{quality}'
            f'<a class="btn" href="/api/runs/{run_id}/files/{html.escape(run.get("xlsx", "RFQ.xlsx"))}">'
            f'Download RFQ.xlsx</a><a class="btn ghost" href="/runs/{run_id}">Open in dashboard</a>'
            f'<p><a href="/rfq">&larr; Build another RFQ</a></p>')
    return PAGE.format(body=body)
