"""Watches the team inbox from inside the web app, so no separate mailbot.py window is needed.

Starts with the app when BOT_EMAIL / BOT_PASSWORD are set (RFQ_INBOX_WATCH=0 turns it off). It uses
mailbot.check_once, so replies, holds and follow-ups behave exactly like mailbot.py. If a separate mailbot.py
is already watching (a fresh heartbeat from another process), the app leaves the inbox to it, so no email
gets two replies. On Azure Functions a timer trigger (function_app.py) does this job instead.
"""
import os
import threading
import time

from app import settings

POLL_SECONDS = 30
_started = threading.Event()
_stop = threading.Event()


def enabled():
    return os.environ.get("RFQ_INBOX_WATCH", "1").strip() != "0" and not os.environ.get("FUNCTIONS_WORKER_RUNTIME")


def other_watcher():
    """True if another process (mailbot.py) checked the inbox in the last 90 seconds."""
    beat = settings.mailbot.last_heartbeat()
    return (bool(beat) and beat.get("pid") != os.getpid() and beat.get("by") == "mailbot.py"
            and time.time() - float(beat.get("at", 0)) < 90)


def _loop():
    while not _stop.is_set():
        settings.refresh()
        if settings.mail_configured() and not other_watcher():
            from app.services import runner
            with runner._live_lock:  # one scraping Chrome: inbox builds and uploaded live runs take turns
                settings.mailbot.check_once(by="web app")
        _stop.wait(POLL_SECONDS)


def start():
    if enabled() and not _started.is_set():
        _started.set()
        threading.Thread(target=_loop, name="inbox-watcher", daemon=True).start()


def stop():
    _stop.set()
