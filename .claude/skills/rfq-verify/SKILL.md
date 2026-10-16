---
name: rfq-verify
description: Check the RFQ flow against spec.md "Done when". Builds the four sample emails offline (or live) and compares email 1 with the reference Excel cell for cell, checks the expected Not found items, Sources coverage and reply.eml. Use after any change to rfq/, before committing, or when asked "does it work / does it match the reference".
argument-hint: "[--live] [--no-quality]"
user-invocable: true
---

# Verify the RFQ flow

The acceptance checks from `spec.md` ("Done when"), runnable in one go. `check.py` only reads the outputs,
so it works with any implementation of `rfq/build.py`.

## Steps

1. If `rfq/build.py` does not exist yet, say so and stop: there is nothing to check.
2. Build and check in one command, with the venv Python (`.venv/bin/python` on Linux/macOS,
   `.venv\Scripts\python.exe` on Windows):
   ```
   .venv/bin/python .claude/skills/rfq-verify/check.py --build [--live] [--no-quality]
   ```
   - Default: offline. This is the mode the reference and the Not found list are defined for.
   - `--live`: builds without `--offline` (the Chrome window must be open; see the `rfq-run` skill).
     `225123` must then be Found.
   - `--no-quality`: run the default as well, because the spec requires email 1 to match with and
     without the quality agent.
   - It writes to `out/verify/` (cleared first) and prints each build's summary line. A build that exits
     non-zero is reported with its error output.
3. The checker covers the expected items and order, Not found rows, text-only cells, Sources coverage,
   reply.eml, the email-1 reference (values and Sources order) and `run.json` status `ready` for email 1.
4. To re-check existing outputs without rebuilding, drop `--build` (and pass `--out` if they are elsewhere).
5. Also run `pytest -q` if a `tests/` folder exists, and `npm test` in `web/` if a `web/` folder exists.

## Report

- One line per email: PASS, or the FAIL lines copied as they are.
- For a value mismatch with the reference, open both workbooks and show the cell: product, column, ours
  vs reference. Then find the cause in `rfq/`.
- Do not change the reference, the checker's expected lists, or the spec to make a check pass. If a check
  looks wrong, say why and ask.
