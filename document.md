# Ferguson RFQ Automation: Features and Architecture

> Status: design document. It describes the system as planned in `PLAN.md` and `spec.md`. The parts are
> built in the order given at the end.

## 1. What the system does

Ferguson receives **RFQ (Request for Quote) emails**. Each one lists product IDs, which can appear in four
ways:

- in the email body;
- in an Excel attachment;
- mixed with competitor part numbers;
- buried inside a forwarded email.

The system turns each email into:

- a filled **`RFQ.xlsx`** built from `templates/rfq_template.xlsx`, with one row per product;
- a **Sources** sheet with one row per filled value, showing where it came from;
- a **Notes** sheet recording what happened to each item;
- a **Summary** sheet with the fill rate, quality flags and AI suggestions;
- a **reply email** (`reply.eml`) sent in the same thread as the request.

The base is deterministic: **same email in, same Excel out, every time.** AI is used only to make
suggestions. It never changes a value.

---

## 2. System architecture

```mermaid
flowchart LR
    subgraph Inputs
        GM["Gmail inbox"]
        UP["Dashboard upload / sample emails"]
    end

    subgraph Entry["Entry points"]
        MB["mailbot.py<br/>IMAP poll every 30 s"]
        API["FastAPI app/<br/>runs, review, health"]
    end

    subgraph Core["rfq/ core library (no web imports)"]
        BUILD["build.py CLI"]
        PIPE["pipeline.py<br/>fixed stage order"]
        EXT["extract/<br/>email, attachments, patterns"]
        SRC["sources/<br/>live, spec_sheet, catalog, merge"]
        QA["quality/<br/>units, rules, llm, summary"]
        OUT["output/<br/>workbook, style, reply"]
        REV["review/state.py"]
    end

    subgraph External
        CHR["Chrome on port 9333<br/>ferguson.com"]
        PDF["api.ferguson.com<br/>spec sheet PDFs"]
        AOAI["Azure OpenAI"]
    end

    subgraph Data["Local data"]
        CAT["product_catalog.json<br/>+ sources CSV"]
        SPC["data/spec_cache/<br/>bundled PDFs"]
        TPL["rfq_template.xlsx"]
    end

    subgraph Files["out/&lt;run&gt;/"]
        F1["RFQ.xlsx"]
        F2["reply.eml"]
        F3["run.json, review.json"]
        F4["events.jsonl, run.log"]
    end

    WEB["React web/<br/>dashboard + review UI"]

    GM --> MB
    UP --> WEB --> API
    MB -->|subprocess| BUILD
    API -->|subprocess| BUILD
    BUILD --> PIPE
    PIPE --> EXT --> SRC --> QA --> OUT
    SRC --> CHR
    SRC --> PDF
    SRC --> SPC
    SRC --> CAT
    QA --> AOAI
    OUT --> TPL
    OUT --> Files
    API --> Files
    API --> REV --> OUT
    MB -->|send reply| GM
    API -->|approve & send| GM
```

### Layers

| Layer | Folder | Responsibility |
|---|---|---|
| Core library | `rfq/` | Email → `RunResult` → files. Knows nothing about the web. |
| CLI shims | `rfq/build.py`, `rfq/chrome.py` | Fixed command-line contract used by `mailbot.py` and the deck. |
| Email bot | `mailbot.py` | Watches Gmail, runs a build per RFQ email, sends or holds the reply. |
| API | `app/` | FastAPI JSON API, SSE progress and the review actions. Serves `web/dist`. |
| Frontend | `web/` | React + Vite + TypeScript + shadcn/ui dashboard. |
| Tests | `tests/` | Offline unit and integration tests, run in CI on Linux and Windows. |

---

## 3. End-to-end flow of one RFQ email

```mermaid
flowchart TD
    A["RFQ email arrives"] --> B["mailbot.py picks it up<br/>subject contains RFQ"]
    B --> C["python rfq/build.py email.eml --out out"]
    C --> D["Extract IDs"]
    D --> E["Look up each item"]
    E --> F["Fill RFQ, Sources, Notes"]
    F --> G["Quality Agent<br/>units, rule flags, AI suggestions"]
    G --> H["Write RFQ.xlsx, reply.eml, run.json"]
    H --> I{"run.json status"}
    I -->|ready| J["Send reply in same thread"]
    I -->|needs_review| K["Hold: no reply yet<br/>notify reviewer"]
    K --> L["Reviewer resolves flags in dashboard"]
    L --> M["Approve & send"]
    M --> N["Regenerate outputs<br/>without review marks"]
    N --> J
    C -.->|build crashed or timed out| O["Fallback reply:<br/>a person will follow up"]
    J --> P["Mark email Seen"]
    K --> P
    O --> P
```

