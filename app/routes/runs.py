"""Runs: list, detail, start (upload or sample), live progress (SSE), the original email and files."""
import asyncio
import email
import email.policy
import json
import time
from pathlib import PureWindowsPath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app import settings
from app.services import runner, store
from rfq import config
from rfq.extract.mail import read_email
from rfq.infra.io import safe_folder_name

router = APIRouter(prefix="/api")


def _detail_or_404(run_id):
    try:
        return store.detail(run_id)
    except store.NotFound:
        raise HTTPException(404, "No such run.")


@router.get("/runs")
def list_runs():
    return {"runs": store.list_runs()}


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    data = _detail_or_404(run_id)
    if data["run"].get("quality_ran"):
        from rfq.review import state
        data["review"] = state.view(store.run_dir(run_id))
    data["mail_configured"] = settings.mail_configured()
    return data


@router.post("/runs")
async def start_run(file: UploadFile | None = File(None), sample: str = Form(""), mode: str = Form("")):
    mode = settings.FORCED_MODE or mode or settings.default_mode()
    if mode not in config.MODES:
        raise HTTPException(400, f"Unknown mode {mode!r}.")
    settings.UPLOADS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if file is not None and file.filename:
        if not file.filename.lower().endswith(".eml"):
            raise HTTPException(400, "Please upload an .eml file (save the email from your mail client).")
        data = await file.read(settings.MAX_UPLOAD_BYTES + 1)
        if len(data) > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(400, "That email is larger than 15 MB.")
        base = PureWindowsPath(file.filename).name  # drops any path, / or \\ separated
        stem = safe_folder_name(base.rsplit(".", 1)[0].lstrip(". "), limit=50) or "upload"  # server picks
    elif sample:
        path = settings.ROOT / "emails" / f"{sample}.eml"
        if not settings.RUN_ID_RE.match(sample) or not path.is_file():
            raise HTTPException(404, "No such sample email.")
        data, stem = path.read_bytes(), sample
    else:
        raise HTTPException(400, "Upload an .eml file or pick a sample email.")
    eml = settings.UPLOADS / f"{stem}-{stamp}.eml"
    n = 2
    while eml.exists() or (settings.OUT / eml.stem).exists():
        eml = settings.UPLOADS / f"{stem}-{stamp}-{n}.eml"
        n += 1
    eml.write_bytes(data)
    run_id = runner.start(eml, mode)
    return {"id": run_id, "mode": mode}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str):
    """Server-sent events: every pipeline event, then 'end' when the run is finished."""
    try:
        path = store.run_dir(run_id) / "events.jsonl"
    except store.NotFound:
        raise HTTPException(404, "No such run.")

    async def stream():
        sent, deadline, idle = 0, time.monotonic() + settings.BUILD_TIMEOUT, 0
        while time.monotonic() < deadline:
            lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
            for line in lines[sent:]:
                yield f"data: {line}\n\n"
            new = len(lines) - sent
            sent = len(lines)
            done = any('"type": "run_done"' in line for line in lines)
            job = runner.job(run_id)
            finished = done or (job is not None and job["state"] in ("done", "failed"))
            if finished or (job is None and new == 0 and idle > 6):
                yield f"data: {json.dumps({'type': 'end', 'state': (job or {}).get('state', 'done')})}\n\n"
                return
            idle = 0 if new else idle + 1
            await asyncio.sleep(0.4)
            yield ": keep-alive\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/runs/{run_id}/email")
def original_email(run_id: str):
    run = _detail_or_404(run_id)["run"]
    path = run.get("email_path") or (runner.job(run_id) or {}).get("email_path", "")
    from pathlib import Path
    if not path or not Path(path).exists():
        raise HTTPException(404, "The original email is not available.")
    data = read_email(Path(path))
    return {"subject": data.subject, "sender": data.sender, "sender_name": data.sender_name, "date": data.date,
            "texts": [{"label": label, "text": text} for label, text in data.texts],
            "attachments": [{"name": name, "bytes": len(payload)} for name, payload in data.attachments]}


@router.get("/runs/{run_id}/preview")
def reply_preview(run_id: str):
    """The customer email exactly as it would be sent."""
    try:
        path = store.file_path(run_id, "reply.eml")
    except store.NotFound:
        raise HTTPException(404, "No reply yet.")
    msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
    text = msg.get_body(("plain",))
    html = msg.get_body(("html",))
    return {"to": msg.get("To", ""), "subject": msg.get("Subject", ""),
            "text": text.get_content() if text else "", "html": html.get_content() if html else "",
            "attachments": [p.get_filename() for p in msg.iter_attachments()]}


@router.get("/runs/{run_id}/files/{name}")
def download(run_id: str, name: str):
    try:
        path = store.file_path(run_id, name)
    except store.NotFound:
        raise HTTPException(404, "No such file.")
    media = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "eml": "message/rfc822"}.get(name.rsplit(".", 1)[-1], "text/plain")
    return FileResponse(path, media_type=media, filename=f"{run_id}-{name}" if name.endswith(".xlsx") else name)


@router.get("/pages/{product_id}/screenshot")
def page_screenshot(product_id: str):
    try:
        return FileResponse(store.screenshot(product_id), media_type="image/png")
    except store.NotFound:
        raise HTTPException(404, "No screenshot for this item.")
