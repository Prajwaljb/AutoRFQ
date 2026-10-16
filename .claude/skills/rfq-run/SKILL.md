---
name: rfq-run
description: Launch and drive the RFQ flow on this machine. Opens the scraping Chromium window on port 9333, runs rfq/build.py on an email (offline, no-browser or live), shows the result, starts mailbot.py, or starts the web app (runs, review, approve & send). Use when asked to run, try, demo or screenshot the RFQ flow, or to check a change in the real app.
argument-hint: "<email.eml | email number 1-4 | mailbot | web> [--offline|--no-browser|--no-quality]"
user-invocable: true
---

# Run the RFQ flow

Python lives in `.venv/`. Always use the venv Python (`mailbot.py` runs the base with the Python that
started it): `.venv/bin/python` on Linux/macOS, `.venv\Scripts\python.exe` on Windows. Below, `PY` means
that path.

## 1. Pick the email

- A number 1-4 means `emails/email-<n>-*.eml`. A path is used as it is.
- `mailbot` means step 4, `web` means step 5.
- No mode given: use live if the Chrome window is up (step 2), else `--no-browser`. Say which mode ran.

## 2. Chrome window (live mode only)

Check first, and don't start a second one (use `127.0.0.1`, not `localhost`: on Windows `localhost` can
resolve to IPv6 while Chrome listens on IPv4):
```
curl -s http://127.0.0.1:9333/json/version
```
If nothing answers, start it in the background with `PY rfq/chrome.py` (finds Chrome, Edge or Chromium on
any OS). If `rfq/chrome.py` doesn't exist yet, use the Linux form of the deck's Chrome command:
```
chromium --remote-debugging-port=9333 --user-data-dir=/tmp/chrome-rfq https://www.ferguson.com/
```
Then wait until the curl check answers. If ferguson.com shows a sign-in or cookie prompt, ask the user to
click "Stay signed out" or accept in that window: the code reads pages like a person, it doesn't solve
prompts. Leave the window open when you're done.

## 3. Build

```
PY rfq/build.py <email.eml> --out out [mode flags]
```
- Show the one-line result it prints (items, found by source, not found, flags).
- Output is in `out/<email name>/`: `RFQ.xlsx`, `reply.eml`, `run.json` and `run.log`.
- Summarise the RFQ for the user by reading it with openpyxl: each row's product_id and Lookup Status, the
  Notes sheet, and the Summary sheet if present. Don't paste whole sheets.
- Report the status from `run.json` (`ready` or `needs_review`) and, if needs_review, the open high
  flags and any AI suggestions (advisory).
- If `rfq/build.py` doesn't exist yet, say so and stop.

## 4. Mailbot (only when asked)

- Needs `BOT_EMAIL` and `BOT_PASSWORD` in `.env`. Check they are set with
  `grep -c '^BOT_' .env`. Never print `.env` or the password.
- Start it in the background: `PY mailbot.py [mode flags]`.
- It answers unread emails from today with RFQ in the subject, sent from another address. Runs with status
  `needs_review` are held: nothing is sent until someone approves them in the web app (step 5).
- It replies from the team inbox to real people, so confirm with the user before starting it. Stop it when
  the test is done.

## 5. Web app (only when asked)

- If `app/main.py` doesn't exist yet, say so and stop.
- If `web/dist/` is missing, build it first: `npm ci && npm run build` in `web/`.
- Start it in the background: `PY -m uvicorn app.main:app --port 8000`, then give the user
  `http://127.0.0.1:8000`.
- Approve & send in the review screen emails a real customer when mail settings are set. Don't click it
  yourself; leave approval to the user.

## Checks

For pass/fail against the spec and the reference, use the `rfq-verify` skill instead.