---

## 4. Pipeline stages in detail

```mermaid
flowchart LR
    S1["1 Read<br/>extract/"] --> S2["2 Look up<br/>sources/"] --> S3["3 Fill<br/>output/workbook"] --> S4["4 Quality<br/>quality/"] --> S5["5 Reply<br/>output/reply"]
```

Each stage writes progress events to `events.jsonl`. The dashboard stepper is driven by these events over
SSE.

### 4.1 Extraction (`rfq/extract/`)

- **Text sources:**
  - every `text/plain` part, falling back to stripped HTML;
  - forwarded `message/rfc822` emails;
  - `.xlsx`, `.xlsm` and `.csv` attachments. In a sheet, the column whose header matches
    `item|product|sku|part|id` is used. If no header matches, any cell matching the ID pattern is used.
- **Ferguson IDs:** `(?<![\w-])#?(\d{5,7})(?![\w-])`. This handles `#5106926` and `1844552 , 4783795`,
  and ignores `x 40 rolls`.
- **Competitor codes:** hyphenated alphanumeric tokens (case-insensitive), e.g. `17783-79-3000`, `31-024`,
  `MTX-4409-XQ`. These are kept and reported as **Not found**.
- **Context filter:** a number right after `tel/phone/fax/zip/pin/po/order/invoice/qty` is skipped.
- **Order:** IDs keep their order of first appearance, and duplicates are dropped with a Note.
- **Limits:** at most 300 items, attachments up to 10 MB, and up to 5,000 rows per sheet.

```mermaid
flowchart TD
    E["email.eml"] --> W["MIME walk"]
    W --> T["text/plain parts"]
    W --> H["text/html → strip tags"]
    W --> R["attached emails → recurse"]
    W --> X["attachments"]
    X --> XL[".xlsx / .xlsm<br/>openpyxl read-only"]
    X --> CS[".csv"]
    X --> BAD[".xls, protected, corrupt<br/>→ Note: please resend"]
    T & H & R & XL & CS --> P["patterns.py<br/>ID + competitor regexes<br/>+ context filters"]
    P --> L["Ordered, de-duplicated item list"]
```

### 4.2 Lookup and fallback (`rfq/sources/`)

```mermaid
flowchart TD
    I["Item"] --> M{"Mode"}
    M -->|live| LV["Live page via Chrome CDP<br/>page must show Item #id"]
    M -->|no-browser| SP
    M -->|offline| CT

    LV -->|found| MG
    LV -->|blocked, timeout,<br/>wrong product, 404| CT["Catalog<br/>product_catalog.json"]
    CT --> MG["merge.py<br/>live wins; differences → Notes"]
    MG --> SP["Spec sheet PDF<br/>fills blank cells only"]
    SP --> DL{"Download OK?"}
    DL -->|yes| RD["pypdf text + regexes<br/>Thickness, ASTM, OSHA, Material"]
    DL -->|no| BC["Bundled copy<br/>data/spec_cache/"]
    BC --> RD
    BC -->|missing| SK["Skip + Note"]
    RD --> RES["Cells with value, source type,<br/>confidence, URL"]
    SK --> RES
    CT -->|not in catalog| NF["Lookup Status = Not found<br/>+ reason in Notes"]
```

| Source | `source_type` | Confidence | Notes |
|---|---|---|---|
| Live ferguson.com page | `ferguson_page` | high | Up to 3 tabs in parallel; results re-sorted into email order. 8-minute live budget; stops after 3 blocks in a row. |
| Spec sheet PDF | `spec_sheet` | medium | Only fills blanks. Keeps the page number and text snippet. |
| Catalog | carried over from CSV | as given | Always available; used by `--offline` and as the fallback. |
| Human reviewer | `human_review` | high | Recorded with reviewer name and time. |

### 4.3 Run modes

| Mode | Flag | Sources used | Use |
|---|---|---|---|
| Live (default) | none | live page → spec PDF → catalog | Demo laptop with Chrome open |
| No browser | `--no-browser` | spec PDF (bundled fallback) → catalog | Azure, servers |
| Offline | `--offline` | catalog only, no network | Tests; reproduces the reference exactly |
| Replay | `--replay` | cached pages and PDFs from `out/.cache/` | Demo with bad Wi-Fi or a blocked site |
| No quality | `--no-quality` | skips Part B | Debugging |

### 4.4 Workbook output (`rfq/output/`)

