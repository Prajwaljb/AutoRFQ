# RFQ flow · spec

## Input
A request email (.eml) from emails/ or from the team inbox. Items are in the body (one per line, inside
sentences, with `#` in front, in a forwarded thread or an attached email) or in an attachment (.xlsx, .xlsm or
.csv, in the column headed like "Item number"). Some items are competitor part numbers, customer codes, or IDs
Ferguson no longer lists. Emails can be messy: HTML only, odd character sets, phone numbers, attachments that
can't be read.

## Steps
1. **Read the email.** Read every text part (HTML is stripped to text), attached emails, then each
   attachment. Find every item:
   - Ferguson product IDs: 5 to 7 digits, standing alone or with `#` in front (`#5106926`, `1844552 ,`).
     Quantities, sizes and dates are not IDs (`x 40 rolls`, `3 inch`). Neither are numbers right after
     tel / phone / fax / mobile / zip / pin / PO / order / invoice / qty, or inside a `+NN` phone number.
   - Other codes: hyphenated part numbers such as `17783-79-3000`, `31-024`, `MTX-4409-XQ`. Keep the
     brand if the line names one (`Mutual Industries`, `Empire`).
   - Keep the order of first appearance. A repeated item is kept once and the repeat is noted.
   - IDs stored as numbers in a sheet (`1376044.0`) become text (`1376044`).
   - At most 300 items. Anything past that is listed in a Note as not processed.
2. **Look up each Ferguson ID** in this order:
   - the live ferguson.com product page, through the Chrome window opened for scraping
     (`http://127.0.0.1:9333`). The page counts only if it shows `Item #<id>`;
   - the manufacturer spec sheet PDF (link in `data/spec_sheet_links.csv`; the bundled copy in `data/spec_cache/` if the
     download fails), only to fill cells still blank;
   - `data/product_catalog.json`, when the live page is blocked, times out, isn't there, or live lookup is
     turned off by an option.
   - Live wins over the catalog. Every difference between them goes to the Notes sheet.
   - Hyphenated codes are not looked up in the base. They go on the RFQ as Not found.
   - Live lookups share a time budget (8 minutes per email). Items left after that use the catalog.
3. **Fill `templates/rfq_template.xlsx`**, RFQ sheet: one row per item, in order.
   - Every value is written as text, exactly as the source gives it. Text starting with `=` stays text.
   - `Image` is `=IMAGE("<picture url>")` (the only formula) and `Picture` is the picture URL.
   - `Lookup Status` is `Found` or `Not found`. A Not found row has only `product_id` and `Lookup Status`.
4. **Sources sheet**: one row for every filled spec cell (product, column, value, source type, confidence,
   source). Catalog values keep the row from `data/product_catalog_sources.csv` as it is. `Image` and
   `Picture` reuse the source of the picture URL. Live values: `ferguson_page`, high, page URL and date.
   Spec sheet values: `spec_sheet`, medium, PDF URL.
5. **Notes sheet** (added, the template has none): one row for each of these:
   - a duplicate;
   - a competitor or unknown code (with its brand);
   - a Not found item;
   - a live/catalog difference;
   - every problem met on the way: an unreadable part or attachment, a blocked page, a skipped spec sheet,
     items over the limit, the time budget running out.
6. **Quality agent (after the base):**
   - Puts units in one standard: Length ft, Width in, Thickness mil, Weight lb. A bare `1000` becomes
     `1000 ft`, and the Sources and Notes sheets record it.
   - Flags missing or odd values, including the `[]` placeholder. Each rule flag has a severity; `high` is
     only for values that are probably wrong.
   - An LLM may add **AI suggestions**. They are advisory: they never write or change a value and never
     change the status. If the LLM is not set up or fails, the rule flags still run and the Summary says
     the AI review was skipped.
   - Adds a Summary sheet: found / not found counts, fill rate, rule flags, AI suggestions, and the status
     `Ready` or `Needs human review` (any open high-severity rule flag).
