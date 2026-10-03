"""
Generate synthetic invoice images and matching mock Roboflow workflow outputs.

This makes the project fully self-contained: `python main.py --demo` runs the
entire pipeline without a Roboflow API key, using these samples. Each sample
pair is:

    images/<name>.png              -- synthetic invoice rendered with PIL
    demo/mock_outputs/<name>.json  -- what the Roboflow workflow *would* return

The mock JSON mirrors the canonical extraction shape produced by
src/extract.py, so the downstream pipeline (normalize -> analyze -> report)
behaves identically in demo and live modes.

Deliberate data-quality scenarios are baked in for the anomaly detector:
  invoice_01  clean Acme Cloud Services invoice
  invoice_02  clean Bright Office Supply invoice
  invoice_03  DUPLICATE invoice number of invoice_01 (different date/amount)
  invoice_04  totals MISMATCH (line items + tax != printed total)
  invoice_05  unusually LARGE amount (outlier vs. the rest of the batch)
"""

import json
import os
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE, "images")
MOCK_DIR = os.path.join(BASE, "demo", "mock_outputs")

W, H = 900, 1150  # portrait invoice canvas


def _font(size):
    """Best-effort truetype font, falling back to PIL's default bitmap font."""
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_invoice(inv):
    """Render one invoice dict to a PNG. Returns the saved path."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title, f_head, f_body = _font(34), _font(22), _font(19)
    x, y = 60, 50

    d.text((x, y), inv["vendor"], font=f_title, fill="black")
    y += 55
    d.text((x, y), inv["vendor_address"], font=f_body, fill="black")
    y += 70

    d.text((x, y), "INVOICE", font=f_head, fill="black")
    y += 40
    d.text((x, y), f"Invoice #: {inv['number']}", font=f_body, fill="black")
    y += 30
    d.text((x, y), f"Date: {inv['date']}", font=f_body, fill="black")
    y += 30
    d.text((x, y), f"Bill to: {inv['bill_to']}", font=f_body, fill="black")
    y += 55

    d.line([(x, y), (W - x, y)], fill="black", width=2)
    y += 15
    d.text((x, y), f"{'Description':<34}{'Qty':>6}{'Amount':>14}", font=f_head, fill="black")
    y += 35
    for item in inv["items"]:
        d.text((x, y), f"{item['desc']:<34}{item['qty']:>6}{item['amount']:>14.2f}",
               font=f_body, fill="black")
        y += 30
    y += 15
    d.line([(x, y), (W - x, y)], fill="black", width=2)
    y += 20

    d.text((x, y), f"{'Subtotal:':>52} {inv['subtotal']:>10.2f}", font=f_body, fill="black")
    y += 30
    d.text((x, y), f"{'Tax (6%):':>52} {inv['tax']:>10.2f}", font=f_body, fill="black")
    y += 30
    d.text((x, y), f"{'TOTAL DUE:':>52} {inv['total']:>10.2f}", font=f_head, fill="black")

    path = os.path.join(IMG_DIR, inv["file"])
    img.save(path)
    return path


def ocr_text_for(inv):
    """The OCR text a Roboflow OCR block would read off the rendered image."""
    lines = [
        inv["vendor"],
        inv["vendor_address"],
        "INVOICE",
        f"Invoice #: {inv['number']}",
        f"Date: {inv['date']}",
        f"Bill to: {inv['bill_to']}",
        "Description Qty Amount",
    ]
    for item in inv["items"]:
        lines.append(f"{item['desc']} {item['qty']} {item['amount']:.2f}")
    lines += [
        f"Subtotal: {inv['subtotal']:.2f}",
        f"Tax (6%): {inv['tax']:.2f}",
        f"TOTAL DUE: {inv['total']:.2f}",
    ]
    return "\n".join(lines)


def mock_output_for(inv):
    """Mimic the workflow's output block: OCR text plus detected regions."""
    return {
        "workflow": "invoice-extraction",
        "image": inv["file"],
        "outputs": {
            "ocr_text": ocr_text_for(inv),
            "regions": [
                {"label": "vendor_block", "text": f"{inv['vendor']} {inv['vendor_address']}",
                 "bbox": [60, 50, 500, 120]},
                {"label": "invoice_number", "text": inv["number"], "bbox": [60, 250, 260, 40]},
                {"label": "total_due", "text": f"{inv['total']:.2f}", "bbox": [560, 760, 200, 40]},
            ],
        },
    }


INVOICES = [
    {
        "file": "invoice_01.png", "vendor": "Acme Cloud Services",
        "vendor_address": "500 Market St, San Francisco, CA 94105",
        "number": "INV-2026-0841", "date": "2026-09-14", "bill_to": "Zachary Middleton",
        "items": [
            {"desc": "Compute instances", "qty": 1, "amount": 480.00},
            {"desc": "Object storage", "qty": 1, "amount": 120.00},
            {"desc": "Support plan", "qty": 1, "amount": 95.00},
        ],
        "subtotal": 695.00, "tax": 41.70, "total": 736.70,
    },
    {
        "file": "invoice_02.png", "vendor": "Bright Office Supply",
        "vendor_address": "12 Commerce Ave, Louisville, KY 40202",
        "number": "INV-2026-0917", "date": "2026-09-21", "bill_to": "Zachary Middleton",
        "items": [
            {"desc": "Copy paper (10 reams)", "qty": 10, "amount": 89.99},
            {"desc": "Toner cartridges", "qty": 2, "amount": 129.50},
        ],
        "subtotal": 219.49, "tax": 13.17, "total": 232.66,
    },
    {
        # Duplicate invoice number of invoice_01, different date and amount.
        "file": "invoice_03.png", "vendor": "Acme Cloud Services",
        "vendor_address": "500 Market St, San Francisco, CA 94105",
        "number": "INV-2026-0841", "date": "2026-09-28", "bill_to": "Zachary Middleton",
        "items": [{"desc": "Compute instances", "qty": 1, "amount": 520.00}],
        "subtotal": 520.00, "tax": 31.20, "total": 551.20,
    },
    {
        # Totals mismatch: line items + tax = 1523.75, but printed total differs.
        "file": "invoice_04.png", "vendor": "Northwind Logistics",
        "vendor_address": "77 Harbor Rd, Evansville, IN 47708",
        "number": "INV-2026-1022", "date": "2026-10-01", "bill_to": "Zachary Middleton",
        "items": [
            {"desc": "Freight - September", "qty": 1, "amount": 1250.00},
            {"desc": "Fuel surcharge", "qty": 1, "amount": 187.50},
        ],
        "subtotal": 1437.50, "tax": 86.25, "total": 1450.00,
    },
    {
        # Outlier amount relative to the rest of the batch.
        "file": "invoice_05.png", "vendor": "Vertex Data Centers",
        "vendor_address": "9000 Data Pkwy, Ashburn, VA 20147",
        "number": "INV-2026-1033", "date": "2026-10-02", "bill_to": "Zachary Middleton",
        "items": [{"desc": "Colocation - Q4", "qty": 1, "amount": 8400.00}],
        "subtotal": 8400.00, "tax": 504.00, "total": 8904.00,
    },
]

if __name__ == "__main__":
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(MOCK_DIR, exist_ok=True)
    for inv in INVOICES:
        render_invoice(inv)
        mock = mock_output_for(inv)
        out = os.path.join(MOCK_DIR, inv["file"].replace(".png", ".json"))
        with open(out, "w") as f:
            json.dump(mock, f, indent=2)
        print(f"wrote images/{inv['file']} + demo/mock_outputs/{os.path.basename(out)}")