- **RFQ sheet:**
  - one row per item in email order; all values are strings;
  - `Image` is the formula `=IMAGE("url")` and `Picture` is the URL;
  - `Lookup Status` is `Found` or `Not found`.
- **Sources sheet:** one row per filled cell, in template column order. Image and Picture reuse the picture
  source.
- **Notes sheet:** `product_id | note`, sorted by item, then by stage.
- **Summary sheet:**
  - KPIs, fill rate per column (bar chart) and the request lines with quantities;
  - risk alerts, the flags table and the AI suggestions table.
- **Styling (`style.py`):** formatting only, never a value change.
  - Branded header, frozen panes, autofilter.
  - A status colour together with text.
  - A confidence colour scale on Sources.
- **Safety:**
  - text starting with `=` stays text;
  - illegal characters are stripped;
  - the file is saved atomically, with a retry if it is locked in Excel.

---

## 5. Quality Agent (Part B)

```mermaid
flowchart LR
    R["Filled rows"] --> U["units.py<br/>Length ft, Width in,<br/>Thickness mil, Weight lb"]
    U --> RL["rules.py<br/>missing, odd values,<br/>description mismatch"]
    RL --> LLM["llm.py<br/>Azure OpenAI<br/>advisory only"]
    LLM --> SM["summary.py<br/>fill rate, flags,<br/>AI suggestions"]
    RL --> ST{"Any unresolved<br/>high-severity rule flag?"}
    ST -->|yes| NR["Needs human review"]
    ST -->|no| RD["Ready"]
```

- **Unit normalisation:** a bare `1000` becomes `1000 ft`. The Sources row keeps its origin and adds "unit
  normalised", and every conversion gets a Note.
- **Rule flags:** each has a rule name and a severity. `high` is used only for probable errors: a missing
  key value on a Found row, or a description that contradicts Width, Length or Color.
- **LLM review:**
  - one call per found row, with only the row JSON and its sources (never the raw email);
  - structured output; a flag must quote the cell value it questions, or it is dropped;
  - **it never changes a value or the status**;
  - if the call fails or there are no credentials, it is skipped and the Summary says so.

---

## 6. Run status lifecycle

```mermaid
stateDiagram-v2
    [*] --> processing
    processing --> ready: no high-severity rule flags
    processing --> needs_review: high-severity rule flag
    processing --> failed: build crashed / timed out
    ready --> sent: mailbot sends reply
    needs_review --> approved: reviewer clicks Approve & send
    approved --> sent: SMTP accepted
    approved --> approved: SMTP failed, Retry
    failed --> fallback_sent: "a person will follow up"
    sent --> [*]
    fallback_sent --> [*]
```

---

## 7. Human-in-the-loop review

```mermaid
sequenceDiagram
    participant C as Customer
    participant G as Gmail
    participant MB as mailbot.py
    participant B as rfq/build.py
    participant R as Reviewer
    participant W as Web UI
    participant A as FastAPI

    C->>G: RFQ email
    MB->>G: IMAP poll
    MB->>B: run build (subprocess)
    B-->>MB: exit 0, run.json = needs_review
    MB->>G: mark Seen (no reply yet)
    MB-->>R: optional notice "RFQ from X needs review (3 flags)"
    R->>W: open Review page
    loop each flag
        R->>W: Keep / Edit / Clear (keyboard)
        W->>A: POST /api/runs/{id}/review
        A->>A: update review.json (atomic, versioned)
    end
    R->>W: Preview customer email
    R->>W: Approve & send
    W->>A: POST /api/runs/{id}/approve
    A->>B: regenerate RFQ.xlsx + reply without review marks
    A->>G: send one in-thread reply (mailbot.make_reply)
    G-->>C: Reply + RFQ.xlsx
    A-->>W: status = sent
```

**Review page:**
- **Layout:** flags grouped by item, high severity first, with a "3 of 7 resolved" progress line.
- **Actions:** Keep value, Edit, or Clear (unknown). An edit or clear adds a `human_review` Sources row.
- **Keyboard:** ↑/↓ to move, Enter to keep, E to edit, Del to clear, Ctrl+Z to undo.
- **Approve & send:** disabled until every high-severity flag is resolved, and the button says why.

---

## 8. Dashboard and API

