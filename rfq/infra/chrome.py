"""Opens the Chrome window the live lookup drives (remote debugging on port 9333), on any OS.

If a debuggable Chrome already answers on the port, it does nothing. Otherwise it finds Chrome (then Edge,
which speaks the same protocol, or Chromium), starts it with its own profile in the temp folder, and waits
until it answers. Leave the window open while RFQs are processed; click "Stay signed out" if asked.
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rfq.sources.ferguson_live import chrome_available

START_URL = "https://www.ferguson.com/"


def candidates():
    """Browser executables to try, best first."""
    if sys.platform.startswith("win"):
        roots = [os.environ.get(v, "") for v in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
        out = [Path(r) / "Google" / "Chrome" / "Application" / "chrome.exe" for r in roots if r]
        out += [Path(r) / "Microsoft" / "Edge" / "Application" / "msedge.exe" for r in roots if r]
        return out
    if sys.platform == "darwin":
        return [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]
    return [Path(p) for p in (shutil.which(n) for n in names) if p]


def find_browser(explicit=None):
    if explicit:
        return Path(explicit) if Path(explicit).exists() else None
    return next((p for p in candidates() if p.exists()), None)


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def launch(port=9333, browser=None, wait=20):
    """Returns (ok, message)."""
    cdp = f"http://127.0.0.1:{port}"
    if chrome_available(cdp):
        return True, f"Chrome is already open for scraping at {cdp}."
    if port_in_use(port):
        return False, f"Port {port} is used by another program. Close it or use --port (and --cdp on build.py)."
    exe = find_browser(browser)
    if exe is None:
        return False, "No Chrome, Edge or Chromium found. Install Chrome, or pass --browser <path to chrome>."
    profile = Path(tempfile.gettempdir()) / "chrome-rfq"
    args = [str(exe), f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run",
            "--no-default-browser-check", START_URL]
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True  # keeps running after this script exits
    subprocess.Popen(args, **kwargs)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if chrome_available(cdp):
            return True, f"Opened {exe.name} for scraping at {cdp} (profile {profile}). Leave it open."
        time.sleep(0.5)
    return False, f"Started {exe} but it did not answer at {cdp} within {wait}s."
