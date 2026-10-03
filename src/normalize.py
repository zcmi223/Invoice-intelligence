"""
Step 2 -- Normalization (data hygiene).

Turns the raw OCR text from the extraction step into a clean, structured
invoice record:

    {
        "source_image": str,
        "vendor": str | None,
        "invoice_number": str | None,
        "date": "YYYY-MM-DD" | None,
        "line_items": [{"description": str, "qty": float, "amount": float}],
        "subtotal": float | None,
        "tax": float | None,
        "total": float | None,
        "parse_warnings": [str],   # every field we could NOT extract cleanly
    }

This is the RevOps "data hygiene" layer: garbage in from OCR becomes
validated, typed records -- or explicit warnings, never silent guesses.
Anything we can't parse with confidence is flagged, not invented.
"""

import re
from datetime import datetime

_MONEY = r"\$?\s*([\d,]+\.\d{2})"
_DATE_RES = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),          # 2026-09-14
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), "%m/%d/%Y"),      # 09/14/2026
    (re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"), "%B %d %Y"),  # Sept 14 2026
]


def _parse_money(text):
    try:
        return float(text.replace(",", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None


def _parse_date(text):
    for pattern, _fmt in _DATE_RES:
        m = pattern.search(text)
        if m:
            try:
                if "%Y-%m-%d" == _fmt:
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                if "%m/%d/%Y" == _fmt:
                    dt = datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                else:
                    dt = datetime.strptime(m.group(0).replace(",", ""), "%B %d %Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def normalize(extraction):
    """Normalize one extraction dict into a structured invoice record."""
    text = extraction.get("ocr_text", "") or ""
    warnings = []

    record = {
        "source_image": extraction.get("source_image"),
        "vendor": None,
        "invoice_number": None,
        "date": None,
        "line_items": [],
        "subtotal": None,
        "tax": None,
        "total": None,
        "parse_warnings": warnings,
    }

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        warnings.append("empty OCR text -- nothing to normalize")
        return record

    # Vendor: first strong non-keyword line (real invoices put the vendor first).
    skip = ("invoice", "bill to", "description", "qty", "amount", "subtotal",
            "tax", "total", "date:")
    for ln in lines:
        low = ln.lower()
        if not any(k in low for k in skip) and len(ln) > 2:
            record["vendor"] = ln
            break
    if not record["vendor"]:
        warnings.append("vendor not found")

    # Invoice number: common label variants ("Invoice #:", "Invoice No.", "Inv #").
    # The label must include #/No. so the bare word "INVOICE" never matches.
    m = re.search(r"(?:invoice|inv)\s*(?:#|no\.?)\s*:?\s*([A-Za-z0-9\-]+)",
                  text, re.IGNORECASE)
    if m:
        record["invoice_number"] = m.group(1)
    else:
        warnings.append("invoice number not found")

    # Date: first parseable date on a line mentioning date, else anywhere.
    date_lines = [ln for ln in lines if "date" in ln.lower()] + lines
    for ln in date_lines:
        d = _parse_date(ln)
        if d:
            record["date"] = d
            break
    if not record["date"]:
        warnings.append("invoice date not found")

    # Line items: "<description> <qty> <amount>" rows.
    item_re = re.compile(r"^(.+?)\s+(\d+(?:\.\d+)?)\s+" + _MONEY + r"$")
    in_items = False
    for ln in lines:
        low = ln.lower()
        if "description" in low and "qty" in low:
            in_items = True
            continue
        if any(k in low for k in ("subtotal", "tax", "total due", "total:")):
            in_items = False
        if in_items:
            m = item_re.match(ln)
            if m:
                record["line_items"].append({
                    "description": m.group(1).strip(),
                    "qty": float(m.group(2)),
                    "amount": _parse_money(m.group(3)),
                })
    if not record["line_items"]:
        warnings.append("no line items parsed")

    # Money fields: labeled totals. "TOTAL DUE" wins over bare "total".
    def money_after(label_res):
        # Allow an optional parenthetical between label and colon: "Tax (6%): 41.70".
        for ln in lines:
            m = re.search(label_res + r"(?:\s*\([^)]*\))?\s*:?\s*" + _MONEY,
                          ln, re.IGNORECASE)
            if m:
                return _parse_money(m.group(1))
        return None

    record["subtotal"] = money_after(r"subtotal")
    record["tax"] = money_after(r"tax")
    record["total"] = (money_after(r"total\s*due") or money_after(r"(?<!sub)total"))

    for field in ("subtotal", "tax", "total"):
        if record[field] is None:
            warnings.append(f"{field} not found")

    return record
