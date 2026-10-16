"""Deploys AutoRFQ to Azure and checks the live link.

    az logout && az login          # after setting up MFA at portal.azure.com (AADSTS50076/50079)
    python scripts/deploy_azure.py [--target functions|webapp] [--name autorfq-xyz] [--group rg-autorfq]
                                   [--location centralindia] [--with-secrets] [--dry-run]

--target functions (default, as on Day 3): resource group, storage account, Function App (Python 3.12, Linux,
consumption), function_app.py + host.json wrap the FastAPI app; only /tmp is writable (RFQ_OUT_DIR=/tmp/autorfq).
--target webapp: App Service (Linux, Python 3.12, F1) instead.

What it does:
1. builds the web UI (npm ci && npm run build in web/) unless web/dist is up to date,
2. packages app/, rfq/, data/, templates/, reference/, emails/, mailbot.py, requirements.txt, web/dist,
3. creates the resource group, plan and web app if they don't exist (Python 3.12),
4. sets RFQ_MODE=no-browser (no browser in the cloud), RFQ_OUT_DIR=/home/data/out (persistent),
   and with --with-secrets the AZURE_OPENAI_* and BOT_* values from .env,
5. deploys the zip (Oryx installs requirements.txt), then waits for /api/health and runs the email-1
   self-check against the live URL.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["app", "rfq", "data", "templates", "reference", "emails", "mailbot.py", "spec.md"]
FUNCTION_FILES = ["function_app.py", "host.json"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "node_modules"}
STARTUP = "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
SECRET_KEYS = ["OPENAI_API_KEY", "OPENAI_MODEL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
               "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION", "BOT_EMAIL", "BOT_PASSWORD",
               "REVIEW_NOTIFY_EMAIL", "SERPAPI_API_KEY", "ADMIN_TOKEN", "RFQ_DB_TTL_HOURS"]


def az(*args, check=True, capture=True):
    exe = shutil.which("az")
    if not exe:
        sys.exit("The Azure CLI (az) is not installed.")
    proc = subprocess.run([exe, *args, "-o", "json"], capture_output=capture, text=True, encoding="utf-8")
    if check and proc.returncode != 0:
        sys.exit(f"az {' '.join(args[:3])} failed:\n{(proc.stderr or '').strip()[-1500:]}")
    try:
        return json.loads(proc.stdout) if capture and proc.stdout.strip() else None
    except ValueError:
        return proc.stdout


def build_web(force=False):
    web = ROOT / "web"
    dist = web / "dist" / "index.html"
    newest_src = max(p.stat().st_mtime for p in (web / "src").rglob("*") if p.is_file())
    if dist.exists() and dist.stat().st_mtime > newest_src and not force:
        print("web/dist is up to date")
        return
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm is needed to build the web UI (Node 20+).")
    print("building web/ ...")
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=web, check=True)
    subprocess.run([npm, "run", "build"], cwd=web, check=True)


def cloud_requirements(target):
    """requirements.txt for the cloud: no playwright (no browser there), plus azure-functions for Functions."""
    lines = [l for l in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if not l.strip().lower().startswith(("playwright", "pytest"))]
    if target == "functions":
        lines.append("azure-functions>=1.18")
    return "\n".join(lines) + "\n"


def package(target="functions"):
    path = Path(tempfile.gettempdir()) / f"autorfq-{target}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("requirements.txt", cloud_requirements(target))
        for name in FUNCTION_FILES if target == "functions" else []:
            z.write(ROOT / name, name)
        for name in INCLUDE:
            src = ROOT / name
            files = [src] if src.is_file() else [p for p in src.rglob("*") if p.is_file()]
            for f in files:
                if not SKIP_PARTS & set(f.relative_to(ROOT).parts):
                    z.write(f, f.relative_to(ROOT).as_posix())
        for f in (ROOT / "web" / "dist").rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(ROOT).as_posix())
    print(f"package: {path} ({path.stat().st_size // 1024} KB)")
    return path


def read_env():
    values = {}
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["functions", "webapp"], default="functions")
    ap.add_argument("--name", default="", help="app name (globally unique); default autorfq-<random>")
    ap.add_argument("--group", default="rg-autorfq")
    ap.add_argument("--location", default="centralindia")
    ap.add_argument("--plan", default="plan-autorfq")
    ap.add_argument("--sku", default="F1", help="F1 (free) or B1")
    ap.add_argument("--with-secrets", action="store_true", help="copy AZURE_OPENAI_* and BOT_* from .env")
    ap.add_argument("--rebuild-web", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="build and package only")
    args = ap.parse_args()

    build_web(args.rebuild_web)
    zip_path = package(args.target)
    if args.dry_run:
        return 0

    account = az("account", "show")
    print(f"subscription: {account['name']} ({account['user']['name']})")
    state_file = ROOT / ".azure-app.json"
    saved = json.loads(state_file.read_text()) if state_file.exists() else {}
    name = args.name or saved.get("name") or f"autorfq-{os.urandom(3).hex()}"

    if not az("group", "exists", "-n", args.group):
        az("group", "create", "-n", args.group, "-l", args.location)
    settings = {"SCM_DO_BUILD_DURING_DEPLOYMENT": "true", "RFQ_MODE": "no-browser", "RFQ_AUTO_BROWSER": "0"}
    if args.with_secrets:
        env = read_env()
        settings.update({k: env[k] for k in SECRET_KEYS if env.get(k)})

    if args.target == "functions":
        storage = ("st" + "".join(ch for ch in name if ch.isalnum()))[:24].lower()
        if az("storage", "account", "show", "-g", args.group, "-n", storage, check=False) in (None, ""):
            az("storage", "account", "create", "-g", args.group, "-n", storage, "-l", args.location,
               "--sku", "Standard_LRS", "--allow-blob-public-access", "false")
        if az("functionapp", "show", "-g", args.group, "-n", name, check=False) in (None, ""):
            az("functionapp", "create", "-g", args.group, "-n", name, "--storage-account", storage,
               "--consumption-plan-location", args.location, "--runtime", "python", "--runtime-version", "3.12",
               "--functions-version", "4", "--os-type", "linux")
        state_file.write_text(json.dumps({"name": name, "group": args.group, "target": "functions"}), encoding="utf-8")
        settings.update({"RFQ_OUT_DIR": "/tmp/autorfq", "ENABLE_ORYX_BUILD": "true"})
        az("functionapp", "config", "appsettings", "set", "-g", args.group, "-n", name, "--settings",
           *[f"{k}={v}" for k, v in settings.items()])
        print("deploying (remote build installs requirements.txt; a few minutes) ...")
        az("functionapp", "deployment", "source", "config-zip", "-g", args.group, "-n", name,
           "--src", str(zip_path), "--build-remote", "true", "--timeout", "900")
    else:
        if az("appservice", "plan", "show", "-g", args.group, "-n", args.plan, check=False) in (None, ""):
            az("appservice", "plan", "create", "-g", args.group, "-n", args.plan, "--is-linux", "--sku", args.sku,
               "-l", args.location)
        if az("webapp", "show", "-g", args.group, "-n", name, check=False) in (None, ""):
            az("webapp", "create", "-g", args.group, "-p", args.plan, "-n", name, "--runtime", "PYTHON:3.12")
        state_file.write_text(json.dumps({"name": name, "group": args.group, "target": "webapp"}), encoding="utf-8")
        settings.update({"RFQ_OUT_DIR": "/home/data/out", "WEBSITES_CONTAINER_START_TIME_LIMIT": "600"})
        az("webapp", "config", "appsettings", "set", "-g", args.group, "-n", name, "--settings",
           *[f"{k}={v}" for k, v in settings.items()])
        az("webapp", "config", "set", "-g", args.group, "-n", name, "--startup-file", STARTUP)
        print("deploying (Oryx installs requirements.txt; this takes a few minutes) ...")
        az("webapp", "deploy", "-g", args.group, "-n", name, "--src-path", str(zip_path), "--type", "zip",
           "--track-status", "false")

    url = f"https://{name}.azurewebsites.net"
    print(f"waiting for {url} ...")
    for _ in range(60):
        try:
            health = get(f"{url}/api/health", timeout=20)
            print("health:", health)
            break
        except Exception:
            time.sleep(10)
    else:
        sys.exit(f"{url} did not come up; see: az webapp log tail -g {args.group} -n {name}")
    check = get(f"{url}/api/selfcheck", data=b"", timeout=180)
    print(f"self-check on the live link: ok={check.get('ok')} rows={check.get('rows')} sources={check.get('sources')}")
    print(f"\nLive: {url}   upload page: {url}/rfq   dashboard: {url}/")
    return 0 if check.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
