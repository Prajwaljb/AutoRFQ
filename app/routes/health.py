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
