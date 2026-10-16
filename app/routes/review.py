"""Review decisions, undo, approve and send."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import mailer, store
from rfq.review import state

router = APIRouter(prefix="/api/runs/{run_id}")


class Decision(BaseModel):
    flag_id: str
    action: str = Field(pattern="^(keep|edit|clear)$")
    reviewer: str = Field(min_length=1, max_length=80)
    value: str | None = None
    version: int | None = None


class Undo(BaseModel):
    version: int | None = None


class Substitute(BaseModel):
    requested: str = Field(min_length=1, max_length=60)
    alternative: str = Field(pattern=r"^\d{5,7}$")
    reviewer: str = Field(min_length=1, max_length=80)


class Approve(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    send: bool = False


def _dir(run_id):
    try:
        return store.run_dir(run_id)
    except store.NotFound:
        raise HTTPException(404, "No such run.")


@router.post("/review")
def decide(run_id: str, body: Decision):
    folder = _dir(run_id)
    try:
        state.decide(folder, body.flag_id, body.action, body.reviewer, body.value, body.version)
    except state.Stale as e:
        raise HTTPException(409, str(e))
    except state.ReviewError as e:
        raise HTTPException(400, str(e))
    return state.view(folder)


@router.post("/review/undo")
def undo(run_id: str, body: Undo):
    folder = _dir(run_id)
    try:
        state.undo(folder, body.version)
    except state.Stale as e:
        raise HTTPException(409, str(e))
    except state.ReviewError as e:
        raise HTTPException(400, str(e))
    return state.view(folder)


@router.post("/substitute")
def substitute(run_id: str, body: Substitute):
    """Replaces a Not found item with a Ferguson item (a reviewer's decision; the customer confirms)."""
    folder = _dir(run_id)
    try:
        state.substitute(folder, body.requested, body.alternative, body.reviewer)
    except state.ReviewError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.post("/approve")
def approve(run_id: str, body: Approve):
    """Rebuilds the RFQ without review marks (status approved), then optionally sends the reply."""
    folder = _dir(run_id)
    try:
        state.finalise(folder, body.reviewer)
    except state.ReviewError as e:
        raise HTTPException(400, str(e))
    result = {"status": "approved", "sent_to": None}
    if body.send:
        try:
            result["sent_to"] = mailer.send(folder)
            result["status"] = "sent"
        except (mailer.MailNotConfigured, mailer.SendFailed, mailer.BadRequest) as e:
            result["send_error"] = str(e)
    return result


class SendTo(BaseModel):
    to: str | None = Field(default=None, max_length=200)


@router.post("/send")
def send(run_id: str, body: SendTo | None = None):
    """Sends the RFQ: to the customer's thread, or to the address in `to`. Never twice to the customer."""
    folder = _dir(run_id)
    try:
        return {"status": "sent", "sent_to": mailer.send(folder, body.to if body else None)}
    except (mailer.MailNotConfigured, mailer.BadRequest) as e:
        raise HTTPException(400, str(e))
    except mailer.SendFailed as e:
        raise HTTPException(502, str(e))
