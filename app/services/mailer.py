"""Approve & send: one reply in the customer's thread, reusing mailbot.make_reply and the saved email."""
import email
import email.policy
import json
import re
import time
from email.utils import formatdate, make_msgid
from pathlib import Path

from app import settings
from app.settings import mailbot
from rfq.review import state


class MailNotConfigured(Exception):
    pass


class SendFailed(Exception):
    pass


class BadRequest(Exception):
    """The request can't be sent as asked (wrong address, not an inbox RFQ, held)."""


EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def send(run_dir, to=None):
    """Sends the RFQ reply. The status becomes sent only after the mail server accepted it.

    Without `to`: the reply goes to the customer in the original thread (inbox RFQs).
    With `to`: reply.eml and RFQ.xlsx go to that address instead (uploaded or sample RFQs, demos, a colleague).
    A held RFQ can't be sent before it is reviewed and approved.
    """
    settings.refresh()
    if not settings.mail_configured():
        raise MailNotConfigured("Mail is not set up (BOT_EMAIL and BOT_PASSWORD in .env).")
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    status = run.get("status")
    if status == "needs_review":
        raise BadRequest("This RFQ is held: review and approve it first.")
    if to:
        to = to.strip()
        if not EMAIL_RE.match(to):
            raise BadRequest(f"{to!r} is not an email address.")
        if not (run_dir / "reply.eml").exists():
            raise SendFailed("There is no reply to send yet.")
        reply = email.message_from_bytes((run_dir / "reply.eml").read_bytes(), policy=email.policy.default)
        subject = run.get("subject") or "RFQ"
        for header in ("From", "To", "Subject", "In-Reply-To", "References", "Message-ID", "Date"):
            del reply[header]
        reply["From"] = mailbot.BOT_EMAIL
        reply["To"] = to
        reply["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        reply["Message-ID"] = make_msgid(domain=mailbot.BOT_EMAIL.split("@")[-1])
        reply["Date"] = formatdate(localtime=True)
        reply["Auto-Submitted"] = "auto-replied"
    else:
        original_path = Path(run.get("email_path", ""))
        if settings.INBOX not in original_path.resolve().parents:
            raise BadRequest("This RFQ was uploaded, not received in the inbox: there is no customer thread to "
                             "reply to. Use Email RFQ… with an address instead.")
        if status == "sent":
            raise BadRequest("This RFQ was already sent to the customer.")
        if status not in ("ready", "approved"):
            raise BadRequest(f"This RFQ is {status}: there is nothing to send.")
        if not original_path.exists():
            raise SendFailed("The original email is no longer on disk, so the reply can't be threaded.")
        original = email.message_from_bytes(original_path.read_bytes(), policy=email.policy.default)
        reply = mailbot.make_reply(original, run_dir)
    try:
        mailbot.send(reply, "rfq_email" if to else "reply", run_dir.name, "dashboard")
    except Exception as e:
        raise SendFailed(f"The mail server did not accept the reply ({type(e).__name__}). Try again.") from e
    state.set_status(run_dir, "sent")
    _record(run_dir, reply["To"])
    return reply["To"]


def _record(run_dir, to):
    path = run_dir / "run.json"
    run = json.loads(path.read_text(encoding="utf-8"))
    run.setdefault("sent_to", []).append({"to": str(to), "at": time.strftime("%Y-%m-%d %H:%M")})
    path.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
