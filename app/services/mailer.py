"""Approve & send: one reply in the customer's thread, reusing mailbot.make_reply and the saved email."""
import email
import email.policy
import json
from pathlib import Path

from app import settings
from app.settings import mailbot
from rfq.review import state


class MailNotConfigured(Exception):
    pass


class SendFailed(Exception):
    pass


def send(run_dir):
    """Sends the approved reply. The status becomes sent only after the mail server accepted it."""
    if not settings.mail_configured():
        raise MailNotConfigured("Mail is not set up (BOT_EMAIL and BOT_PASSWORD in .env).")
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("status") == "sent":
        raise SendFailed("This RFQ was already sent.")
    if run.get("status") != "approved":
        raise SendFailed("Approve the RFQ before sending it.")
    original_path = Path(run.get("email_path", ""))
    if not original_path.exists():
        raise SendFailed("The original email is no longer on disk, so the reply can't be threaded.")
    original = email.message_from_bytes(original_path.read_bytes(), policy=email.policy.default)
    reply = mailbot.make_reply(original, run_dir)
    try:
        mailbot.send(reply)
    except Exception as e:
        raise SendFailed(f"The mail server did not accept the reply ({type(e).__name__}). Try again.") from e
    state.set_status(run_dir, "sent")
    return reply["To"]
