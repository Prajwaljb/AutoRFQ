# AutoRFQ: Ferguson RFQ emails in, filled RFQ out

A sourcing manager gets RFQ emails that list product IDs: in the body, in an Excel attachment, mixed with
competitor part numbers, or buried in a forwarded thread. Copying each product's specs into the RFQ
template by hand takes hours. AutoRFQ reads the email, looks every item up, fills
`templates/rfq_template.xlsx` with a source for every value, checks the result, and replies in the same
email thread, usually in under a minute.

- **Base flow (no AI):** same email in, same Excel out. Email 1 matches `reference/email-1 reference output.xlsx`
  cell for cell, including all 105 Sources rows.
- **RFQ Quality Agent:** standardises units, flags missing or odd values, adds a Summary sheet, and holds
  doubtful RFQs for a person to approve. AI (Azure OpenAI) only adds advisory suggestions.
- **Web app:** runs, live progress, item cards with sources, keyboard review, approve & send.
- **Email bot:** answers RFQ emails in a Gmail inbox.

Spec: [`spec.md`](spec.md) · Plan: [`PLAN.md`](PLAN.md) · Features and diagrams: [`document.md`](document.md)

## Architecture

```mermaid
flowchart LR
    Gmail["Gmail inbox"] --> Bot["mailbot.py"]
    UI["React web app"] --> API["FastAPI app/"]
    Bot -->|subprocess| Build["rfq/build.py"]
    API -->|subprocess| Build
    Build --> Extract["extract: body, HTML,<br/>attachments, forwards"]
    Extract --> Lookup["look up: ferguson.com (Chrome CDP)<br/>→ spec sheet PDF → catalog"]
    Lookup --> Fill["fill RFQ + Sources + Notes"]
    Fill --> Quality["Quality Agent: units, rule flags,<br/>AI suggestions, Summary"]
    Quality --> Out["RFQ.xlsx · reply.eml · run.json"]
    Out -->|ready| Send["reply in thread"]
    Out -->|needs review| Review["review in web app"] --> Send
```

| Folder | What it is |
|---|---|
| `rfq/` | The core library. Stages: `extract/`, `sources/` (live, spec sheet, catalog, merge), `quality/`, `output/`, `review/`, `infra/` |
| `app/` | FastAPI: JSON API, SSE progress, approve & send; serves `web/dist` |
| `web/` | React + Vite + TypeScript + Tailwind, Ferguson palette, dark/light |
| `mailbot.py` | Gmail loop: replies, holds RFQs that need review, never loops on a bad email |
| `tests/` | 90 offline tests (pytest) + vitest |
| `data/spec_cache/` | Bundled spec sheet PDFs, the fallback when a download fails |

## Run it

Python 3.10+ and Node 20+. Commands for Linux/macOS; on Windows use `.venv\Scripts\python` and `py -3`.

```bash
python -m venv .venv            # Windows: py -3 -m venv .venv
.venv/bin/pip install -r requirements.txt
(cd web && npm ci && npm run build)
```

**One email:**

```bash
.venv/bin/python rfq/build.py emails/email-1-ids-in-body.eml --out out            # live: opens Chrome, closes it after
.venv/bin/python rfq/build.py emails/email-1-ids-in-body.eml --out out --offline  # catalog only, repeatable
```

This writes `out/<email name>/RFQ.xlsx`, `reply.eml`, `run.json` and `run.log`.

| Mode | Option | Sources used |
|---|---|---|
| Live | (default) | ferguson.com through a visible Chrome window (opened and closed for you; `--keep-browser` keeps it), then spec sheets, then the catalog |
| No browser | `--no-browser` | spec sheet PDFs (bundled copies if a download fails) and the catalog. Used on Azure |
| Offline | `--offline` | catalog only, no network. The tests and the reference use this |
| Replay | `--replay` | pages and PDFs cached by an earlier run, with no network |

**Web app:** `.venv/bin/python -m uvicorn app.main:app --port 8000`, then open http://127.0.0.1:8000.

**Settings (`.env`):** copy `.env.example` to `.env` in the repo root and fill in what you use. `.env` is
git-ignored. One loader (`rfq/infra/env.py`) feeds it to `build.py`, `mailbot.py` and the web app, and the
Diagnostics page shows which keys are set (never their values).

| Key | For |
|---|---|
| `BOT_EMAIL`, `BOT_PASSWORD` | the team Gmail and its 16-letter **App Password** (Google Account → Security → 2-Step Verification → App passwords). Used by `mailbot.py` and by Approve & send |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | the quality agent's LLM check (or `AZURE_OPENAI_ENDPOINT` / `_API_KEY` / `_DEPLOYMENT`) |
| `REVIEW_NOTIFY_EMAIL`, `DASHBOARD_URL` | optional "needs review" notice and its link |
| `SERPAPI_API_KEY` | optional web search for competitor codes with no description |

**Email bot:** with the mail keys set, run `.venv/bin/python mailbot.py`. It answers unread emails from today
with "RFQ" in the subject, sent from another address, in the same thread. RFQs that need review wait in the
dashboard until someone clicks Approve & send.

**Upload page:** http://127.0.0.1:8000/rfq (the same page runs on Azure).

**Checks:**

```bash
.venv/bin/python -m pytest                                    # 90 offline tests
.venv/bin/python .claude/skills/rfq-verify/check.py --build   # spec.md "Done when"
(cd web && npm test)
```

## Deploy to Azure

```bash
az login
.venv/bin/python scripts/deploy_azure.py --with-secrets
```

The script creates an **Azure Function App** (Python 3.12, Linux, consumption plan), as on Day 3:
- **`function_app.py`** wraps the FastAPI app, and **`host.json`** sets `routePrefix: ""`, so `/rfq`, `/`
  and `/api` keep their paths.
- **Settings:** `RFQ_MODE=no-browser` (there's no browser in the cloud) and `RFQ_OUT_DIR=/tmp/autorfq` (only
  /tmp is writable). `--with-secrets` copies the keys from `.env` into the app settings.
- **Requirements:** the zip leaves playwright out.
- **Check:** after deploying, it runs the email-1 self-check against the live URL.

`--target webapp` uses App Service instead. If you see AADSTS50076/50079, sign in at portal.azure.com, set up
the Authenticator app, then run `az logout` and `az login`.

**What runs where:** the email bot runs on a laptop, since it needs Gmail and, for live pages, Chrome. The
upload page and dashboard run on Azure.

Live link: _added after the first deploy_.

## Limits

- **ferguson.com blocks headless and scripted browsers.** Live mode needs a visible Chrome window on the
  machine, so the cloud deployment uses spec sheets and the catalog instead.
- **Catalog prices date from 24 Sep 2026.** The reply labels them as list prices from that date.
- **Spec sheet reading is pattern based** (Thickness, ASTM, OSHA, Material). It only fills blank cells, and
  every disagreement goes to the Notes sheet.
- **Code vs model.** Units, blanks, placeholders, ranges, wrong units and description/application
  contradictions are plain code. The LLM only looks for what code can't see. Its flags are advisory: it sees
  product data only, never the email, and never changes a value or the status.
- **No user accounts.** The reviewer name is stored in the browser.
- **The brand colours are provisional.** They come from Ferguson Brand Connect's public theme; the
  guideline pages need a login.
