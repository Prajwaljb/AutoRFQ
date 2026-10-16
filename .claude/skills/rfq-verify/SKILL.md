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
2. Build all four sample emails into a fresh folder (use the venv Python: `.venv/bin/python` on
   Linux/macOS, `.venv\Scripts\python.exe` on Windows; once `check.py --build` exists, use that instead of
   the loop):
   ```
   rm -rf out/verify
   for f in emails/*.eml; do .venv/bin/python rfq/build.py "$f" --out out/verify --offline $EXTRA; done
   ```
   - Default: `--offline`. This is the mode the reference and the Not found list are defined for.
   - With `--live` in the arguments: drop `--offline` (the Chrome window must be open; see the `rfq-run`
     skill) and pass `--live` to the checker. `225123` must then be Found.
   - With `--no-quality` in the arguments: add it to `$EXTRA`. Run the default as well, because the spec
     requires email 1 to match with and without the quality agent.
   - If a build exits non-zero, report its error output; don't hide it.
3. Run the checker:
   ```
   .venv/bin/python .claude/skills/rfq-verify/check.py --out out/verify [--live]
   ```
4. Check the status: `out/verify/email-1-ids-in-body/run.json` must say `ready` (spec "Done when"). Report it
   if `run.json` is missing.
5. Also run `pytest -q` if a `tests/` folder exists, and `npm test` in `web/` if a `web/` folder exists.

## Report

- One line per email: PASS, or the FAIL lines copied as they are.
- For a value mismatch with the reference, open both workbooks and show the cell: product, column, ours
  vs reference. Then find the cause in `rfq/`.
- Do not change the reference, the checker's expected lists, or the spec to make a check pass. If a check
  looks wrong, say why and ask.
