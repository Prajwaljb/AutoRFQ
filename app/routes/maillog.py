"""The log of sent emails: GET /api/mail-log (newest first; filter by run, status or kind)."""
from fastapi import APIRouter

from rfq.infra import maillog

router = APIRouter(prefix="/api")


@router.get("/mail-log")
def mail_log(limit: int = 200, run_id: str = "", status: str = "", kind: str = ""):
    return {"entries": maillog.recent(limit, run_id, status, kind), "counts": maillog.counts(), "kinds": maillog.KINDS}
