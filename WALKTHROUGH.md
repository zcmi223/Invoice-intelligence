# WALKTHROUGH: Rebuild `invoice-intelligence` From Scratch

This document teaches you to recreate the entire project yourself, step by
step. It's written for a smart beginner: you can follow instructions and
write basic Python, but you've never used Roboflow or built a computer-vision
project.

By the end you will understand every file, every Roboflow concept the project
touches, and *why* each decision was made.

**Time estimate:** 2–3 hours (faster if you skip the optional live-API section).

---

## Part 0 — Concepts you need first

### What Roboflow is

Roboflow is a platform for building with **computer vision** (teaching
computers to understand images). Five concepts matter here:

| Concept | What it is | Analogy |
|---|---|---|
| **Project** | A container for one vision task (e.g. "find invoice fields") | A dbt project / a spreadsheet workbook |
| **Dataset** | Labeled images you upload and annotate | Your raw source tables |
| **Model** | A trained neural net that finds things in images | A trained forecast model |
| **Workflow** | A no-code chain of *blocks* (detect → crop → OCR → output) that runs as one API call | An ETL pipeline / DAG |
| **Inference** | Running a model or workflow on a new image to get predictions | Running the forecast on new actuals |

The key insight: **Workflows let you compose vision steps without training
anything.** Our pipeline needs text off an invoice — Roboflow already ships an
**OCR block** (`roboflow_core/ocr@v1`) that does that. We chain it in a
workflow and call the whole chain from Python with one function.

### How the pieces fit

```text
You (Python) ──HTTP──▶ Roboflow hosted Inference API ──▶ runs your Workflow
                                                              │
Python ◀──JSON (OCR text + detected regions)──────────────────┘
```

The Python package that speaks this HTTP API is **`inference-sdk`**
(`pip install inference-sdk`). Its main class is `InferenceHTTPClient`, and
the method we use is `run_workflow(...)`.

### Prerequisites

- **Python 3.10+** — check with `python3 --version`
- **pip** — check with `pip --version`
- **A GitHub account** (to publish the repo at the end)
- **A free Roboflow account** — sign up at
  [app.roboflow.com](https://app.roboflow.com). Your **API key** lives at
  *Settings → API* once you're logged in. (You only need this for Part 6;
  everything before that runs without it.)
- A terminal and a text editor. That's it — no GPU, no Docker.

---

## Part 1 — Scaffold the project

**Why:** a predictable layout means anyone (including future-you) can find
things. `src/` holds the pipeline stages, `scripts/` holds one-off tooling,
`images/` and `demo/` hold data, `output/` holds generated artifacts.

```bash
mkdir -p invoice-intelligence/{src,images,demo/mock_outputs,scripts,output}
cd invoice-intelligence
touch src/__init__.py
```

**What success looks like:** `ls -R` shows the five directories.

Now create the dependency and config files:

**`requirements.txt`** — the only three packages we need:

```text
inference-sdk>=0.9   # Roboflow's official Python client (live mode)
pillow>=10.0         # image generation for synthetic samples
python-dotenv>=1.0   # loads .env files into environment variables
```

**Why these and nothing else:** the heavy computer-vision work happens on
Roboflow's servers, not your laptop — that's the whole point of the hosted
Inference API. No torch, no CUDA, no 2 GB downloads.

