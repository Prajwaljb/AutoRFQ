"""Runs rfq/build.py as a subprocess, like mailbot.py does.

Never runs Playwright inside the web server's event loop (Windows event-loop limits, crash isolation,
timeouts). One live run at a time, because there is one scraping Chrome window; others wait their turn.
"""
import subprocess
import sys
import threading
import time

from app import settings
from rfq import config

_jobs = {}
_jobs_lock = threading.Lock()
_live_lock = threading.Lock()


def job(run_id):
    with _jobs_lock:
        return dict(_jobs[run_id]) if run_id in _jobs else None


def running():
    with _jobs_lock:
        return [k for k, v in _jobs.items() if v["state"] in ("queued", "processing")]


def _set(run_id, **fields):
    with _jobs_lock:
        _jobs.setdefault(run_id, {}).update(fields)


def command(eml, mode, out=None):
    cmd = [sys.executable, str(settings.ROOT / "rfq" / "build.py"), str(eml), "--out", str(out or settings.OUT)]
    if mode == config.OFFLINE:
        cmd.append("--offline")
    elif mode == config.NO_BROWSER:
        cmd.append("--no-browser")
    else:
        cmd += ["--cdp", settings.CDP]
    return cmd


def child_env():
    """The environment for build.py. On Azure Functions the packages live on the worker's sys.path only
    (.python_packages), so the subprocess gets that path explicitly."""
    import os
    env = dict(os.environ)
    paths = [p for p in sys.path if p]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(paths))
    return env


def _work(run_id, eml, mode):
    lock = _live_lock if mode == config.LIVE else None
    try:
        if lock:
            lock.acquire()
        _set(run_id, state="processing", started=time.time())
        proc = subprocess.run(command(eml, mode), cwd=settings.ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=settings.BUILD_TIMEOUT, env=child_env())
        if proc.returncode == 0:
            _set(run_id, state="done", output=proc.stdout.strip())
        else:
            _set(run_id, state="failed", error=(proc.stderr.strip() or f"exit {proc.returncode}")[-500:])
    except subprocess.TimeoutExpired:
        _set(run_id, state="failed", error=f"timed out after {settings.BUILD_TIMEOUT}s")
    except Exception as e:
        _set(run_id, state="failed", error=f"{type(e).__name__}: {e}")
    finally:
        if lock:
            lock.release()


def start(eml, mode):
    """Starts a build in the background. Returns the run id (the email file name without .eml)."""
    from rfq.infra.io import safe_folder_name
    run_id = safe_folder_name(eml.stem)
    _set(run_id, state="queued", mode=mode, email_path=str(eml), error="", started=time.time())
    (settings.OUT / run_id).mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_work, args=(run_id, eml, mode), daemon=True).start()
    return run_id


def run_sync(eml, mode, out):
    """A blocking build (self-check)."""
    return subprocess.run(command(eml, mode, out), cwd=settings.ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=settings.BUILD_TIMEOUT, env=child_env())
