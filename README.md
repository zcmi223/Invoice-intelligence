# invoice-intelligence

Turn invoice and receipt **images** into a clean spend dataset and an
anomaly-flagged finance report — powered by [Roboflow](https://roboflow.com)
computer vision.

```text
invoice images ──▶ Roboflow Workflow ──▶ normalize ──▶ analyze ──▶ report.md
                   (detect + OCR)       (data hygiene)  (spend + anomalies)
```

## What it does

Drop a folder of invoice/receipt images in, get a finance-ready report out:

- **Extract** — each image runs through a Roboflow Workflow (object detection
  + OCR) that reads the vendor, invoice number, date, line items, and totals.
- **Normalize** — raw OCR text becomes typed, validated records. Anything the
  parser can't extract cleanly becomes an explicit warning, never a guess.
- **Analyze** — spend by vendor / month / category, plus anomaly detection:
  duplicate invoice numbers (double-billing), totals mismatches (line items +
  tax ≠ printed total), outlier amounts (>3× batch median).
- **Report** — a Markdown spend report with summary tables, flags, and
  per-invoice detail.

## Why this matters for Revenue Operations

| Pipeline stage | RevOps concern it addresses |
|---|---|
| Roboflow OCR extraction | **Pipeline automation** — replace manual invoice keying with a vision pipeline |
| Normalization + parse warnings | **Data hygiene** — dirty source data becomes validated records or explicit flags |
| Duplicate / mismatch / outlier flags | **Leakage & risk** — catch double-billing and errors before money moves |
| Spend by vendor / month / category | **Reporting inputs** — clean actuals feed forecasts and budget variance |
| Demo mode + `.env` config | **Reproducibility** — anyone can run the pipeline without credentials |

## Architecture

```text
images/*.png
      │
      ▼
┌─────────────┐     ┌──────────────────────────────────────────────┐
│  extract.py │────▶│ Roboflow Inference SDK (live)                │
└─────────────┘     │  InferenceHTTPClient.run_workflow(           │
      │             │    workspace_name, workflow_id="invoice-     │
      │             │    extraction", images={"image": path})      │
      │             │                                              │
      │             │  Demo mode: loads demo/mock_outputs/*.json   │
      │             │  (same shape a real workflow returns)        │
      └─────────────┴──────────────────────────────────────────────┘
      │
      ▼  canonical extraction dict {ocr_text, regions}
┌──────────────┐
│ normalize.py │  regex parsing → typed record {vendor, date,
└──────────────┘  items[], subtotal, tax, total} + parse_warnings
      │
      ▼
┌────────────┐
│ analyze.py │  aggregations + anomaly rules → analysis dict
└────────────┘
      │
      ▼
┌───────────┐
│ report.py │  → output/report.md
└───────────┘
```

## How the Roboflow integration works

The project uses Roboflow's **hosted Inference API** via the official
[`inference-sdk`](https://inference.roboflow.com/inference_helpers/inference_sdk/)
Python package — no GPU, no local model weights, no Docker required.

The `"invoice-extraction"` **Workflow** (built once in the Roboflow app) is a
chain of **blocks**:

1. **Input** — receives the invoice image.
2. **OCR** (`roboflow_core/ocr@v1`) — reads all text on the page.
3. **Object Detection → Dynamic Crop** — an optional trained detector finds key
   regions (vendor block, totals block); crops are re-run through OCR for
   higher accuracy on the fields that matter most.
4. **Output** — returns the OCR text plus detected regions as JSON.

At runtime, `src/extract.py` calls:

```python
from inference_sdk import InferenceHTTPClient

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=ROBOFLOW_API_KEY,
)
result = client.run_workflow(
    workspace_name=ROBOFLOW_WORKSPACE,   # your workspace slug
    workflow_id="invoice-extraction",    # the workflow URL slug
    images={"image": "images/invoice_01.png"},
    parameters={"confidence": 0.35},
)
```

`run_workflow` returns one dict per image, keyed by the workflow's declared
output names — the code reads `output.keys()` instead of hard-coding them, so
it adapts to whatever your workflow returns.

**No API key?** Demo mode loads pre-baked mock outputs from
`demo/mock_outputs/` that mirror the real workflow's shape, so the whole
pipeline runs end-to-end with zero setup.

## Quickstart (demo mode — no key needed)

```bash
git clone https://github.com/zcmi223/invoice-intelligence.git
cd invoice-intelligence
pip install -r requirements.txt

# (re)generate the 5 synthetic sample invoices + mock Roboflow outputs
python scripts/generate_samples.py

# run the full pipeline
python main.py --demo --output output/report.md
```

Expected output:

```text
invoice-intelligence | mode: demo (mocked extraction) | 5 image(s)
  extracting  invoice_01.png ...
  extracting  invoice_02.png ...
  extracting  invoice_03.png ...
  extracting  invoice_04.png ...
  extracting  invoice_05.png ...
  normalized  5/5 invoice(s)
  anomalies   3 flag(s)
  report      output/report.md
```

Open `output/report.md`: spend by vendor/month/category, plus the three
deliberate data-quality scenarios — a **duplicate invoice number**, a
**totals mismatch**, and an **outlier amount**.

## Going live with your own Roboflow account

1. Create a free account at [app.roboflow.com](https://app.roboflow.com) and
   copy your API key (Settings → API).
2. In the Roboflow app, create a Workflow named `invoice-extraction`:
   Input → OCR block → (optional) detection + Dynamic Crop → Output.
3. Copy `.env.example` to `.env` and fill in `ROBOFLOW_API_KEY`,
   `ROBOFLOW_WORKSPACE` (your workspace slug), and `ROBOFLOW_WORKFLOW_ID`.
4. Run against your own invoices:

```bash
python main.py --input /path/to/your/invoices --output output/report.md
```

## Project structure

```text
invoice-intelligence/
├── main.py                  # CLI: extract → normalize → analyze → report
├── requirements.txt         # inference-sdk, pillow, python-dotenv
├── .env.example             # Roboflow credentials template (never commit .env)
├── src/
│   ├── config.py            # env-based config; LIVE_MODE = key + workspace set
│   ├── extract.py           # Roboflow SDK workflow call / demo mock loader
│   ├── normalize.py         # OCR text → typed invoice record + warnings
│   ├── analyze.py           # aggregations + anomaly rules
│   └── report.py            # Markdown report renderer
├── scripts/
│   └── generate_samples.py  # renders 5 synthetic invoices + mock outputs (PIL)
├── images/                  # sample invoice images (synthetic, generated)
├── demo/mock_outputs/       # mock Roboflow workflow responses for demo mode
├── output/                  # generated reports (gitignored in real use)
└── WALKTHROUGH.md           # step-by-step: rebuild this entire project yourself
```

## Roadmap ideas

- Train a custom Roboflow object-detection model on labeled invoice fields
  (vendor block, totals block) to replace the generic OCR-only path.
- Confidence-threshold routing: low-confidence extractions go to a human
  review queue (the classic RevOps data-quality loop).
- Export the normalized dataset to CSV/Parquet for Snowflake ingestion.
- Trend analysis: month-over-month spend variance alerts for forecasting.

## Notes

- Sample invoices are **synthetic** (generated by `scripts/generate_samples.py`)
  — no real vendor data anywhere in this repo.
- Never commit `.env`. The `.gitignore` excludes it.
- Built by an FP&A analyst learning computer vision — see `WALKTHROUGH.md`
  for the full rebuild tutorial.
