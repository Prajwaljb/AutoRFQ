"""Loads the repo's .env file into the environment, once, for every entry point.

build.py, mailbot.py and the web app all read their settings from the environment. Locally those come from
.env (git-ignored; .env.example is the template); on Azure the same names are App settings. A value already
set in the environment wins over .env.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

# Names the app knows about, for the Diagnostics page (which shows whether each is set, never the value).
KNOWN = {
    "mail": ["BOT_EMAIL", "BOT_PASSWORD", "REVIEW_NOTIFY_EMAIL", "DASHBOARD_URL"],
    "ai": ["OPENAI_API_KEY", "OPENAI_MODEL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
           "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION"],
    "search": ["SERPAPI_API_KEY"],
    "run": ["RFQ_MODE", "RFQ_OUT_DIR", "RFQ_CDP", "RFQ_AUTO_BROWSER", "RFQ_SPEC_DOWNLOAD", "RFQ_PRODUCTS_DB",
            "RFQ_DB_TTL_HOURS", "ADMIN_TOKEN"],
}
SECRET = {"BOT_PASSWORD", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "SERPAPI_API_KEY", "ADMIN_TOKEN"}

_loaded = False
_from_file = {}  # names this module set from .env (and their values), so reload() can update them


def parse(text):
    """KEY=value lines; # comments and blank lines are skipped, quotes around values are removed."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


def load(path=ENV_FILE):
    """Reads .env into os.environ (without overriding what is already set). Safe to call many times."""
    global _loaded
    if _loaded and path == ENV_FILE:
        return
    try:
        values = parse(Path(path).read_text(encoding="utf-8-sig"))
    except OSError:
        values = {}
    for key, value in values.items():
        if value != "" and key not in os.environ:
            os.environ[key] = value
            _from_file[key] = value
    if path == ENV_FILE:
        _loaded = True


def reload(path=ENV_FILE):
    """Re-reads .env so edits apply without a restart. Values set outside .env (shell, Azure) still win."""
    try:
        values = parse(Path(path).read_text(encoding="utf-8-sig"))
    except OSError:
        values = {}
    for key in list(_from_file):  # removed or emptied in .env
        if not values.get(key) and os.environ.get(key) == _from_file[key]:
            os.environ.pop(key, None)
            _from_file.pop(key)
    for key, value in values.items():
        if not value:
            continue
        if key not in os.environ or os.environ.get(key) == _from_file.get(key):
            os.environ[key] = value
            _from_file[key] = value


def status():
    """{group: {NAME: True/False}}: which settings have a value. Never returns a value."""
    return {group: {name: bool(os.environ.get(name, "").strip()) for name in names}
            for group, names in KNOWN.items()}