7. **Save** `RFQ.xlsx`, `reply.eml`, `run.json` (run details and status) and `run.log`. The reply is written
   for the buyer:
   - how many products were found and not found;
   - an item table in email order;
   - for each item that couldn't be matched, the reason and what to send instead;
   - a "Quality check" line in buyer words: every value checked, how many measurements were converted
     to standard units, and how many values are worth a second look on the Summary sheet (or "No issues
     found"; "checked by our team" after a review);
   - that every value is on the Sources sheet;
   - RFQ.xlsx attached.

   If no items were found, the reply asks the sender for the item numbers. The reply never contains
   internal words (flag, rule, severity), fill rates, review links, "AI" or "DRAFT".
8. **Send or hold.**
   - **Ready:** the reply is sent automatically.
   - **Needs human review:** nothing goes to the customer yet. A person reviews each flag (keep, edit or
     clear the value) and then approves. The approved RFQ is rebuilt without review marks and sent as the
     one reply in the same thread. An edit gets a `human_review` Sources row with the reviewer and time.

## Rules
- Blank means unknown. Never guess a value. The quality agent flags, it never invents. A blank beats a guess.
- The quality agent runs inside the flow (a stage of `rfq/build.py`), not as a separate script. Everything it
  adds has a source or a reason: a converted unit keeps its Sources row and gets a Note; every flag and AI
  suggestion states its reason and quotes the value it is about.
- Never drop an item. Unknown IDs and competitor parts stay on the RFQ as Not found.
- Every filled spec cell has a Sources row. `product_id`, `Description` and `Lookup Status` do not, as in
  the reference.
- The base uses no AI: same email in, same RFQ and Sources sheets out. LLM output only goes to the AI
  suggestions on the Summary sheet and in the review screen.
- The output is deterministic:
  - status, highlights and reply wording depend only on rule flags;
  - rows and notes follow the email's order, never the order in which lookups finish;
  - timings never go into RFQ.xlsx or the reply.

  Spec sheets fall back to the bundled copies in `data/spec_cache/` when the download fails.
- A bad email or a broken source gives a smaller RFQ and a Note, never a failed run. If Chrome is not open,
  the whole run uses catalog + spec sheets, with one warning.
- Every email to the team inbox gets exactly one reply. An RFQ that needs review is held until a person
  approves it. If the flow fails, the sender gets a "a person will follow up" reply, and the email is still
  marked read so it is never retried in a loop.
- Runs the same on Windows and Linux. All files are read and written as UTF-8 and all paths are built in
  code. If RFQ.xlsx is open in Excel, the flow saves a copy instead of failing.
- Secrets (Gmail App Password, Azure keys) live in `.env` only, and never appear in logs.

## Run
`python rfq/build.py <email.eml> --out out` writes `RFQ.xlsx`, `reply.eml`, `run.json` and `run.log` to
`out/<email name>/`.
- **Options:**
  - `--offline`: catalog only, no network, used by tests.
  - `--no-browser`: catalog + spec PDFs, used on Azure.
  - `--no-quality`: skip the quality agent.
  - `--cdp <url>`: Chrome address, default `http://127.0.0.1:9333`.
  - `--replay`: reuse the cached pages and PDFs in `out/.cache/` (re-run without network).
- **Output:** one printed line: items, found (live / spec sheet / catalog), not found, flags, warnings.
- **Exit code:** `0` when the RFQ and reply were written (even with warnings), `2` for a wrong command line
  or missing email file, `1` only if the kit itself is broken (template or catalog missing).
- **Other commands:**
  - `python rfq/chrome.py`: opens the scraping Chrome window on Windows or Linux (Edge if Chrome is missing).
  - `python mailbot.py`: answers emails with RFQ in the subject in the team inbox, using the same command.
    It doesn't send runs with status `Needs human review`; those wait for approval in the web app.
  - `uvicorn app.main:app`: the web app (runs, review, approve & send), serving the built `web/dist`
    (`npm ci && npm run build` in `web/` first).
  - **Azure App Service:** startup command
    `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`, with `RFQ_MODE=no-browser` in App Settings.
- **Python path:** use the venv. On Windows that's `.venv\Scripts\python`; on Linux, `.venv/bin/python`.

## Done when
- `--offline` on email 1: the RFQ and Sources sheets equal `reference/email-1 reference output.xlsx`, with
  and without the quality agent, and the status is `Ready`.
- Building the same email twice gives the same values on every sheet, even when the lookups finish in a
  different order. An AI suggestion never changes a value or the status.
- `--offline` on emails 2 to 4: `225123`, `9677533`, `17783-79-3000`, `31-024`, `MTX-4409-XQ` and
  `17774-79-3000` show as Not found, `#5106926` appears once, and no item is dropped.
- Live: `225123` (email 2) is Found from ferguson.com, and live/catalog differences are on the Notes sheet.
- Broken inputs each give an RFQ, a reply, a Note and exit code 0: no items, HTML-only, bad charset, an
  unreadable attachment, a phone number next to IDs.
- With Chrome closed, a normal run still finishes from the catalog.
- The offline tests pass on Windows and Linux.
- An email with RFQ in the subject sent to the team inbox gets RFQ.xlsx back in the same thread. If the flow
  fails, the sender still gets one reply and the bot moves on to the next email.
- An RFQ that needs review sends nothing until it is approved in the web app. After approval it sends one
  reply in the same thread, with the edits on the Sources sheet as `human_review`.
- Azure: uploading email 1 to the deployed app gives the same RFQ values as a local run in the same mode
  (`--no-browser`). Compared with the reference, the only allowed differences are blank cells filled from
  a spec sheet (in the reference, OSHA and ASTM are blank for some rows). Each of those has a `spec_sheet`
  Sources row.