**`.env.example`** — a template for secrets (you'll copy it to `.env` later):

```text
ROBOFLOW_API_KEY=
ROBOFLOW_API_URL=https://serverless.roboflow.com
ROBOFLOW_WORKSPACE=
ROBOFLOW_WORKFLOW_ID=invoice-extraction
```

**`.gitignore`** — so secrets and junk never reach GitHub:

```text
.env
__pycache__/
*.py[cod]
.venv/
.DS_Store
```

**Why `.env` + `.gitignore` matters:** API keys are passwords. They live in
`.env` (on your machine only), and `.gitignore` guarantees git won't commit
them. The `.env.example` shows *which* variables exist without containing
values — this is the industry-standard pattern.

Install dependencies and verify:

```bash
pip install -r requirements.txt
python3 -c "import PIL, dotenv; print('deps ok')"
```

**What success looks like:** `deps ok` printed, no errors. (If `inference-sdk`
isn't needed yet, that's fine — it's only imported when a key is present.)

---

## Part 2 — Generate synthetic sample invoices

**Why synthetic data:** real invoices contain real vendor/employee info — you
never commit those to a public repo. Generating fakes with PIL gives us
realistic images with *known* contents, so we can verify the parser is correct.

Create **`scripts/generate_samples.py`**. The important design points:

1. **Render with PIL** — white canvas, black text, a vendor header, invoice
   number, date, a line-item table, subtotal/tax/total. Five invoices with
   different vendors, dates, and amounts.
2. **Bake in three data-quality scenarios** (these are what the anomaly
   detector will catch later):
   - `invoice_03`: **duplicate** invoice number of `invoice_01`
   - `invoice_04`: **totals mismatch** — line items + tax ≠ printed total
   - `invoice_05`: **outlier amount** — ~12× the batch median
3. **Emit a mock Roboflow response** per image into
   `demo/mock_outputs/<name>.json`, shaped exactly like the canonical
   extraction dict the live path produces:

```json
{
  "workflow": "invoice-extraction",
  "image": "invoice_01.png",
  "outputs": {
    "ocr_text": "<the text an OCR block would read>",
    "regions": [
      {"label": "vendor_block", "text": "...", "bbox": [x, y, w, h]},
      ...
    ]
  }
}
```

**Why the mock mirrors the live shape:** the rest of the pipeline
(normalize → analyze → report) can't tell demo from live. One code path,
two data sources — that's what makes demo mode honest instead of fake.

Run it:

```bash
python scripts/generate_samples.py
```

**What success looks like:**

```text
wrote images/invoice_01.png + demo/mock_outputs/invoice_01.json
wrote images/invoice_02.png + demo/mock_outputs/invoice_02.json
wrote images/invoice_03.png + demo/mock_outputs/invoice_03.json
wrote images/invoice_04.png + demo/mock_outputs/invoice_04.json
wrote images/invoice_05.png + demo/mock_outputs/invoice_05.json
```

Open one PNG to confirm it looks like an invoice.

---

## Part 3 — Configuration (`src/config.py`)

**Why a config module:** every setting lives in one place, read from
environment variables. The single most important line:

```python
LIVE_MODE = bool(ROBOFLOW_API_KEY and ROBOFLOW_WORKSPACE)
```

**Why:** the pipeline must *degrade gracefully*. No key → demo mode, no crash,
no half-broken API call. This one boolean is the entire live/demo switch, and
`main.py` only flips it when `--demo` is passed explicitly.

---

## Part 4 — Extraction (`src/extract.py`): the Roboflow integration

This is the heart of the project. Its contract:

```python
extract_invoice(image_path) -> {
    "source_image": str,
    "mode": "live" | "demo",
    "ocr_text": str,        # full-page text from the workflow
    "regions": [...],       # detected regions (may be empty)
}
```

### The live path — what the API calls do

```python
from inference_sdk import InferenceHTTPClient

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",  # Roboflow's hosted endpoint
    api_key=ROBOFLOW_API_KEY,
)
result = client.run_workflow(
    workspace_name=ROBOFLOW_WORKSPACE,  # your workspace slug
    workflow_id="invoice-extraction",   # the workflow's URL slug (NOT its doc ID)
    images={"image": image_path},       # local path, base64, or https:// URL
    parameters={"confidence": 0.35},    # must match the workflow's declared params
)
```

Line by line:

- **`InferenceHTTPClient`** — a thin HTTP client. `api_url` points at
  Roboflow's **serverless** hosted inference (as opposed to
  `http://localhost:9001`, which you'd use with a self-hosted Inference
  server). Serverless means zero infrastructure on your side.
- **`run_workflow`** — executes your whole workflow remotely and returns a
  **list with one dict per input image**. Each dict is keyed by whatever
  **output names you declared** in the workflow builder — which is why the
  code reads `output.keys()` instead of hard-coding names. If you rename an
  output in the Roboflow UI, the Python still works.
- **`images={"image": ...}`** — the key (`"image"`) must match the workflow's
  input block name. Values can be local paths, base64 strings, or `https://`
  URLs (plain `http://` is rejected).
- **`parameters`** — runtime knobs the workflow declares (like a stored
  procedure's arguments). Anything undeclared is ignored; wrong types fail at
  runtime.

The response mapping then normalizes Roboflow's raw output into our canonical
shape: strings containing "ocr"/"text" become `ocr_text`; lists of
detections become `regions` with `label`/`text`/`bbox`.

### The demo path

Loads `demo/mock_outputs/<name>.json` and returns the same canonical shape.
If a mock is missing, it raises a clear `FileNotFoundError` telling you to
run the generator — fail loudly, not silently.

### The workflow you'd build in the Roboflow app

(You'll do this for real in Part 6. Conceptually:)

1. **Input block** — accepts the invoice image.
2. **OCR block** (`roboflow_core/ocr@v1`) — reads every text string on the page.
3. **Object Detection → Dynamic Crop** *(optional upgrade)* — a trained
   detector finds the vendor block and totals block; each crop is re-OCR'd for
   higher accuracy on the fields that matter.
4. **Output block** — exposes `ocr_text` and `regions` to the API response.

---

## Part 5 — Normalization (`src/normalize.py`): data hygiene

**Why this layer exists:** OCR output is *dirty* — inconsistent labels
("Total", "TOTAL DUE", "Amount Due"), varied date formats, stray whitespace.
Finance systems need typed fields. This module is the RevOps "data hygiene"
layer: garbage in → validated records, or explicit warnings.

The output record:

```python
{
  "vendor": str | None, "invoice_number": str | None, "date": "YYYY-MM-DD" | None,
  "line_items": [{"description", "qty", "amount"}],
  "subtotal": float | None, "tax": float | None, "total": float | None,
  "parse_warnings": [...],   # every field we COULD NOT extract
}
```

Key techniques and *why*:

- **Regexes with multiple label variants** for invoice number, dates
  (`YYYY-MM-DD`, `MM/DD/YYYY`, `Month D YYYY`), and money fields.
- **The "TOTAL DUE wins" rule:** match `total\s*due` *before* bare `total`,
  otherwise "Subtotal" contains "total" and you'd grab the wrong number.
  (The code uses a negative lookbehind `(?<!sub)total` as a backstop.)
- **The invoice-number trap we actually hit:** the naive pattern
  `(?:invoice\s*#|...|inv\.?)` matched the bare word "INVOICE" via the
  `inv\.?` alternative and captured `"OICE"`. The fix: require the label to
  include `#` or `No.` — `(?:invoice|inv)\s*(?:#|no\.?)`. Lesson: **test your
  regexes against real strings**; OCR parsing is where silent bugs live.
- **Never invent data:** every unparseable field appends to
  `parse_warnings` instead of being guessed. Downstream, warnings become
  anomaly flags. This is the single most "finance-brain" decision in the
  project — like a reconciliation that *fails loudly* instead of plugging.

---

## Part 6 — Analysis (`src/analyze.py`) and reporting (`src/report.py`)

### Analysis

Aggregations a finance leader actually wants:

- **Spend by vendor / month / category** — category comes from a keyword map
  (`CATEGORY_KEYWORDS`); anything unmatched lands in "Other" rather than being
  forced into a wrong bucket.
- **Three anomaly rules:**
  1. `duplicate_invoice_number` — same invoice # on two images → possible
     double-billing. (This is *the* classic AP-fraud control.)
  2. `totals_mismatch` — Σ(line items) + tax ≠ printed total (tolerance $0.01).
  3. `outlier_amount` — total > 3× the batch median → "verify before paying."
- Parse warnings from the normalize step are carried through as flags too.

**Why median, not mean, for the outlier rule:** one $8,900 invoice in a batch
of $200 ones would drag a mean up and hide itself; the median doesn't move.
Robust statistics 101, and exactly the kind of choice worth explaining in an
interview.

### Reporting

`src/report.py` renders the analysis dict to Markdown: summary stats, three
pivot tables, the anomaly list, and per-invoice detail. Markdown was chosen
over HTML/PDF deliberately — it renders natively on GitHub, diffs cleanly in
git, and pastes into Slack/Notion without conversion.

---

## Part 7 — Wire it together (`main.py`) and run the demo

`main.py` is a thin CLI orchestrator:

```text
extract → normalize → analyze → report
```

```bash
python main.py --demo --output output/report.md
```

**What success looks like:**

```text
invoice-intelligence | mode: demo (mocked extraction) | 5 image(s)
  extracting  invoice_01.png ...
  ...
  normalized  5/5 invoice(s)
  anomalies   3 flag(s)
  report      output/report.md
```

Open `output/report.md` and verify: 5 invoices, $11,874.56 total, and exactly
three anomaly flags — `duplicate_invoice_number` (INV-2026-0841),
`totals_mismatch` (INV-2026-1022), `outlier_amount` (INV-2026-1033). If you
see those three, every stage works.

---

## Part 8 — Go live with your real Roboflow account

1. **Get an API key:** log in at
   [app.roboflow.com](https://app.roboflow.com) → *Settings → API* → copy the
   key. (Free tier includes hosted inference credits.)
2. **Find your workspace slug:** it's in your workspace URL —
   `app.roboflow.com/<workspace-slug>`.
3. **Build the workflow:** *Workflows → Create Workflow* →
   - Add an **Input** block (name it `image`).
   - Add an **OCR** block (`roboflow_core/ocr@v1`), wired to the input.
   - *(Optional)* Add an **Object Detection** model block + **Dynamic Crop**
     block targeting the vendor/totals regions, then OCR the crops.
   - Add an **Output** block exposing the OCR text (name it `ocr_text`) and
     any detections.
   - Note the workflow's **URL slug** (e.g. `invoice-extraction`).
4. **Configure locally:**

```bash
cp .env.example .env
# edit .env: ROBOFLOW_API_KEY, ROBOFLOW_WORKSPACE, ROBOFLOW_WORKFLOW_ID
```

5. **Run against real invoices:**

```bash
python main.py --input /path/to/your/invoices --output output/report.md
```

**What success looks like:** `mode: live (Roboflow API)` in the console
banner, and the report reflects *your* documents. If the workflow output keys
differ from what you declared, `extract.py` reads them dynamically — check the
console for which keys it found.

---

## Part 9 — Publish to GitHub

```bash
cd invoice-intelligence
git init -b main
git add .
git status          # confirm .env is NOT listed (it's gitignored)
git commit -m "Invoice intelligence pipeline: Roboflow OCR -> spend report"
```

Create the repo (via web UI or `gh`):

```bash
gh repo create invoice-intelligence --public \
  --description "Invoice images -> Roboflow computer vision -> anomaly-flagged spend reports"
git remote add origin https://github.com/<your-username>/invoice-intelligence.git
git branch -M main
git push -u origin main
```

**What success looks like:** the repo page shows `README.md` rendered, with
`src/`, `images/`, `demo/`, `scripts/` browsable — and no `.env` file
anywhere in the listing.

---

## Part 10 — What makes this project special (the teach-back)

If you only remember five things:

1. **It uses Roboflow the way Roboflow is meant to be used** — not a model
   trained from scratch, but a *Workflow*: composable blocks (OCR, detection,
   crop) executed with one `run_workflow` API call against hosted inference.
   That's the platform's core abstraction, and this project exercises it.
2. **The heavy lifting is serverless.** Your laptop never loads a neural net;
   `inference-sdk` is a thin HTTP client. This is the modern pattern for
   applied CV — and why the requirements file is three lines, not thirty.
3. **Demo mode is honest engineering.** The mock outputs mirror the real API
   shape, so one code path serves both. Reproducibility without credentials is
   what makes a portfolio project actually runnable by a hiring manager.
4. **The finance layer is where your background shows.** Duplicate-invoice
   detection, totals reconciliation, median-based outlier flags, "fail loudly"
   parsing — these are AP controls and data-hygiene instincts, expressed in
   code. That's the bridge between FP&A Zach and RevOps Zach.
5. **Every anomaly in the demo is deliberate and verifiable.** A reviewer can
   open the sample images, read the numbers, and confirm the flags are
   correct. Nothing is hand-waved.

Suggested next steps once you're comfortable: train a custom Roboflow
detection model on labeled invoice fields, add a human-review queue for
low-confidence extractions, and export the dataset to Parquet for Snowflake
ingestion.
