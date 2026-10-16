"""Health (Chrome, AI review, inbox, mail), sample emails and the email-1 self-check."""
import email
import email.policy
import shutil

from fastapi import APIRouter

from app import settings
from app.services import runner, store
from rfq import config
from rfq.infra import env
from rfq.quality import llm
from rfq.sources.ferguson_live import chrome_available

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    settings.refresh()
    forced = settings.FORCED_MODE
    return {
        "chrome": False if forced in ("no-browser", "offline") else chrome_available(settings.CDP, timeout=0.5),
        "chrome_auto": config.AUTO_BROWSER and forced not in ("no-browser", "offline"),
        "ai": llm.enabled(),
        "inbox": store.inbox_watching(),
        "mail": settings.mail_configured(),
        "mode": settings.default_mode(),
        "forced_mode": forced or None,
        "running": runner.running(),
        "settings": env.status(),  # which keys are set (never their values)
        "api_version": settings.API_VERSION,
    }


@router.get("/samples")
def samples():
    out = []
    for path in sorted((settings.ROOT / "emails").glob("*.eml")):
        msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
        out.append({"name": path.stem, "subject": str(msg.get("Subject", "")),
                    "sender": str(msg.get("From", ""))})
    return {"samples": out}


def _rows(path, sheet):
    import openpyxl
    wb = openpyxl.load_workbook(path)
    return [tuple("" if v is None else str(v) for v in r) for r in wb[sheet].iter_rows(min_row=2, values_only=True)
            if any(v not in (None, "") for v in r)]


@router.post("/selfcheck")
def selfcheck():
    """Builds email 1 offline and compares it with the reference, cell for cell."""
    out = settings.OUT / "selfcheck"
    shutil.rmtree(out, ignore_errors=True)
    proc = runner.run_sync(settings.ROOT / "emails" / "email-1-ids-in-body.eml", config.OFFLINE, out)
    xlsx = out / "email-1-ids-in-body" / "RFQ.xlsx"
    if proc.returncode != 0 or not xlsx.exists():
        return {"ok": False, "detail": (proc.stderr or proc.stdout)[-400:]}
    ours, ref = _rows(xlsx, "RFQ"), _rows(config.REFERENCE, "RFQ")
    rows_ok = sum(1 for a, b in zip(ours, ref) if a == b)
    s_ours, s_ref = _rows(xlsx, "Sources"), _rows(config.REFERENCE, "Sources")
    src_ok = sum(1 for a, b in zip(s_ours, s_ref) if a == b)
    ok = rows_ok == len(ref) == len(ours) and src_ok == len(s_ref) == len(s_ours)
    return {"ok": ok, "rows": f"{rows_ok}/{len(ref)}", "sources": f"{src_ok}/{len(s_ref)}",
            "detail": proc.stdout.strip()}


@router.post("/mail/test")
def mail_test():
    """Signs in to the team inbox (IMAP) and the mail server (SMTP) without sending anything."""
    import imaplib
    import smtplib
    settings.refresh()
    if not settings.mail_configured():
        return {"ok": False, "detail": "BOT_EMAIL / BOT_PASSWORD are not set in .env."}
    out = {}
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", timeout=20) as imap:
            imap.login(settings.mailbot.BOT_EMAIL, settings.mailbot.BOT_PASSWORD)
        out["imap"] = "ok"
    except Exception as e:
        out["imap"] = f"{type(e).__name__}: {str(e)[:120]}"
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(settings.mailbot.BOT_EMAIL, settings.mailbot.BOT_PASSWORD)
        out["smtp"] = "ok"
    except Exception as e:
        out["smtp"] = f"{type(e).__name__}: {str(e)[:120]}"
    ok = out["imap"] == "ok" and out["smtp"] == "ok"
    hint = "" if ok else (" Use a Google App Password (16 lowercase letters) for BOT_PASSWORD, not the account password:"
                          " Google Account -> Security -> 2-Step Verification -> App passwords. Then restart the app.")
    return {"ok": ok, "detail": f"IMAP: {out['imap']} · SMTP: {out['smtp']}.{hint}"}