```mermaid
flowchart TD
    subgraph Web["web/ React app"]
        RP["Runs page<br/>tabs: Needs review, Processing, Sent, Failed"]
        RUN["Run page<br/>Items, Email, Sources, Activity"]
        RV["Review page<br/>two panes + keyboard"]
        NEW["New RFQ<br/>drop .eml or pick a sample, choose mode"]
        DG["Diagnostics<br/>health + Self-check"]
    end
    subgraph API["app/ FastAPI"]
        E1["GET /api/runs"]
        E2["GET /api/runs/{id}"]
        E3["GET /api/runs/{id}/events (SSE)"]
        E4["POST /api/runs"]
        E5["POST /api/runs/{id}/review"]
        E6["POST /api/runs/{id}/approve"]
        E7["GET /api/runs/{id}/files/{name}"]
        E8["GET /api/health, /api/samples"]
    end
    RP --> E1
    RUN --> E2
    RUN --> E3
    RUN --> E7
    NEW --> E4
    RV --> E5
    RV --> E6
    DG --> E8
    E4 --> RN["services/runner.py<br/>build.py subprocess,<br/>one live run at a time"]
    E6 --> ML["services/mailer.py"]
```

- **Health bar:** Chrome Connected/Offline · AI review On/Off · Inbox Watching/Off.
- **Item cards:** image, ID, description, status badge, source label, price · stock, flag count. Clicking a
  card opens a side sheet with every field and its source; spec values also show the PDF page and snippet.
- **Design rules:**
  - dark theme by default, with a light theme;
  - every status has an icon **and** text;
  - 150-200 ms fades only; reduced motion is respected;
  - WCAG AA contrast and full keyboard access.

---

## 9. Customer reply

The reply is multipart (HTML + plain text) with `RFQ.xlsx` attached. It contains:

- a summary line, e.g. "Your RFQ for 7 items is attached: 5 matched, 2 need your input.";
- a counts line, e.g. "Products found: 5 of 7. Not found: 2.";
- an item table: #, Item, Description, Status, Unit price, Availability;
- "Items we couldn't match", each with a reason and a next step, e.g. "Did you mean 9677531?";
- a quality line in buyer words, e.g. "Quality check: every value checked. 3 measurements converted to
  standard units (ft, in, mil, lb). 2 values are worth a second look; they are listed on the Summary
  sheet." (or "No issues found."; after a review: "Quality check: checked by our team.");
- "Every value's source is on the Sources sheet."

It **never** contains internal words (flag, rule, severity), fill rates, review links, the word "AI", or "DRAFT".

---

## 10. Failure handling

Principle: **a bad input or a broken source makes the RFQ smaller; it never makes the run fail.**

```mermaid
flowchart TD
    P["Problem occurs"] --> Q{"Where?"}
    Q -->|bad input / attachment| N1["Skip part, Note,<br/>continue"]
    Q -->|browser down| N2["Probe once at start,<br/>switch to no-browser,<br/>one warning"]
    Q -->|page blocked / timeout| N3["Catalog fallback + Note;<br/>stop live after 3 blocks"]
    Q -->|PDF fails| N4["Bundled copy,<br/>else skip + Note"]
    Q -->|LLM fails| N5["Skip AI for row,<br/>rule flags still run"]
    Q -->|kit broken:<br/>template/catalog missing| N6["exit 1 + error.txt"]
    Q -->|bad CLI usage| N7["exit 2"]
    N1 & N2 & N3 & N4 & N5 --> OK["exit 0:<br/>RFQ.xlsx + reply.eml written"]
```

| Exit code | Meaning |
|---|---|
| `0` | RFQ.xlsx and reply.eml were written, possibly with warnings |
| `1` | The kit itself is broken (template or catalog) and nothing could be written |
| `2` | Usage error: missing `.eml` or bad flags |

**Mailbot hardening:**
- Each email is wrapped in try/except/finally.
- On failure, the bot sends the "a person will follow up" reply.
- The email is **always** marked `\Seen`, so one bad email can never block the inbox.

Problems are recorded in three places: the **Notes** sheet (the buyer sees it), **`run.log`** (warnings and
tracebacks), and the printed summary line (`warnings: N`).

---

## 11. Determinism guarantees

| Rule | How |
|---|---|
| AI is advisory | Status, highlights and reply wording come from rule flags only |
| Stable order | Parallel lookups are re-sorted into email order; Notes sorted by item, then stage |
| Spec PDFs | Bundled fallback copies make `--no-browser` repeatable |
| No timings in outputs | Timings appear only in the dashboard, console and `run.log` |
| Values, not bytes | Tests compare cell values; openpyxl timestamps may differ |
| Human edits | The only change allowed after the build, recorded as a `human_review` source |

---

## 12. Data model

