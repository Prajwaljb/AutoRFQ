# Plan: Ferguson RFQ flow (Part A base + Part B Quality Agent + Azure)

## Context
Source material: the presentation deck in `image_conxt/`, README.md and data/README.md. Ferguson gets RFQ request
emails listing product IDs (in the body, in an Excel attachment, mixed with competitor parts, or buried in a
messy forward). We build:
- **Part A, the base (no AI):** email → find IDs → look each up (live ferguson.com via a real Chrome over CDP,
  spec-sheet PDF, backup catalog as fallback) → fill `templates/rfq_template.xlsx` (one row per ID, a
  Sources row for every value, `Not found` for unknown IDs) → write reply. Same email in, same Excel out.
- **Part B, the agentic arm:** an **RFQ Quality Agent** (Azure OpenAI) that normalises units, flags
  missing/odd values, adds a Summary sheet with the fill rate, and holds the RFQ for human review when needed.
- **Deploy** base + arm on **Azure** (no browser there: catalog + spec PDFs only).

Process decision: a short hand-written **`spec.md`** in the kit root, as the deck asks (Part A step 2). No spec-kit.

**Hackathon goal: a product that feels finished, without risking correctness.** The base stays
deterministic and matches the reference exactly. On top of it: a calm, modern dashboard and review UI, a
clean customer reply, a styled Excel, and a human-in-the-loop gate. Usefulness beats effects: no gimmick
animations, no emoji badges, nothing the customer or reviewer has to decode.

### Progress so far (re-checked on disk 2026-10-16)
- **Build order steps 0-2 done (2026-10-16):**
  - **Step 0:** `check.py --build` in the `rfq-verify` skill, and CI (`.github/workflows/ci.yml`).
  - **Step 1, the offline base:** `rfq/` with `config`, `models`, `infra/`, `extract/`, `sources/catalog`,
    `output/workbook` + `reply`, `pipeline` and `build.py`.
  - **Step 2:** the `mailbot.py` patch (follow-up reply, always `\Seen`, hold gate, `run.json` status).
  - **Checks:** 48 offline tests pass on Python 3.14 and 3.11. Email 1 equals the reference, including the
    105 Sources rows in order.
  - **Small changes from the design:**
    - the email reader is `rfq/extract/mail.py`, so the name doesn't shadow the stdlib `email`;
    - the template's "How to fill" sheet is dropped, because the reference has only RFQ / Sources /
      Notes.
- **Part A finished (2026-10-16):**
  - **Live lookup (`rfq/sources/ferguson_live.py`):** checked against the real site through a visible
    Chromium (ferguson.com blocks headless browsers).
    - All 4 emails were built live.
    - Email 1 live equals the reference: 0 differing cells.
    - `225123` is Found live.
  - **Spec sheets:** `spec_sheet.py`, with 39 links stored as 8 unique PDFs in `data/spec_cache/` (16 MB),
    downloaded by `scripts/fetch_specs.py`.
  - **Merge rules (`merge.py`):** a bare number carries its column's standard unit; ", " lists are stored
    as "|"; spec-sheet Material wording never counts as a conflict.
  - **Other pieces:** `rfq/chrome.py` launcher, `--replay` from the page cache, and Excel styling
    (`style.py`).
  - **Tests:** 66 offline tests (Python 3.14 + 3.11). Tests set `RFQ_SPEC_DOWNLOAD=0`, so they read the
    bundled PDFs and never download.
- **Open question:** `9677533` is listed on ferguson.com again. In live mode it is Found, but the `rfq-verify`
  checker expects Not found for it in `--live` too (the spec only requires that offline).
- **Part B, web app and deploy script built (2026-10-16):**
  - **Quality Agent:** `rfq/quality/` (units, rules, advisory LLM, Summary) and `rfq/review/state.py`.
  - **Web:** `app/` (FastAPI) and `web/` (React + Vite + TS + Tailwind; shadcn-style components written by
    hand on the brand tokens).
  - **Deploy:** `scripts/deploy_azure.py`.
  - **Chrome:** live runs open the scraping window and close it when done (`--keep-browser` keeps it).
  - **Checks:** 90 pytest + 4 vitest. A Playwright run of the UI went through upload, a live email 2
    build, held for review, keyboard review, approve, and the self-check.
- **Blocked on the user:**
  - Azure needs an MFA sign-in (`az login`) before `scripts/deploy_azure.py` can create the App Service;
  - a real Gmail test needs `BOT_EMAIL` / `BOT_PASSWORD` in `.env`.
- **Cleanup done (2026-10-16):** the spec-kit artifacts `specs/001-rfq-flow/` and `.specify/feature.json`
  are deleted ("No spec-kit" above). The root `spec.md` is the spec.
- **spec.md reviewed and updated (2026-10-15):** IDs are 5-7 digits; product_id, Description and Lookup
  Status have no Sources rows (as in the reference); the LLM only adds flags; "Done when" is per mode
  (offline vs live); the output sheets are spelled out. Checked: the Sources rule in the spec rebuilds all
  105 reference Sources rows in exact order.
- **Project skills:** `rfq-run` (start Chrome / build / mailbot / web app) and `rfq-verify` (acceptance
  checks from the spec) in `.claude/skills/`.
- **Hardening revision (2026-10-16):** added "Cross-platform: Linux + Windows" and "Failure handling".
  Decisions from the user:
  - patch mailbot.py **and** make build.py exit 0 whenever it wrote a reply;
  - Windows is a demo + dev machine (launcher, Windows CI).
- **Determinism + UX + structure revision (2026-10-16).** Decisions from the user:
  - **AI scope:** LLM flags are advisory only; status, highlights and reply wording come from rule flags.
  - **Determinism fixes adopted:** stable ordering, bundled spec PDFs as a download fallback, and no
    timings in output files. Byte-identical files are not required: the deck compares values.
  - **Hold gate:** "Needs review" RFQs are held until a person approves them. Ready RFQs are sent
    automatically.
  - **Frontend:** React + Vite + TypeScript + shadcn/ui; dark theme by default with a light toggle.
  - **Brand (2026-10-16):** the UI, Excel and reply follow Ferguson's design language. The palette is
    navy `#00446a` and accent `#00a0dd`, and the font is Inter. These values are provisional; see "Design
    rules".
  - **Structure:** a layered layout (core library / API / web) that can take new sources and pages
    without reshuffling.
- **Deck check (2026-10-16):** all 12 slides in `image_conxt/` were compared with this plan, and they
  match. Three deviations were decided on purpose by the user:
  - the layered structure is kept, even though the deck says "a few files";
  - the hold gate is kept (Ready RFQs are still sent with no manual steps);
  - the reply keeps the deck's counts and "Quality check" line, reworded for a buyer (see "Customer
    experience").
- **Re-confirmed:** the reference output's RFQ values equal `data/product_catalog.json` for all 6 email-1
  IDs (no differences). The reference Notes sheet is empty, apart from its header.

