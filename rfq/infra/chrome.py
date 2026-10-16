"""Opens the Chrome window the live lookup drives (remote debugging on port 9333), on any OS.

If a debuggable Chrome already answers on the port, it does nothing. Otherwise it finds Chrome (then Edge,
which speaks the same protocol, or Chromium), starts it with its own profile in the temp folder, and waits
until it answers.

The window is hidden by default (RFQ_SHOW_BROWSER=1 shows it). It is still a real, headed browser:
ferguson.com refuses headless Chrome, so on Linux it runs on an invisible virtual display (Xvfb) when one is
installed, and on Windows/macOS the window opens off-screen.
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


def close_browser(cdp):
    """Closes the scraping browser at cdp (all its windows). True if one was closed.

    Only the dedicated scraping profile listens on the debugging port, so the user's own browsing is
    never touched.
    """
    if not chrome_available(cdp):
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp, timeout=5000)
            try:
                browser.new_browser_cdp_session().send("Browser.close")
            except Exception:
                pass  # the connection drops as the browser exits
    except Exception:
        return False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and chrome_available(cdp, timeout=0.3):
        time.sleep(0.2)
    return not chrome_available(cdp, timeout=0.3)


def port_of(cdp):
    try:
        return int(cdp.rstrip("/").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 9333


def show_window():
    return os.environ.get("RFQ_SHOW_BROWSER", "0").strip().lower() in ("1", "true", "yes")


def hidden_prefix():
    """(command prefix, extra Chrome args, how it is hidden) for a hidden but headed window."""
    if sys.platform.startswith("linux"):
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            return [xvfb, "-a", "-s", "-screen 0 1366x900x24"], ["--window-size=1366,900"], "on a virtual display"
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return [], [], "no display and no Xvfb (install xvfb)"
    return [], ["--window-position=-32000,-32000", "--window-size=1366,900"], "off-screen"


def launch(port=9333, browser=None, wait=20, show=None):
    """Returns (ok, message). show=None follows RFQ_SHOW_BROWSER (hidden by default)."""
    cdp = f"http://127.0.0.1:{port}"
    if chrome_available(cdp):
        return True, f"Chrome is already open for scraping at {cdp}."
    if port_in_use(port):
        return False, f"Port {port} is used by another program. Close it or use --port (and --cdp on build.py)."
    exe = find_browser(browser)
    if exe is None:
        return False, "No Chrome, Edge or Chromium found. Install Chrome, or pass --browser <path to chrome>."
    profile = Path(tempfile.gettempdir()) / "chrome-rfq"
    show = show_window() if show is None else show
    prefix, extra, how = ([], [], "visible") if show else hidden_prefix()
    if os.environ.get("RFQ_IN_CONTAINER") == "1":
        extra = extra + ["--no-sandbox", "--disable-dev-shm-usage"]
    args = prefix + [str(exe), f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run",
            "--no-default-browser-check", *extra, START_URL]
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True  # keeps running after this script exits
    subprocess.Popen(args, **kwargs)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if chrome_available(cdp):
            return True, f"Opened {exe.name} ({how}) for scraping at {cdp} (profile {profile})."
        time.sleep(0.5)
    return False, f"Started {exe} but it did not answer at {cdp} within {wait}s."