```mermaid
classDiagram
    class RunResult {
        run_id
        sender
        subject
        mode
        status: RunStatus
        items: Item[]
        notes: Note[]
        flags: Flag[]
        ai_suggestions: Flag[]
    }
    class Item {
        index
        product_id
        kind: ferguson | competitor
        qty
        lookup_status: Found | Not found
        cells: dict~column, Cell~
    }
    class Cell {
        value
        source_type
        confidence
        source
    }
    class Note {
        product_id
        stage
        text
    }
    class Flag {
        id
        product_id
        column
        value
        issue
        rule
        severity
        resolved
    }
    class RunStatus {
        processing
        ready
        needs_review
        approved
        sent
        failed
        fallback_sent
    }
    RunResult "1" --> "*" Item
    RunResult "1" --> "*" Note
    RunResult "1" --> "*" Flag
    Item "1" --> "*" Cell
    RunResult --> RunStatus
```

The same model is used by every pipeline stage, by `run.json`, and by the API (`app/schemas.py`
mirrors it).

---

## 13. Deployment

```mermaid
flowchart LR
    subgraph Laptop["Demo laptop: Linux or Windows"]
        CH["Chrome :9333"]
        MBL["mailbot.py"]
        APPL["uvicorn app.main:app"]
    end
    subgraph Azure
        AS["App Service, Linux<br/>FastAPI + web/dist<br/>RFQ_MODE=no-browser"]
        ST["/home/data/out<br/>persistent"]
        AO["Azure OpenAI"]
        KV["App Settings / Key Vault<br/>secrets"]
    end
    GH["GitHub Actions CI<br/>pytest on ubuntu + windows<br/>Node: tsc, eslint, vitest, build"]

    MBL --> CH
    APPL --> CH
    AS --> ST
    AS --> AO
    AS --> KV
    GH -->|az webapp up| AS
```

- **Cross-platform rules:**
  - `pathlib` paths built from `ROOT`, and explicit UTF-8 everywhere (`utf-8-sig` for the CSVs);
  - Windows-safe folder names, with atomic Excel saves and a lock retry;
  - a Chrome/Edge launcher in `rfq/chrome.py`.
- **Secrets** live in `.env` locally and in App Settings on Azure: `BOT_EMAIL`, `BOT_PASSWORD`,
  `AZURE_OPENAI_*`, `REVIEW_NOTIFY_EMAIL`, `DASHBOARD_URL`.

---

## 14. Extra features (ranked)

1. **Quantities and estimated quote value.** A request-lines table with line totals.
2. **Sourcing risk alerts.** Out of stock, stale catalog prices, discontinued or Not found items.
3. **"Did you mean…?"** For near-miss IDs. Only a suggestion, never substituted automatically.
4. **Compliance matrix.** ANSI / OSHA / ASTM / UL per product.
5. **Follow-up emails in the same thread.** "Also add 5106899" produces version 2 of the RFQ.
6. **More attachment types.** PDF item lists, and IDs in the subject line.
7. **Prompt-injection safety.** The LLM sees product data only, and every flag must quote its cell.
8. **Showcase extras:**
   - page cache + replay;
   - fill rate before vs after;
   - time saved;
   - one-click Self-check;
   - parallel tabs;
   - Ferguson alternatives for competitor parts.

---

## 15. Build order

```mermaid
flowchart TD
    B0["0 Housekeeping: skills by OS"] --> B1["1 Base offline + tests"]
    B1 --> B2["2 mailbot.py patch"]
    B2 --> B3["3 API + web skeleton"]
    B3 --> B4["4 Live + spec sources, replay"]
    B4 --> B5["5 Styled Excel + reply"]
    B5 --> B6["6 Quality Agent + review flow"]
    B6 --> B7["7 Mailbot end to end, Linux + Windows"]
    B7 --> B8["8 Azure deploy + showcase"]
    B8 --> B9["9 Ranked extras"]
```

## 16. How correctness is checked

- **`test_reference`:** email 1 offline matches `reference/email-1 reference output.xlsx` cell for cell
  (6 rows, 105 Sources rows, status Ready).
- **`test_extract`:** the four expected ID lists. Unknown and competitor items show as Not found and are
  never dropped.
- **`test_determinism`, `test_failures`, `test_quality`:** repeatability, the broken-input fixtures, and the
  AI staying advisory.
- **`test_review_state`, `test_hold_flow`:** review decisions, and the hold → approve → reply path.
- **Web:** vitest unit tests and a Playwright end-to-end test of the review flow.
- **Skill:** `/rfq-verify` runs the acceptance checks from `spec.md`.