### Facts established during exploration
- **The deck's bar:** "The base needs no AI: same email in, same Excel out, every time." The test slide
  checks it by **values** ("open your output next to the reference… the values should match"). The sample
  reply in the deck shows counts only ("Products found: 3 … Quality check: 7 cells flagged, 0 units
  converted … Every filled value is listed with its source on the Sources sheet"), no timings.
- `mailbot.py` (from the kit) runs `python rfq/build.py <eml> --out out [extra args]`.
  - **Outputs:** it expects `out/<eml stem>/RFQ.xlsx`. It uses `out/<eml stem>/reply.eml` if present (it
    rewrites the headers itself), otherwise it sends a plain reply with RFQ.xlsx attached.
  - **Other behaviour:** it passes through extra flags such as `--offline`. `make_reply(original, folder)`
    builds the in-thread reply and is reused for approved held RFQs.
  - **Poison-email bug:** if build.py exits non-zero or runs past its 900 s timeout, the exception escapes
    `check_inbox()` before `STORE \Seen`. The email stays unread and is retried every 30 s forever, gets no
    reply, and blocks every RFQ email after it in the same search. **Decision:** fix it in both places (see
    "Failure handling").
- `reference/email-1 reference output.xlsx` can be rebuilt **exactly from `data/product_catalog.json`**:
  - **RFQ values:** every value equals the catalog value, with the `Picture` column = catalog `Picture URL`.
  - **Cell format:** all cells are strings (inlineStr, e.g. `No of Tools` = `"1"`).
  - **Image column:** `Image` is the formula `=IMAGE("<picture url>")`.
  - **Sources sheet:** the catalog rows from `product_catalog_sources.csv` for each filled RFQ column, in
    template column order, plus `Image` and `Picture` rows that copy the `Picture URL` source row. There is
    **no** Description source row (the CSV has none).
  - **Extra sheet:** the reference adds a **Notes** sheet (`product_id | note`), which the template lacks.
- **Catalog coverage:** email-1 IDs are all in the catalog. Email 2 has `225123` missing from the catalog
  (back live on ferguson.com, so found live and Not found offline). Email 4 has `9677533` missing. Email 3 has
  competitor parts `17783-79-3000`, `31-024`, `MTX-4409-XQ`, and email 4 has `17774-79-3000`; all must
  appear as `Not found`.
- **Spec sheets:** `data/spec_sheet_links.csv` has 39 links, all on `api.ferguson.com`, which may block
  scripts the way the site does. Hence the bundled fallback copies.
- **Local machine:** Linux, Python 3.14, `uv`, `chromium` and `az` are installed.
- **Windows is a first-class target** (decision): teammates develop on Windows and run the live demo there
  (Chrome window, mailbot, dashboard). The deck's commands are Windows PowerShell. See "Cross-platform".
- **Data quirks that affect error handling:**
  - 5 products have Product details `[]` (a placeholder, with a Sources row).
  - Product details and Brand contain non-ASCII text, so every file read needs an explicit encoding.
  - The CSVs start with a UTF-8 BOM (`utf-8-sig`).
  - 17 products have bare Length/Width numbers.
  - No catalog value starts with `=`.

## Project structure
The core library knows nothing about the web. The CLI entry points keep the paths that `mailbot.py` and the
deck use. New sources (e.g. a SerpApi competitor finder), checks or pages each add one file in the right
folder without touching the others.
```
rfq/                          # core: email -> RunResult -> files. No web imports.
  __init__.py
  build.py                    # CLI shim, fixed contract: python rfq/build.py <eml> --out DIR
                              #   [--offline] [--no-browser] [--no-quality] [--cdp URL] [--replay]
  chrome.py                   # CLI shim -> infra/chrome.py (python rfq/chrome.py)
  config.py                   # ROOT, modes, limits, template column order, unit standards: one place
  models.py                   # dataclasses: Item, Cell(value, source), Note, Flag, RunResult, RunStatus
  pipeline.py                 # run(eml, out, mode, on_event) -> RunResult; fixed stage order
  extract/    email.py        # MIME walk, text/HTML parts, attached emails
              attachments.py  # xlsx/xlsm/csv readers with limits
              patterns.py     # ID + competitor-code regexes, context filters (phone, PO, qty, ...)
  sources/    base.py         # Source protocol: lookup(item) -> {column: Cell}
              catalog.py      # product_catalog.json + product_catalog_sources.csv
              ferguson_live.py  # Playwright over CDP, page cache/replay, screenshots
              spec_sheet.py   # download -> bundled copy -> skip; pypdf text + regexes + snippets
              merge.py        # live wins; differences -> Notes; spec fills blanks only
  quality/    units.py, rules.py, llm.py, summary.py
  output/     workbook.py     # RFQ, Sources, Notes, Summary sheets (values)
              style.py        # formatting only, never changes a value
              reply.py        # customer reply (HTML + text) and internal review notice
              templates/      # reply.html, reply.txt, review_notice.txt
  review/     state.py        # review.json: load, apply a decision, finalise -> regenerate outputs
  infra/      io.py           # utf-8 IO, safe_cell(), atomic save + lock retry, safe folder names
              log.py, events.py, chrome.py
app/                          # FastAPI: JSON API + serves web/dist
  main.py, schemas.py         # schemas mirror rfq/models.py
  routes/     runs.py, review.py, health.py, samples.py
  services/   runner.py       # build.py as a subprocess, tails events.jsonl, one live run at a time
              mailer.py       # approve & send: reuses mailbot.make_reply + the saved original email
web/                          # React + Vite + TypeScript + Tailwind + shadcn/ui
  src/pages/       RunsPage, RunPage, ReviewPage, NewRunPage, DiagnosticsPage
  src/components/  ui/ (shadcn), ItemCard, StatusBadge, SourceBadge, SourceSheet, EmailView,
                   PipelineSteps, KpiStrip, HealthBar, EmptyState
  src/lib/         api.ts (typed client), sse.ts, sort.ts, format.ts
  e2e/             Playwright tests of the review flow
scripts/          fetch_specs.py  # one-off: download the 39 spec PDFs into data/spec_cache/
data/spec_cache/  bundled spec PDFs (committed)
tests/
  unit/           test_extract, test_sources, test_quality, test_review_state
  integration/    test_reference, test_failures, test_determinism, test_hold_flow
  fixtures/       small broken .eml files built by the tests (no real customer data)
.github/workflows/ci.yml      # pytest on ubuntu-latest + windows-latest; Node job for web/
mailbot.py                    # (existing) small patch, see "Failure handling" and "Hold gate"
out/<run>/                    # RFQ.xlsx, reply.eml, run.log, events.jsonl, run.json, review.json
```
- **One data model.** `rfq/models.py` is shared by every stage, by `run.json` and by the API
  (`app/schemas.py` mirrors it), so the same words mean the same things everywhere.
- **Pipeline events** (`rfq/infra/events.py`): each stage reports progress as an in-process callback (used
  by the web app) and as lines in `out/<run>/events.jsonl` (so mailbot runs show up live too). Events:
  `email_read`, `item_found`, `lookup_start` / `lookup_done` (source + screenshot path), `spec_pdf_read`,
  `quality_flag`, `excel_saved`, `reply_saved`, `run_done` (status). They drive the stepper on the Run
  page.
- **Run status lifecycle** (one enum, `RunStatus`):
  - `processing -> ready -> sent`
  - `processing -> needs_review -> approved -> sent`
  - `failed -> fallback_sent`
- **Build artifacts:** `web/dist` is git-ignored and built by CI and the deploy. Teammates who don't work on
  the UI run `npm ci && npm run build` in `web/` once.
- **Secrets:** `.env` (git-ignored) holds `BOT_EMAIL`, `BOT_PASSWORD`, `AZURE_OPENAI_ENDPOINT`,
  `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, optional `REVIEW_NOTIFY_EMAIL` and `DASHBOARD_URL`.
- **requirements.txt:** openpyxl, playwright, pypdf, openai, fastapi, uvicorn, python-multipart, pytest.

## Determinism
"Same email in, same Excel out" is a rule, enforced by these points:

| Rule | Detail |
|---|---|
| LLM is advisory | Status, cell highlights and the reply wording come from **rule flags only**. LLM flags go to an "AI suggestions" table on the Summary sheet and in the review UI. They never change a value or the status |
| Stable order | Lookups from parallel tabs are collected, then written in item (email) order. Notes are sorted by (item index, stage: extract → lookup → spec → quality). Ties in "did you mean" and alternative suggestions are sorted by product_id |
| Spec PDFs | Download first. If that fails, use the bundled copy in `data/spec_cache/` (Sources keep `spec_sheet` + the URL; a Note says "read from bundled copy"). Only if both fail, skip with a Note |
| No timings in outputs | Stage timings and "time saved" appear only on the dashboard, in the console and in `run.log`, never in RFQ.xlsx or the reply |
| Byte-identical files | Not required (the deck compares values). openpyxl timestamps and MIME boundaries may differ; the tests compare cell values |
| Human edits | The only change allowed after the build. Recorded as a Sources row `human_review`, high, with reviewer and time |

**Guarantee per mode:**
- `--offline`: fully repeatable.
- `--no-browser`: repeatable, thanks to the bundled PDFs.
- Live: repeatable apart from the live site's own data. The live time budget and the "3 blocks in a row"
  cut-off only act in live mode, and each writes a Note.

## Part A: the base (build in this order, run after each step, commit when it works)

**1. `spec.md`.** Follow the deck skeleton, plus a `## Run` line: `python rfq/build.py <email.eml> --out out`
writes `out/<email name>/RFQ.xlsx` and `reply.eml`.

**2. `rfq/extract/`: read the email** (stdlib `email` + openpyxl for `.xlsx` attachments).
- **Text sources:** all `text/plain` parts (fall back to stripped HTML), then each xlsx attachment: use the
  column whose header matches `item|product|sku|part|id`, otherwise any cell matching the ID pattern.
- **Ferguson IDs:** `(?<![\w-])#?(\d{5,7})(?![\w-])` (5 digits too: the catalog has `91882`, `91930`). This
  handles `#5106926` and `1844552 , 4783795`, and ignores `x 40 rolls`, `3 inch` and the digit groups
  inside hyphenated parts.
- **Competitor / unknown codes:** a hyphenated alphanumeric token with ≥4 digits
  (`[A-Z0-9]+(?:-[A-Z0-9]+)+`), excluding dates. This catches `17783-79-3000`, `31-024` and `MTX-4409-XQ`.
  Kept as items so they appear as `Not found`.
- **Order and duplicates:** keep the order of first appearance and drop repeats. Write a Notes entry for
  duplicates ("listed twice, kept once") and for competitor items ("competitor part number, brand: Mutual").
- **Checked:** these regexes were run on the four sample emails during planning and gave exactly the lists
  below. Email 2's attachment header is "Item number", which the header rule matches. Make the competitor
  pattern case-insensitive so lowercase codes are caught too.
- **Expected lists** (become tests):
  - **e1:** the 6 IDs.
  - **e2:** the 8 attachment IDs.
  - **e3:** `5106878, 5106907, 4570880, 9677531, 17783-79-3000, 31-024, MTX-4409-XQ`.
  - **e4:** `5106926, 8067331, 1844552, 4783795, 5106888, 9677533, 17774-79-3000`.

**3. `rfq/sources/`: look up each item.** Each source returns `{column: Cell(value, source_type,
confidence, source)}`.
- **Catalog (`catalog.py`):** `data/product_catalog.json` + `product_catalog_sources.csv` (carry their
  source rows over as-is).
- **Live (`ferguson_live.py`):** Playwright `connect_over_cdp("http://127.0.0.1:9333")`, using the open
  Chrome window from the deck.
  - **Address:** the default is `127.0.0.1`, not `localhost`. On Windows `localhost` can resolve to IPv6 `::1`
    while Chrome listens on IPv4 only.
  - **Tabs:** open our own new tab(s) and close them at the end. Never close the user's tabs or the browser.
  - **Right product:** the page must show `Item #<id>`. A redirect to another product or a search page counts
    as "not on the live site", not as Found.
  - **Finding the page:** open the catalog `Ferguson URL` if known, otherwise ferguson.com search for the ID.
  - **Reading values:** read title, specs table, price and stock. Map Ferguson attribute labels to template
    columns (e.g. "Number of Tools Included" → `No of Tools`).
  - **Sources:** `ferguson_page`, high, URL + date.
  - **Failures:** timeout or block → catalog fallback and keep going.
  - **Pacing:** a short delay between pages. Up to 3 tabs in parallel; results are re-sorted into item order.
- **Merge rule (`merge.py`, from the deck):** live wins; any live/catalog difference goes to the Notes sheet.
- **Spec sheet PDF (`spec_sheet.py`):**
  - **Getting the file:** the URL comes from `spec_sheet_links.csv`. Download it with urllib and cache it
    in `out/.cache/`. If the download fails, use the bundled copy in `data/spec_cache/`.
  - **Reading it:** text with pypdf, then regexes for Thickness (mil), ASTM D-xxxx, OSHA and Material. Keep
    the page number and the text snippet for each value.
  - **Only fills blank cells.** It never overwrites. Source `spec_sheet`, medium, with the PDF URL.
  - **Disagreements** → Notes.
- **Modes:**
  - `--offline`: catalog only, no network. Used by tests; reproduces the reference.
  - `--no-browser`: catalog + spec PDFs. Used on Azure.
  - Default: live + PDF + catalog fallback.
- **Not found:** in no source → `Lookup Status = Not found`, all spec cells blank, plus a Notes row with the
  reason (competitor part, not in catalog or on ferguson.com).

**4. `rfq/output/workbook.py`: fill the RFQ.**
- **Template:** load it with openpyxl.
- **RFQ sheet:** row per item in order, string values. `Image` = `=IMAGE("url")`, `Picture` = URL.
  `Lookup Status` = Found / Not found.
- **Sources sheet:** one row per filled cell (template column order; Image/Picture reuse the picture source).
- **Notes sheet:** create it if missing.
- **Output:** save to `out/<eml stem>/RFQ.xlsx` (atomic save, see "Cross-platform").

**5. `rfq/output/reply.py` + `rfq/pipeline.py` + `rfq/build.py`.**
- **reply.eml:** see "Customer experience".
- **run.json:** run metadata (sender, subject, received, mode, counts) and the `RunStatus`. mailbot and the
  web app read it.
- **build.py:** a thin CLI around `pipeline.run()`. It prints a one-line result (the deck shows "3 IDs, 3
  found (live page 3, catalog fallback 0)…").
  - **Exit codes:**
    - `0` whenever RFQ.xlsx and reply.eml were written, even with warnings (no items, bad attachment,
      browser down, LLM failed).
    - `2` for a usage error (missing or unreadable .eml path, bad flags).
    - `1` only when the kit itself is broken (template or catalog missing or corrupt) and no output could be
      written.
  - **Last-resort guard:** a top-level `try/except` writes `error.txt` (traceback) into the output folder. If
    the template can still be loaded, it also writes a minimal RFQ (every extracted item as `Not found`, plus
    a Note "processing error") and a reply saying "we hit a problem; a person will follow up".

**6. Email bot.**
- **Gmail setup:** App Password in `.env`.
- **Browser:** `python rfq/chrome.py` on any OS (see "Cross-platform"). The manual equivalents are:
  - **Windows (deck):** `& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9333 --user-data-dir="$env:TEMP\chrome-rfq" https://www.ferguson.com/`
  - **Linux:** `chromium --remote-debugging-port=9333 --user-data-dir=/tmp/chrome-rfq https://www.ferguson.com/`
- **Run:** `python mailbot.py` from the venv (it uses `sys.executable`), then send a test email with "RFQ" in
  the subject.
- **Hold gate:** see "Hold gate" below.

## Part B: RFQ Quality Agent (`rfq/quality/`, runs inside the pipeline unless `--no-quality`)
Revised 2026-10-16 from the agent slides in `image_conxt/agent/`. The deck's bar: "Catch the errors before a
factory does. A person still reviews every RFQ; the agent makes that review fast and focused." It runs
**after the Excel is filled, before the reply**: base → rules → LLM check → Summary sheet.

**Which checks are code and which need the model** (the deck scores knowing the difference; the Summary and the
web app label every flag "by code" or "by model"):

| Check | By | Why |
|---|---|---|
| Units to one standard (Length ft, Width in, Thickness mil, Weight lb) | code | a lookup table is enough |
| Blank cells (missing) | code | an empty cell is a fact |
| `[]` placeholders, non-numeric or out-of-range measurements | code | patterns and ranges |
| Wrong unit for a column ("300 in" Length when the description says 300 ft) | code | numbers compare exactly |
| Description vs Width / Length / Colour | code | the description carries those numbers |
| Application vs Lettering / colour (APWA: water blue, sewer green, gas yellow, electric red, telecom orange, reclaimed purple) | code | keyword + colour table |
| Anything else that looks odd or contradicts the rest of the row | model | needs reading, not matching |

1. **Units (`units.py`).** A bare number gets the unit (`"1000"` → `"1000 ft"`). An explicit other unit is
   converted (`"333.33 yds."` → `"1000 ft"`, rounded when within 0.1% of a whole number).
   - **Never a quiet fix:** a conversion is skipped, and flagged instead, when the result would contradict the
     description or fall outside the plausible range. `"300 in"` on a "6 in. x 300 ft." tape stays `"300 in"` and
     gets a high `wrong_unit` flag with the reason.
   - Every change keeps its Sources row (origin + "unit normalised by the quality agent") and gets a Note.
2. **Blanks (`rules.py`, `missing`).** Every empty spec cell on a Found row is a `missing` flag (severity
   `low`), counted per column and per product for the fill rate. Blank Description, Length or Width on a
   Found row is `high` (`missing_key_value`).
3. **Suspicious values (`rules.py`).** Placeholders, non-numeric values, out-of-range values, wrong units,
   description mismatches, and Application vs Lettering/colour (`application_mismatch`).
   - **Example:** email 1's 5106891 says Application "Water" while its Lettering says Sewer and the tape is green.
   - **Severity:** `high` only for values that are probably wrong (wrong unit, description mismatch on a
     measurement, missing key value): those hold the RFQ. A conflict between descriptive columns is `medium`,
     so email 1 stays `Ready`, and it is flagged and visible.
4. **LLM check (`llm.py`).** It asks only what code can't see. It runs once per found row, given the row's
   values (with the Description) and their sources, never the email.
   - **Output:** JSON `{column, issue, severity, quoted_value}`; a flag whose quoted value isn't exactly the
     cell's value is dropped.
   - **Provider:** OpenAI (`OPENAI_API_KEY`, `OPENAI_MODEL`; "the same key as Days 2 and 3") or Azure OpenAI
     (`AZURE_OPENAI_*`). There's a 30 s timeout, 2 retries and a 90 s total cap.
   - **Advisory:** model flags never change a value or the status.
   - **On failure:** units and blanks still run, and the Summary says "LLM check skipped: <reason>".
5. **Flag, never overwrite (`output/style.py`).** Flagged cells are coloured and get a comment with the reason
   and who flagged it. The value is left for a person.
   - **Colours:** grey for missing (code), amber for suspicious (code), orange for suspicious (model).
   - **When:** the marks are in every RFQ.xlsx, not only held ones. A resolved flag loses its mark when the
     approved file is rebuilt.
6. **Summary sheet (`summary.py`).**
   - **Overview:** products requested, found, found on the web (live), not found; spec cells filled X of Y;
     overall fill rate; flags by type (missing, unit, suspicious, not found); units converted; the LLM check line
     ("ran (gpt-…, N flags)" or "skipped: reason").
   - **Fill rate per column:** filled, found products, fill rate (found), fill rate (all requested).
   - **Fill rate per product:** filled of total spec cells, per found product.
   - **Every flag:** item, column, value, issue, rule, severity, by code/model, state.
   - **Also:** request lines with the estimated total, alerts, suggested alternatives, and the chart.
7. **Reply.** The buyer-worded quality line stays, and it now counts blanks too: "every value checked; N
   measurements standardised; N values worth a second look; N cells unknown (left blank). Details on the
   Summary sheet."
8. **Status.** `Needs human review` while any open high-severity **rule** flag remains; otherwise `Ready`.
   Model flags and low (missing) flags never hold an RFQ. The review page lists high and medium flags; missing
   cells are summarised, not listed one by one.

**Test with (the deck's list, also in `tests/`):**
- **Email 2 `--offline`:** bare `1000` becomes `1000 ft`, with many missing flags (weights, standards).
- **Email 2 live:** 1432040's Length "300 in" against "6 in. x 300 ft." is flagged `wrong_unit` and left
  unchanged, and the RFQ is held.
- **Email 3 with "333.33 yds.":** a unit test.
- **Email 1:** 5106891 gets an Application/Lettering flag and email 1 stays Ready, matching the reference.
- **By email:** the reply carries the quality line and the Summary sheet.

**Done when:**
- every length is in ft and every width in in, or flagged when that can't be done safely;
- each flag points to the exact cell with a reason;
- the Summary shows the correct fill rate per column and per product;
- email 2 uploaded to the Azure link comes back with the flags and the Summary.

## Hold gate (human in the loop)
- **Ready:** the reply is sent automatically. Part A stays "no manual steps".
- **Needs review:**
  - **What happens:** the customer gets nothing yet. The run waits in the review queue and the optional
    `REVIEW_NOTIFY_EMAIL` gets "RFQ from X needs review (3 flags)" with a link to the dashboard review page.
  - **After approval:** when a reviewer clicks **Approve & send**, `review/state.py` regenerates RFQ.xlsx
    and the reply without the review marks. `app/services/mailer.py` then sends exactly one reply in the
    same thread, using `mailbot.make_reply` and the saved original from `out/inbox/`.
- **Failure:** the "a person will follow up" reply (see "Failure handling").
- **mailbot.py patch:** after the build, read `run.json`. If the status is `needs_review`: don't send, log
  "Held for review: <DASHBOARD_URL>/runs/<id>", send the optional internal notice, and mark the email
  `\Seen` as always.

## Customer experience (the RFQ requester)
- **Reply email** (`rfq/output/templates/reply.html` + `reply.txt`; multipart/alternative, RFQ.xlsx
  attached), written for a buyer:
  - **Opening:** a greeting, then one summary line: "Your RFQ for 7 items is attached: 5 matched, 2 need
    your input."
  - **Item table:** in email order: #, Item, Description, Status, Unit price, Availability. Catalog prices
    say "list price as of 24 Sep 2026". Remote images use the ferg-img URLs.
  - **"Items we couldn't match":** each with its reason (competitor part, brand Mutual; not on
    ferguson.com) and one next step ("reply with the Ferguson item number"). A near-miss reads "Did you mean
    9677531?".
  - **Counts line** (as in the deck's sample reply, in buyer words): "Products found: 5 of 7. Not found: 2."
  - **Quality line** (the deck's "Quality check" line, in buyer words; built from rule flags only):
    - "Quality check: every value checked. 3 measurements converted to standard units (ft, in, mil, lb)."
    - If there are open low-severity flags, add: "2 values are worth a second look; they are listed on the
      Summary sheet." Otherwise add: "No issues found."
    - After a review: "Quality check: checked by our team."
  - **Closing:** "Every value's source is on the Sources sheet", then a signature.
  - **Never included:** internal words (flag, rule, severity), fill-rate %, review links, "AI", "DRAFT".
  - **Look:** the brand palette with inline CSS only.
    - A navy `#00446a` header bar with "Ferguson" in white text.
    - The table header in `brand-mist` with navy text.
    - Arial / Helvetica, because email clients don't load Inter.
- **Excel (`rfq/output/style.py`, formatting only):**
  - **RFQ sheet:** first, in the reference layout.
    - **Header:** navy `#00446a` with white bold text (see "Brand" under Design rules).
    - **Layout:** frozen header + ID column, autofilter, readable widths, wrapped long text, and row heights
      that make the `IMAGE()` thumbnails visible.
    - **Status:** the status cell has a colour **and** text. Not found rows are tinted `brand-mist`.
  - **Sources sheet:** a confidence colour scale (semantic colours) and clickable source URLs in navy.
  - **Summary sheet:** KPI cells (found, not found, fill rate, flags), a per-column fill-rate bar chart
    (openpyxl `BarChart`), the flags table and the AI suggestions table.
  - **Review marks:** yellow fill + comment on flagged cells exist only while an RFQ is held. The approved
    file is rebuilt without them. Auto-sent Ready files list their low-severity flags on the Summary only.

## Reviewer experience and frontend (`web/`, React + Vite + TypeScript + shadcn/ui)
**Shell:**
- **Top bar:** product name, a health bar (Chrome: Connected/Offline · AI review: On/Off · Inbox:
  Watching/Off), the theme toggle (dark by default, light available) and the primary **New RFQ** button.
- **Left nav:** Runs · New RFQ · Diagnostics.

**Runs page (home):**
- **Tabs with counts:** Needs review · Processing · Sent · Failed.
- **Sort:** Needs review first, oldest waiting first (showing an age like "waiting 2 h"), then the rest
  newest first.
- **Row:** customer, subject, received, items (found/total), flags, status badge. The dashboard also lists
  runs started by `mailbot.py` (it reads `out/*/run.json` + `events.jsonl`).
- Empty, loading (skeleton rows) and error states.

**Run page:**
- **Header:** customer, subject, status badge and **one** context-dependent primary action ("Review 3
  flags", "Approve & send", "Download RFQ.xlsx"). Secondary actions (download reply.eml, re-run, open
  folder) sit in a menu.
- **Tabs:**
  - **Items:** cards in email order, or a table toggle.
  - **Email:** the original email with the detected IDs highlighted; duplicates and competitor codes are
    marked with a label.
  - **Sources.**
  - **Activity:** pipeline steps, timings, "processed in 41 s" and the estimated manual time saved.
- **Item card:**
  - **Layout:** a fixed image area (placeholder if no image), the ID in monospace, the description clamped
    to 2 lines, a status badge, a source label (Live page / Spec sheet / Catalog), a price · stock line and
    a flag count.
  - **Not found card:** muted, with its reason and next step.
  - **Click:** opens a side sheet with every field and its source (type, confidence, link). Spec-sheet
    values also show the PDF page and text snippet.
- **While a run is processing:** a stepper (Read → Look up → Fill → Quality → Reply) driven by SSE events.
  Skeleton cards hold their final positions, so nothing jumps. In live mode a small "Browser" panel shows
  the current page thumbnail.

**Review page** (two panes):
- **Left pane:**
  - **Order:** flags grouped by item, high to low severity, then item order. Progress shows "3 of 7
    resolved".
  - **AI suggestions:** a separate collapsed group labelled "advisory".
- **Right pane:** the flagged value in context, the reason (rule name), the source evidence and the other
  fields of that product.
- **Actions:** **Keep value** · **Edit** · **Clear (unknown)**. An edit or a clear records a Sources row
  `human_review`, high, with reviewer + time.
- **Keyboard:** ↑/↓ to move, Enter to keep, E to edit, Del to clear, Ctrl+Z to undo the last decision.
- **Sticky footer:** **Preview customer email** (the exact email and attachment name) and **Approve &
  send**. Approve & send is disabled until every high-severity flag is resolved, and the button says why.
  Sending asks for confirmation. Afterwards a toast appears and the status changes to Sent.
- **Reviewer name:** asked once and stored locally (no auth for the hackathon).

**New RFQ page:** a drop zone for `.eml` files, the 4 sample emails as cards, and a mode select (Live / No
browser / Offline), each with a one-line explanation.

**Diagnostics page:** health details, and a **Self-check** button that runs the email-1 reference check
("6/6 rows, 105/105 sources matched").

**Design rules (no gimmicks):**
- **Brand (Ferguson design language):**
  - **Source:** the Ferguson Brand Connect guideline needs a login. These values come from its public
    portal theme and are **provisional** until someone checks them against the guideline.
  - **Palette** (one set of tokens in `web/src/index.css`, reused by `rfq/output/style.py` and the reply
    template):

    | Token | Hex | Use |
    |---|---|---|
    | `brand-navy` | `#00446a` | primary: top bar, primary buttons, links, Excel headers, the reply header bar |
    | `brand-navy-700` | `#003d5f` | hover |
    | `brand-navy-800` | `#003655` | pressed; dark-theme surfaces |
    | `brand-blue` | `#00a0dd` | accent: focus ring, active tab, selection, progress |
    | `brand-steel` | `#b2c7d2` | borders, dividers, muted icons |
    | `brand-mist` | `#e6ecf0` | page and section background (light theme), Not found row tint |

  - **Colour use:**
    - Navy on white is 10.3:1 and on mist 8.7:1 (both AA).
    - `brand-blue` on white is only 3.0:1, so it is never used for body text on light backgrounds; it is
      fine for focus rings, icons and large text.
    - In the dark theme `brand-blue` becomes the primary text and button colour (6.2:1 on the dark base),
      and navy is used for surfaces.
  - **Status colours** (success, warning, danger, info) are semantic. They don't come from the brand
    palette and must not be confused with it.
- **Components and colour:** shadcn/ui on Tailwind design tokens mapped to the brand tokens above, with
  neutral greys tinted toward `brand-steel` / `brand-mist` instead of zinc. Every status has an icon
  (lucide) **and** text, never colour or emoji alone.
- **Type and layout:**
  - **Font:** Inter (the brand portal's font). Email clients fall back to Arial / Helvetica.
  - **Text styles:** tabular numbers for prices and counts, IDs in monospace.
  - **Layout:** a 4/8 px spacing grid, one card radius and one elevation level.
  - **Logo:** use the Ferguson name in text only; no logo files unless taken from Brand Connect.
- **Motion:** 150–200 ms fades only; `prefers-reduced-motion` is respected.
- **Accessibility:** WCAG AA contrast in both themes, visible focus rings, everything reachable by
  keyboard, `aria-live` for run progress.
- **Screen size:** desktop first (1280 px and up) and still usable on a tablet.
- **Removed from the earlier plan:** flying ID chips, card flips, count-up counters, the ring gauge and
  emoji source badges. KPIs are plain numbers.

**API (`app/`):**
- **Endpoints:** `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/events` (SSE),
  `POST /api/runs` (upload or sample), `POST /api/runs/{id}/review` (one decision),
  `POST /api/runs/{id}/approve`, `GET /api/runs/{id}/files/{name}`, `GET /api/health`, `GET /api/samples`.
- **Serving:** FastAPI serves `web/dist` at `/`. In dev, Vite proxies `/api`.

## Showcase techniques (useful, not decorative)
- **Page cache + replay:** cache every live product page (HTML + screenshot) and spec PDF in `out/.cache/`.
  `--replay` re-runs from the cache, so a blocked ferguson.com or bad Wi-Fi during judging can't break the
  demo.
- **"Before vs after" fill rate:** fill rate for catalog only, + live page, + spec PDF, + quality. Shown on
  the Run page and the Summary sheet (fill rates only, no timings).
- **Time saved:** stage timings and total, next to an estimated manual time (configurable, e.g. 6 min per
  product). Dashboard and run.log only.
- **Self-check:** the email-1 reference check, one click on the Diagnostics page.
- **Parallel lookups:** 3 browser tabs at a time over CDP (with polite delays); results are re-sorted into
  item order.
- **Grounded AI:** LLM flags use structured outputs and must quote the cell value they question.
- **Ferguson alternatives for Not found (stretch):** for a competitor item, suggest catalog products with the
  same colour/width/type, parsed deterministically from the line text. Shown as suggestions only, never put
  on the RFQ.

**More useful additions (ranked by value ÷ effort)**
1. **Quantities + estimated quote value.**
   - **Capture:** email 2's attachment has a `Qty (rolls)` column and email 4 says `x 40 rolls`; record qty
     per item during extraction.
   - **Where it shows:** a "Request lines" table (ID, qty, unit price, line total, price source/date) on the
     Summary sheet, the Run page and the reply ("Estimated value: $4,312"). The RFQ sheet itself stays
     unchanged so the reference still matches.
2. **Sourcing risk alerts.**
   - **Out of stock:** items marked `OutOfStock` → "lead-time risk".
   - **Stale prices:** catalog-sourced prices are labelled "as of 24 Sep 2026, not live".
   - **Discontinued / Not found** items are listed.
   - **Shown at the top** of the reply and Summary. A buyer acts on these first.
3. **"Did you mean…?" for near-miss IDs.**
   - **When:** an unknown 5-7 digit ID that is one digit off (or one swapped pair) from a catalog ID.
   - **What happens:** a Note suggests the close match ("9677533 → did you mean 9677531?"), shown in the
     review UI with an Accept button. It is never auto-substituted, so blank still means unknown.
4. **Compliance matrix.** ANSI / OSHA / ASTM / UL per product as a ✓ grid on the Summary sheet and the
   Run page. Buyers screen suppliers on standards; this is free from data we already have.
5. **Follow-up emails in the same thread.**
   - **Trigger:** the customer replies "also add 5106899" or "remove 9677514".
   - **What happens:** the bot finds the earlier run by the thread's `References`, applies the change and
     sends version 2 of the RFQ with a "what changed" line.
   - **Quoted text:** quoted `>` text is ignored for these replies; forwarded blocks are still read (needed
     for email 4).
6. **More attachment types.** PDF item lists (pypdf is already installed), plus IDs in the subject line.
7. **Prompt-injection safety (a talking point for judges).**
   - **What the LLM sees:** product data only, never the raw email body. Web/PDF text is passed as quoted data
     with structured outputs.
   - **Grounding:** flags must quote the cell value they question.
   - **Limits on input:** attachment size/type limits; openpyxl read-only.
8. **Offline tests in GitHub Actions.** A green badge in the README answers the judges' "how do you know it
   works?" at a glance.
9. **Azure polish (optional).** Secrets in Key Vault via managed identity, Application Insights for
   request/LLM timing.

**Demo script** (to write into `README` or the pitch):
1. The dashboard is open on Azure (or locally with Chrome for the live part).
2. Send email 4 from a phone to the team inbox.
3. The run appears on the Runs page; the IDs are found and the cards fill in place.
4. It lands under "Needs review". Resolve the flags by keyboard on the Review page.
5. Preview the customer email, then Approve & send. The clean reply lands in the same thread.
6. Click a value to show its source and the PDF snippet.
7. Press Self-check on the Diagnostics page.

## Cross-platform: Linux + Windows
The same code and commands run on both. Rules for every file in `rfq/` and `app/`:
- **Paths:** `pathlib.Path` only, built from `ROOT` in `rfq/config.py` (the repo root resolved from the
  file's location), never from the current directory.
  - No hard-coded `/` or `\`, no `/tmp`; use `tempfile`.
  - Output folder names come from the email file stem, with the characters Windows forbids (`<>:"/\|?*`,
    trailing dots/spaces) replaced. They are capped at 80 characters, so the full path stays under
    Windows' 260-character limit.
- **CLI shims:** `rfq/build.py` and `rfq/chrome.py` are run as scripts, so they add `ROOT` to `sys.path`
  before importing `rfq.*`.
- **Encoding:** every `open()` / `read_text()` passes `encoding="utf-8"` (`"utf-8-sig"` for the CSVs). Windows
  defaults to cp1252, which breaks on the catalog's non-ASCII text. `reply.eml` is written as bytes
  (`msg.as_bytes()`), so line endings stay CRLF as email needs.
- **Console:** at start-up, `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. Printed lines stay
  plain ASCII (no emoji or arrows), so a cp1252 console or a redirected log can't crash the run.
- **Excel file lock:** on Windows, a `RFQ.xlsx` open in Excel can't be overwritten (`PermissionError`).
  - **Saving:** save to `RFQ.tmp.xlsx`, then `os.replace` it onto `RFQ.xlsx`.
  - **If it's locked:** retry 3 times over 2 s. Then save `RFQ (2).xlsx` and print "close RFQ.xlsx in Excel".
    For mailbot runs the folder is always new, so this never applies there.
- **Chrome launcher (`rfq/infra/chrome.py`, run as `python rfq/chrome.py`):**
  - **Already running:** if `http://127.0.0.1:9333/json/version` answers, it does nothing.
  - **Finding a browser:**
    - Windows: Chrome under `%ProgramFiles%`, `%ProgramFiles(x86)%` and `%LocalAppData%`, then Microsoft Edge
      (always present, and it speaks the same protocol).
    - Linux: `google-chrome`, `chromium`, `chromium-browser` on PATH.
    - macOS: `/Applications/Google Chrome.app`.
  - **Starting it:** profile in `tempfile.gettempdir()/chrome-rfq`. `--browser PATH` overrides the search.
  - **Port taken:** if 9333 is used by something that isn't Chrome, it says so and suggests `--port`.
- **Async on Windows:** the web app never runs Playwright inside uvicorn's event loop. `app/services/runner.py`
  starts `build.py` as a subprocess (as mailbot does) and follows `events.jsonl`. This avoids Windows
  event-loop limits, isolates crashes, and enforces a timeout.
- **Python:** 3.10+ (no 3.12+ only syntax); Windows teammates may not be on 3.14. `requirements.txt` uses
  lower bounds only; all packages have Windows wheels. `playwright install` is **not** needed (we attach to
  the user's Chrome).
- **Node (web only):** Node 20 LTS+ on both OSes. Scripts in `web/package.json` are OS-neutral (no `rm -rf`,
  no shell-specific syntax).
- **Venv path:** `.venv/bin/python` (Linux/macOS) vs `.venv\Scripts\python.exe` (Windows).
  - **Skills:** `rfq-run` / `rfq-verify` pick the right one.
  - **Docs:** README shows both, plus `py -3 -m venv .venv` for Windows.
- **Skill scripts:** `check.py --build` runs the four builds itself through `sys.executable`, so `rfq-verify`
  no longer needs a bash `for` loop. This works in PowerShell and Git Bash alike.
- **CI:** GitHub Actions runs `pytest` (offline) on `ubuntu-latest` and `windows-latest`, plus a Node job
  (`tsc`, eslint, vitest, `vite build`). This catches path, encoding and newline bugs before the demo.
- **Known Excel caveat:** `=IMAGE()` needs Excel 365 or 2021+. Older Excel shows `#NAME?` in that one column.
  It stays (the reference uses it); `Picture` carries the plain URL.

## Failure handling
Principle: **a bad input or a broken source makes the RFQ smaller, never the run fail.** Every problem lands
in one of three places:
- **Notes sheet:** what happened to which item (the buyer sees it).
- **`run.log`:** one line per warning, plus a traceback for unexpected errors, in the output folder.
- **The printed summary line:** `warnings: N`.

Only the cases in build.py's exit codes (above) stop a run.

| Stage | What can go wrong | Handling |
|---|---|---|
| Input | .eml path missing, a folder, unreadable | exit 2 with a one-line message |
| Input | Malformed MIME, unknown charset, bad base64/QP | `get_content()` in try; fall back to `get_payload(decode=True).decode(charset or "utf-8", errors="replace")`; Note "part could not be decoded" if still unreadable |
| Input | HTML-only body, or `message/rfc822` forwarded as an attachment | strip tags with `html.parser`; `walk()` recurses into attached emails |
| Input | No items found | still write RFQ (header only), a Note, and a reply asking the sender for item numbers; status `ready` (nothing to review, the reply asks the customer); exit 0 |
| Input | Too many items (pasted catalogue, huge sheet) | cap at 300 items; the rest go to a Note "not processed, list too long" |
| Attachment | `.xls` (old format), `.csv`, `.xlsm`, `.pdf`, password-protected or corrupt `.xlsx` | `.xlsx`/`.xlsm`: openpyxl `read_only=True, data_only=True` in try. `.csv`: `csv` module. `.xls`, protected or corrupt files: skip with Note "could not read attachment X, please resend as .xlsx" |
| Attachment | IDs stored as numbers (`1376044.0`), with spaces or `#` | normalise: whole floats → int → str, strip, drop `#`. Leading zeros can't be recovered from numbers, so add a Note |
| Attachment | Size or zip-bomb risk | skip attachments > 10 MB; read at most 5,000 rows per sheet |
| Extraction | Phone, zip, PO or order numbers that look like IDs (e.g. Pune pin code `411001`) | skip a number when the words just before it are `tel/phone/fax/mobile/zip/pin/po/order/invoice/qty`, or it's inside a `+NN` phone pattern. Anything kept but unknown just shows as Not found: never dropped, never guessed |
| Lookup: browser | Chrome not running or port refused | detected **once** at start (1 s probe); the whole run switches to `--no-browser` with one warning (not one per item) |
| Lookup: browser | Chrome closed or crashed mid-run; Playwright not installed | catch `playwright` `Error`/`ImportError`; mark the browser dead; remaining items use the catalog |
| Lookup: page | Timeout (20 s per page), HTTP 403/429/5xx, "Access Denied" / captcha / "Pardon our interruption" text | treat as blocked → catalog fallback, Note "live page blocked". After 3 blocks in a row, stop trying live for this run |
| Lookup: page | 404, search with no results, redirect to another product | "not on the live site": use the catalog; if not in the catalog either → Not found |
| Lookup: page | Layout changed (selectors find nothing) | 0 values parsed counts as a failed live read, never as Found with blanks; Note + catalog fallback |
| Lookup: budget | Many items × slow pages could exceed mailbot's 900 s timeout | overall live budget of 8 min; after that, the remaining items go straight to the catalog with a Note |
| Spec PDF | Download error/timeout (30 s), HTML error page instead of a PDF, encrypted or scanned PDF with no text, pypdf exception | check the `%PDF` header before caching; a failed download → bundled copy in `data/spec_cache/` with a Note; if that is missing or unreadable too → skip with a Note. Never cache a bad file |
| Spec PDF | Cached file corrupt (half-written) | write the cache through a temp file + `os.replace`; on a read error, delete the cache file and download once more |
| Catalog / template | File missing, invalid JSON, sheet renamed | checked at start-up with a clear message naming the file → exit 1 (the kit is broken, not the email) |
| Data | `[]` placeholder values; bare numbers without units | base copies them as they are (the source says so); the quality agent flags `[]` as "empty placeholder" and normalises units |
| Excel write | Text starting with `=` from a web page or email would become a formula | `safe_cell()` writes it as a string (`data_type="s"`). Only the `Image` column is a formula, and its URL is checked to be `https://` with `"` escaped |
| Excel write | Control characters (`IllegalCharacterError`), cell > 32,767 characters | strip illegal characters with openpyxl's `ILLEGAL_CHARACTERS_RE`; cut to 32,000 + Note |
| Excel write | Output folder not writable, disk full | exit 1 with the path in the message (the guard in build.py still tries `error.txt`) |
| Quality LLM | No Azure settings, network error, 401, 429, timeout, content filter, invalid JSON or a flag that doesn't quote its cell | client `timeout=30, max_retries=2`; any failure skips the LLM for that row; Summary says "AI review skipped for N rows: reason". Rule flags still run. Total LLM time capped at 90 s |
| Reply | Very large RFQ.xlsx | fine for Gmail (25 MB); the reply notes if items were capped |
| Mailbot | build.py fails or times out (see the poison-email fact) | patch `mailbot.py` (small, kept in its style): wrap each email in `try/except Exception`. On failure, log it, send a short "we couldn't process this RFQ automatically, a person will follow up" reply in the same thread, and **always** mark it `\Seen` in `finally`. A failed SMTP send is logged and the email is still marked read, so it never loops |
| Mailbot | Run held for review | no reply now; log the dashboard link; mark `\Seen`. The reply is sent once, on approval |
| Mailbot | Two RFQ emails arrive together | already handled: one at a time, separate `out/rfq-<time>-<uid>` folders |
| Review | Approve & send fails (SMTP error) | status stays `approved`, the UI shows the error and a Retry button; never sends twice (the status is set to `sent` only after SMTP accepts) |
| Review | Two reviewers on one run | review.json writes are atomic; each decision carries the flag id and the last-seen version, and a stale write is rejected with "reload" |
| Web app | Upload is not .eml, too big (> 15 MB), or has a path-traversal filename | reject with 400; the server picks the folder name (`uuid`), never the client |
| Web app | Two live runs at once on one Chrome | a lock allows one live run at a time; others queue or run `--no-browser` |
| Web app | Browser tab closes during SSE | the run continues; the results stay on the Runs page |
| Azure | No browser, read-only app folder | `RFQ_MODE=no-browser` env forces the mode; `out/` goes under `/home/data` (writable, persistent) |

**Logging:** `rfq/infra/log.py` sets up `logging` to `run.log` in the output folder plus a console line for
warnings. No secrets in logs: `.env` values and email bodies are never logged, only IDs, counts and error
types.

## Azure deployment
Revised from the deploy slides: "Wrap, don't rewrite". There's no browser in the cloud and only /tmp is
writable.

**Target: Azure Functions** (Python 3.12, Linux, Consumption plan), as on Day 3. App Service stays as an
alternative.
- **`function_app.py`:** wraps the existing FastAPI app (`azure.functions.AsgiFunctionApp`); nothing is
  rewritten.
- **`host.json`:** `routePrefix: ""`, so the API, the dashboard and `/rfq` keep their paths. The bare address
  serves the dashboard.
- **`/rfq` page:** the deck's upload page. Upload a request email (.eml), the RFQ is built synchronously, and a
  result page shows the counts, the quality line and a **Download RFQ.xlsx** button. Browsers block a file sent
  straight back from a form, hence the result page. It is server-rendered, so it works even if the SPA's live
  updates don't.
- **App settings:**
  - `RFQ_MODE=no-browser` (backup catalog + bundled spec sheets);
  - `RFQ_OUT_DIR=/tmp/autorfq`, because only /tmp is writable;
  - `RFQ_AUTO_BROWSER=0`;
  - the keys (OpenAI, mail) set with `az functionapp config appsettings set`, never in the zip.
- **The zip:** `function_app.py`, `host.json`, `requirements.txt` without playwright (written by the deploy
  script), `app/`, `rfq/`, `data/`, `templates/`, `reference/`, `emails/`, `web/dist`. `.env` stays out.
- **Script:** `scripts/deploy_azure.py --target functions` (default) or `--target webapp`.
  - **Functions:** resource group, storage account, Function App, settings, zip deploy with a remote build.
  - **After deploying:** it waits for `/api/health`, then runs the email-1 self-check on the live link.
- **What runs where (for the presentation):** the email bot runs on the laptop (needs Gmail and, for live
  pages, Chrome); the upload page and dashboard run on Azure.
- **Done when:** email 1 uploaded to the live link gives the same RFQ as the laptop (from the catalog), and
  the arm's work shows in the Excel.
- **Known snags (from the deck):**
  - **AADSTS50076/50079:** sign in at portal.azure.com, set up the Authenticator app, then `az logout` and
    `az login`.
  - **Name taken:** add two letters.
  - **A missing module:** add it to `requirements.txt`.
  - **Cold start:** open the page once before the demo.
- **Hand-in (slide "Push to the common repo"):** fork `github.com/Tanmaya-kh/ferguson-agentic-fest`, copy the
  code into the team folder (without `.env`, `venv`, `out`), fill in the team README, and open one PR. **Not
  done without the user's go-ahead**: the user chose `Prajwaljb/AutoRFQ` as the working repo.

## Product database (added 2026-10-16, user request: "a centralized db for future scaling")
- **What:** `rfq/infra/productdb.py`, a SQLite database (`out/products.db`, or `RFQ_PRODUCTS_DB`; on Azure
  `/tmp/autorfq/products.db`) holding every product the flow has found.
  - **Per product:** cells with their sources, price and stock, the source (live / catalog / spec), the URL,
    the fetch time and a re-use count.
- **Fetch once, reuse:** a live run takes a product fetched from ferguson.com within `RFQ_DB_TTL_HOURS`
  (default 24) from the database, with a Note. When every item is fresh, no Chrome window is opened at all.
- **Determinism kept:** offline and no-browser runs never read from it. The reference test is offline.
- **Admin page (`/admin`):**
  - stats and a searchable product table;
  - **Load catalog**, which seeds the backup catalog and never replaces a live product;
  - **Clear database**, for simulating a first run.
  - Writes need `ADMIN_TOKEN` when it is set.
- **Scaling:** the same functions (`get`, `fresh_live`, `upsert`, `list`, `stats`, `clear`) can be moved to a
  server database (Postgres or Azure SQL) without touching the pipeline.

## Competitor and customer codes (added 2026-10-16)
Codes like `Mutual Industries 17783-79-3000`, `Empire 31-024` and `MTX-4409-XQ` are not Ferguson items. The
RFQ row stays **Not found** (the spec and the reference require it), and the flow works out what the part is
and offers a Ferguson equivalent. It never puts another brand's specs on the RFQ, and it never guesses.

1. **What is it? (`rfq/sources/competitor.py`, the "Competitor Product Finder").**
   - **Search:** SerpApi for "<brand> <code>".
   - **Only exact matches:** only results whose title or snippet names this exact code are used.
   - **Specs:** width, length (yards → feet: "333.33 yds." → 1000 ft), colour, detectable, utility on the
     lettering, thickness, and a seen price. **Each value keeps the URL it came from.**
2. **Which Ferguson item? (`sources/alternatives.py`).** Catalog products are scored on those attributes,
   with APWA colours (electric red, water blue, …). A colour or tape-type conflict rules a product out.
   - **Labels:** a match is *strong* (score 8+), *possible*, or *confirmed* (chosen by a reviewer before).
3. **Results on the sample codes (live web):**

   | Code | The web says | Ferguson equivalent |
   |---|---|---|
   | Mutual 17783-79-3000 | Electric line, non-detectable, 3 in x 1000 ft (333.33 yds), red, 4.5 mil (staples.com, mutualindustries.com) | 9677539, 3 in. x 1000 ft. Marking Tape in Red (strong) |
   | Empire 31-024 | Water line, detectable, 6 in x 1000 ft, blue, 5 mil (porterpipe.com, crescentelectric.com) | 5106912, 6 in x 1000 ft Blue Detector Tape, water (strong) |
   | MTX-4409-XQ | nothing: no page names it (the customer's own code) | none: the reply asks for size, colour and use |

4. **Shown to people:**
   - **Reply:** "The web lists it as … Closest Ferguson match: 9677539 … Reply "use 9677539" to add it".
     For an unknown code it asks one specific question instead.
   - **Excel:** the Summary's competitor cross-reference table (every spec with its source) and the
     alternatives table with the match label.
   - **Web app:** "The web says" on the card, the specs with their source links in the side panel, and
     **Use instead** for a reviewer.
5. **Remembered (product database, `crossrefs` table):**
   - each code's finding (or "nothing known") is kept for 30 days, so it isn't searched again;
   - a reviewer's **Use instead** confirms the Ferguson equivalent for that code, and it is suggested first,
     as "our usual equivalent", on every later RFQ;
   - it is visible on the Admin page and removed by Clear database.
6. **Not in offline mode:** offline runs never search or read the cross-reference, so they stay repeatable.

## Configuration (`.env`)
One file in the repo root, git-ignored; `.env.example` is the committed template.
- **Who reads it:** `rfq/infra/env.py` loads it once, for `build.py`, `mailbot.py` and the web app alike. Values
  already set in the environment win.
- **On Azure:** the same names are App settings; `scripts/deploy_azure.py --with-secrets` copies them over.
- **Keys:**
  - `BOT_EMAIL`, `BOT_PASSWORD` (Gmail App Password: Google Account → Security → 2-Step Verification → App
    passwords);
  - `OPENAI_API_KEY`, `OPENAI_MODEL`, or `AZURE_OPENAI_ENDPOINT` / `_API_KEY` / `_DEPLOYMENT`;
  - optional: `REVIEW_NOTIFY_EMAIL`, `DASHBOARD_URL`, `SERPAPI_API_KEY`.
- **Diagnostics page:** shows which keys are set (never their values).

## Frontend: hackathon polish (revised 2026-10-16, user request: "more flashy")
The earlier "no gimmicks" rule is relaxed for the demo. Usefulness stays first: every effect shows real data,
and `prefers-reduced-motion` turns motion off.
- **Background:** an aurora gradient in brand navy and cyan behind glass cards (blur, gradient borders, glow
  on hover).
- **Runs page hero:** "Every RFQ answered in under a minute", with animated counters (RFQs, items found,
  average fill rate, hours saved), an animated pipeline strip (Email → Extract → Look up → Fill → Quality →
  Reply) and a "Try a sample" button.
- **Run page:**
  - **Gauge:** a fill-rate ring.
  - **Agent findings panel:** the same colour legend as the Excel (grey missing, amber code, orange model),
    with "by code" / "by model" chips.
  - **Cards:** item cards stagger in.
  - **While processing:** a live pipeline with a pulsing current step and a ticker of events.
- **Approve & send:** a confetti burst and a toast.
- **Status badges:** glow, while keeping an icon and text.

## Build order (correctness first, then UX; commit after each)
0. **Housekeeping (before any code):**
   - **Docs (done 2026-10-16):** this plan and `spec.md` are updated for the hardening and the
     determinism / UX / structure revisions. `.gitignore` covers `web/dist/` and `web/node_modules/`.
   - **Skills:** make `rfq-run` / `rfq-verify` pick the venv Python by OS, use `rfq/chrome.py`, and add
     `check.py --build` plus a "status Ready for email 1" check.
1. **Base offline:** `config` + `models` + `infra/` → extract → catalog source → workbook → reply →
   pipeline + build.py with exit codes, the guard, `run.log` and `run.json`. `test_reference`,
   `test_failures` and `test_determinism` green, plus the Windows CI job.
2. **mailbot.py patch:** per-email try/except/finally with the fallback reply, plus the hold gate (read
   `run.json`). Tested with a build that is forced to fail and with a held run.
3. **API + web skeleton:** FastAPI routes, the runner service, the Vite app with the shell, the Runs page,
   the Run page and SSE. Builds run as subprocesses.
4. **Live and spec sources:** `chrome.py`, then the live Chrome lookup with blocked/timeout/wrong-product
   handling and the run budget; page cache/replay + screenshots. Then `scripts/fetch_specs.py` (commit
   `data/spec_cache/`) and the spec PDF reader with snippets.
5. Styled Excel + customer reply (HTML + text).
6. **Quality Agent:** rules → Azure OpenAI as advisory, with timeouts and skip-on-failure. Then the
   Summary sheet, `review/state.py`, the Review page and approve & send (`app/services/mailer.py`).
7. Mailbot end to end on Linux **and** Windows, including the hold → approve → reply path.
8. Azure deploy; then the before/after fill rate, time saved, Self-check, parallel tabs and alternatives.
9. Useful additions in ranked order (quantities + quote value and risk alerts first; follow-up threads last).

## Verification
- **Setup:** `uv venv && uv pip install -r requirements.txt`; `cd web && npm ci`.
- **Tests:** `pytest` (all offline).
  - `test_extract`: the four expected ID lists above.
  - `test_reference`: `build.py emails/email-1-ids-in-body.eml --out <tmp> --offline` → RFQ sheet values
    (incl. the IMAGE formula) and the Sources row set equal the reference, cell for cell. This holds with
    and without the quality agent, and the status is `ready`.
  - **Not found checks:** email 2 offline has `225123` = Not found; emails 3 and 4 have the competitor codes
    and `9677533` = Not found; no ID is dropped.
  - `test_determinism`:
    - building each email twice gives equal RFQ, Sources, Notes and Summary values;
    - a shuffled lookup completion order gives the same rows and notes;
    - no output file contains a timing.
  - `test_quality`: unit normalisation, the flag rules, and the Summary fill-rate maths, with the LLM mocked.
    - **AI stays advisory:** with the LLM mocked to return a high-severity flag, the status stays `ready`, no
      cell is highlighted, and the flag appears under AI suggestions.
    - **AI failures:** with the LLM mocked to time out, return 429, or return invalid JSON, the rule flags
      remain, the Summary says "AI review skipped", and no value changes.
  - `test_review_state`: keep/edit/clear decisions, undo, `human_review` source rows, the stale-write
    rejection, and finalise removing the review marks.
  - `test_hold_flow`, with IMAP/SMTP mocked:
    - a `needs_review` run makes the patched mailbot send nothing and mark the email read;
    - approving it sends exactly one in-thread reply;
    - a failing SMTP send leaves the status `approved`.
  - `test_failures`: each fixture gives exit 0, an RFQ.xlsx, a reply.eml and the expected Note.
    - **Email fixtures:** no items; HTML-only body; bad charset; forwarded `message/rfc822`; a phone number
      and pin code next to real IDs; 400 items (capped).
    - **Attachment fixtures:** a corrupt `.xlsx`, a `.xls`, and a `.csv`.
    - **Excel safety:** a value starting with `=` stays text.
    - **Other cases:** a missing template gives exit 1; a missing .eml gives exit 2; a locked output file is
      simulated by patching `os.replace` to raise `PermissionError`.
  - **Browser down:** a build without `--offline` while nothing listens on 9333 finishes with catalog values
    and exactly one "browser not available" warning.
- **Web:**
  - vitest: the status badge mapping, the sort order of the runs, flags and items, and the Approve & send
    button being disabled while a high-severity flag is open.
  - Playwright e2e (`web/e2e`): open a held run, resolve the flags by keyboard, preview the email, then
    approve (mocked SMTP).
- **Windows:** CI runs the whole offline suite on `windows-latest`. On a Windows laptop:
  - **Setup and verify:** `py -3 -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`, then
    `/rfq-verify`.
  - **Live run:** `python rfq\chrome.py`, a live build of email 2 (`225123` Found), and the mailbot test.
  - **File lock:** run once with `RFQ.xlsx` open in Excel to see the lock message.
- **Mailbot robustness:** temporarily rename `templates/rfq_template.xlsx`, send an RFQ email, and check:
  - the sender gets the "a person will follow up" reply;
  - the email is marked read;
  - the next RFQ email (after restoring the template) is still answered.
- **Live run:** Chromium open on port 9333, run build on email 1 without `--offline`, and check the Notes
  sheet for live/catalog differences. Email 2 live should find `225123`.
- **No-browser run:** build email 2 with `--no-browser` and the network off. The RFQ is the same as with the
  network on, and the spec Notes say "bundled copy".
- **End to end:** `python mailbot.py`, send the deck's test email from another account, and get a reply in the
  same thread with RFQ.xlsx and the quality line. Then send email 4's content and take it through hold →
  review → approve.
- **Styling safety:** `test_reference` runs on the styled output, so formatting can't change a value.
- **Dashboard (manual):**
  - **Runs:** `uvicorn app.main:app`, open it, and run all 4 sample emails in both themes.
  - **States:** check the empty, loading and error states, a keyboard-only review, the source side sheet
    and the downloads.
  - **Offline replay:** run once with `--replay` and Wi-Fi off.
- **Customer reply:** open `out/<name>/reply.eml` in a mail client (or send it to yourself) and check the
  HTML and plain-text rendering and the attachment. It must contain no flags, review links, "AI" or "DRAFT".
- **Azure:** open the deployed URL, upload email 2 and email 4, and check the Excel, the Summary and the
  review flow.
- **Commits:** the deck asks for a commit after each working step. I'll commit when you ask.
