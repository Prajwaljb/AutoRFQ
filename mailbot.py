"""Email mode: answer RFQ emails in a Gmail inbox with the RFQ Excel your base builds.

Every 30 seconds it checks the inbox for unread emails from today with "RFQ" in the subject or the text.
For each one it saves the email to out/inbox/, runs YOUR base on it:

    python rfq/build.py <saved email> --out out

and sends back the reply your base wrote (out/<email name>/reply.eml, RFQ.xlsx attached).
Anything you add to rfq/build.py, such as the quality agent, is in the reply automatically.

- If the run's status (out/<email name>/run.json) is needs_review, nothing goes to the customer yet: the
  RFQ waits for a person to approve it in the web app (optional notice to REVIEW_NOTIFY_EMAIL).
- If the base fails or times out, the sender gets a short "a person will follow up" reply.
- Every email is marked read before it is processed, so it is never retried in a loop, and a second
  watcher (another deployment) skips it.

Setup: in .env set BOT_EMAIL (the team Gmail) and BOT_PASSWORD (its 16-letter App Password).
Run:   python mailbot.py            (keep the Chrome window from Part A open; Ctrl+C to stop)
       python mailbot.py --once     (check the inbox once and exit)
Any other options are passed on to rfq/build.py, for example: python mailbot.py --offline
"""
import email
import email.policy
import imaplib
import json
import os
import smtplib
import subprocess
import sys
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUBJECT_KEYWORD = "RFQ"
POLL_SECONDS = 30
SENDER = "mailbot.py"  # who is sending, for the mail log (the web app sets "web app")
XLSX_TYPE = ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")


sys.path.insert(0, str(ROOT))
from rfq.infra import layout, maillog  # noqa: E402
from rfq.infra.env import load as load_env  # noqa: E402  (one .env loader for the bot, the base and the app)

load_env(ROOT / ".env")
OUT = Path(os.environ.get("RFQ_OUT_DIR", "").strip() or ROOT / "out").resolve()  # the web app reads the same folder
BOT_EMAIL = os.environ.get("BOT_EMAIL", "").strip()
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "").replace(" ", "")  # Google shows it in groups of 4
REVIEW_NOTIFY_EMAIL = os.environ.get("REVIEW_NOTIFY_EMAIL", "").strip()  # optional: who hears about held RFQs
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip()  # optional: link in "Held for review" lines


def log(text):
    print(time.strftime("%H:%M:%S"), text, flush=True)


def should_skip(msg):
    """A reason not to answer this email, or None."""
    sender = parseaddr(msg.get("Reply-To") or msg.get("From", ""))[1].lower()
    if not sender:
        return "no sender address"
    if sender == BOT_EMAIL.lower():
        return "sent by this inbox itself"
    if any(m in sender for m in ("no-reply", "noreply", "mailer-daemon")):
        return "automated sender"
    if msg.get("Auto-Submitted", "no").lower() != "no":
        return "automatic email"
    return None


def runs_dir():
    return layout.runs_dir(OUT)


def run_base(eml_path, extra_args):
    """Runs the team's base on one email. Returns the folder it wrote RFQ.xlsx into (out/runs/<name>)."""
    cmd = [sys.executable, "rfq/build.py", str(eml_path), "--out", str(runs_dir()), *extra_args]
    log("Running: " + " ".join(cmd[1:]))
    subprocess.run(cmd, cwd=ROOT, check=True, timeout=900, env=child_env())
    folder = runs_dir() / eml_path.stem
    if not (folder / "RFQ.xlsx").exists():
        raise FileNotFoundError(f"rfq/build.py did not save {folder / 'RFQ.xlsx'} (see the spec)")
    return folder


def child_env():
    """build.py's environment, with this process's sys.path (on Azure Functions the packages are only there)."""
    env = dict(os.environ)
    paths = [p for p in sys.path if p] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(paths))
    return env


def make_reply(original, folder, reply=None):
    """The reply the base wrote (reply.eml), or a plain one with RFQ.xlsx attached.

    Pass reply to send a ready-made message (e.g. the follow-up reply) with the same threading headers.
    """
    if reply is None and (folder / "reply.eml").exists():
        reply = email.message_from_bytes((folder / "reply.eml").read_bytes(), policy=email.policy.default)
    elif reply is None:
        reply = EmailMessage(policy=email.policy.default)
        reply.set_content("Hi,\n\nPlease find the filled RFQ attached.\n\nRFQ Agent")
        reply.add_attachment((folder / "RFQ.xlsx").read_bytes(), maintype=XLSX_TYPE[0],
                             subtype=XLSX_TYPE[1], filename="RFQ.xlsx")
    subject = original.get("Subject", "RFQ request")
    for header in ("From", "To", "Subject", "In-Reply-To", "References", "Message-ID", "Date"):
        del reply[header]
    reply["From"] = BOT_EMAIL
    reply["To"] = original.get("Reply-To") or original.get("From", "")
    reply["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if original.get("Message-ID"):  # keeps the reply in the same thread
        reply["In-Reply-To"] = original["Message-ID"]
        reply["References"] = f"{original.get('References', '')} {original['Message-ID']}".strip()
    reply["Message-ID"] = make_msgid(domain=BOT_EMAIL.split("@")[-1])
    reply["Date"] = formatdate(localtime=True)
    reply["Auto-Submitted"] = "auto-replied"  # stops other auto-replies answering back
    return reply


def send(message, kind="reply", run_id="", by="mailbot.py"):
    """Sends one email and logs the attempt (sent or failed) in the mail log, then re-raises a failure."""
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(BOT_EMAIL, BOT_PASSWORD)
            smtp.send_message(message)
    except Exception as e:
        maillog.record(message, kind, run_id, "failed", f"{type(e).__name__}: {e}", by)
        raise
    maillog.record(message, kind, run_id, "sent", by=by)


def run_status(folder):
    """The status the base wrote to run.json (ready / needs_review / failed), or None."""
    try:
        return json.loads((folder / "run.json").read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None


def set_status(folder, status):
    """Records what the bot did in run.json, so the web app shows it."""
    path = folder / "run.json"
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
        run["status"] = status
        path.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
    except (OSError, ValueError):
        pass


def follow_up_reply():
    """The reply sent when the base could not process the email: a person will follow up."""
    reply = EmailMessage(policy=email.policy.default)
    reply.set_content("Hi,\n\nThank you for your RFQ. We could not process it automatically this time; a "
                      "person from our team will follow up with you shortly.\n\nKind regards,\nFerguson RFQ Agent\n")
    return reply


def hold_for_review(msg, folder):
    """A run that needs human review: no reply to the customer yet, an optional notice to the team."""
    link = f"{DASHBOARD_URL.rstrip('/')}/runs/{folder.name}" if DASHBOARD_URL else f"the web app, run {folder.name}"
    log(f"Held for review: {link}")
    if REVIEW_NOTIFY_EMAIL:
        notice = EmailMessage(policy=email.policy.default)
        notice["From"] = BOT_EMAIL
        notice["To"] = REVIEW_NOTIFY_EMAIL
        notice["Subject"] = f"RFQ from {parseaddr(msg.get('From', ''))[1]} needs review"
        notice.set_content(f"An RFQ is waiting for review before it goes to the customer.\n\n"
                           f"Subject: {msg.get('Subject', '')}\nReview it here: {link}\n")
        try:
            send(notice, "review_notice", folder.name, SENDER)
        except Exception as e:
            log(f"Could not send the review notice: {e}")


def answer(msg, eml, extra_args):
    """Runs the base on one email and replies, holds it, or sends the follow-up reply."""
    try:
        folder = run_base(eml, extra_args)
    except Exception as e:  # build crashed or timed out: the sender still gets one reply
        log(f"The base failed on this email ({type(e).__name__}: {e}); sending the follow-up reply")
        send(make_reply(msg, None, follow_up_reply()), "fallback", eml.stem, SENDER)
        set_status(runs_dir() / eml.stem, "fallback_sent")
        return
    status = run_status(folder)
    if status == "needs_review":
        hold_for_review(msg, folder)
        return
    send(make_reply(msg, folder), "reply", folder.name, SENDER)
    set_status(folder, "fallback_sent" if status == "failed" else "sent")
    log(f"Replied with {folder / 'RFQ.xlsx'}")


def check_inbox(extra_args):
    """Answers every new RFQ email once. One bad email never blocks the others."""
    inbox_dir = OUT / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
        imap.login(BOT_EMAIL, BOT_PASSWORD)
        imap.select("INBOX")
        # Only today's unread emails that say RFQ in the subject or the text ("Please prepare the RFQ for
        # the items below", often with a blank or "Fwd:" subject): the rest of the inbox is never touched.
        _, data = imap.uid("SEARCH", None, "UNSEEN", "SINCE", time.strftime("%d-%b-%Y"),
                           "OR", "SUBJECT", f'"{SUBJECT_KEYWORD}"', "BODY", f'"{SUBJECT_KEYWORD}"')
        for uid in data[0].split():
            # Marked read first, before the build: a second watcher skips it, and a bad email is never
            # retried in a loop.
            imap.uid("STORE", uid, "+FLAGS", r"(\Seen)")
            try:
                _, fetched = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                raw = fetched[0][1]
                msg = email.message_from_bytes(raw, policy=email.policy.default)
                log(f"New email from {msg.get('From')}: {msg.get('Subject')}")
                reason = should_skip(msg)
                if reason:
                    log(f"Skipped ({reason})")
                else:
                    eml = inbox_dir / f"rfq-{time.strftime('%Y%m%d-%H%M%S')}-{uid.decode()}.eml"
                    eml.write_bytes(raw)
                    answer(msg, eml, extra_args)
            except Exception as e:  # e.g. SMTP down: log it; the email is already marked read
                log(f"Problem with email {uid.decode()}: {type(e).__name__}: {e}")


def heartbeat(by="mailbot.py", error=""):
    """Tells the web app the inbox is being watched (out/.mailbot.json): who checked, when, and any problem."""
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / ".mailbot.json").write_text(json.dumps({"email": BOT_EMAIL, "at": time.time(), "by": by,
                                                       "pid": os.getpid(), "error": error[:300]}), encoding="utf-8")
    except OSError:
        pass


def last_heartbeat():
    try:
        return json.loads((OUT / ".mailbot.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def check_once(extra_args=(), by="mailbot.py"):
    """One inbox check with heartbeats before and after (a long build never looks like a stopped bot).
    Returns "" or the problem."""
    global SENDER
    SENDER = by
    heartbeat(by)
    error = ""
    try:
        check_inbox(list(extra_args))
    except imaplib.IMAP4.error as e:
        error = f"Gmail login failed ({e}). Check BOT_EMAIL and BOT_PASSWORD."
    except Exception as e:  # a network blip or one bad email should not stop the bot
        error = f"{type(e).__name__}: {e}"
    heartbeat(by, error)
    return error


def main():
    args = sys.argv[1:]
    once = "--once" in args
    extra_args = [a for a in args if a != "--once"]
    if not BOT_EMAIL or not BOT_PASSWORD:
        sys.exit("Set BOT_EMAIL and BOT_PASSWORD in .env first (see the guide).")
    layout.migrate(OUT)
    if once:
        check_inbox(extra_args)
        return
    log(f"Watching {BOT_EMAIL} for emails with '{SUBJECT_KEYWORD}' in the subject. Ctrl+C to stop.")
    while True:
        error = check_once(extra_args)
        if error.startswith("Gmail login failed"):
            sys.exit(error)
        if error:
            log(f"Problem, trying again in {POLL_SECONDS}s: {error}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopped.")
