"""
Step 3 -- Spend analysis (reporting inputs).

Aggregates normalized invoice records into the numbers a RevOps / finance
leader actually wants, and flags data-quality anomalies:

  * spend by vendor, by month, by category (keyword mapping)
  * duplicate invoice numbers (possible double-billing)
  * totals mismatch (line items + tax != printed total)
  * outlier amounts (>3x the batch median)
  * records with parse warnings (incomplete extraction)

Output shape:

    {
        "summary": {"invoice_count": int, "total_spend": float,
                    "avg_invoice": float, "date_range": [str, str]},
        "by_vendor": [{"vendor": str, "total": float, "count": int}],
        "by_month": [{"month": "YYYY-MM", "total": float, "count": int}],
        "by_category": [{"category": str, "total": float, "count": int}],
        "anomalies": [{"type": str, "invoice": str, "detail": str}],
        "records": [...],   # the normalized records, for the report
    }
"""

from collections import defaultdict
from statistics import median

CATEGORY_KEYWORDS = {
    "Cloud / SaaS": ["cloud", "compute", "storage", "saas", "software", "support plan"],
    "Office": ["paper", "toner", "office", "supply", "supplies"],
    "Logistics": ["freight", "shipping", "logistics", "fuel"],
    "Facilities": ["colocation", "data center", "rent", "colocation"],
}


def _categorize(record):
    text = " ".join(i["description"] for i in record["line_items"]).lower()
    text += " " + (record["vendor"] or "").lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return cat
    return "Other"


def analyze(records):
    records = [r for r in records if r.get("total") is not None]
    totals = [r["total"] for r in records]
    med = median(totals) if totals else 0

    by_vendor = defaultdict(lambda: {"total": 0.0, "count": 0})
    by_month = defaultdict(lambda: {"total": 0.0, "count": 0})
    by_category = defaultdict(lambda: {"total": 0.0, "count": 0})
    anomalies = []
    seen_numbers = {}

    for r in records:
        vendor = r["vendor"] or "Unknown"
        by_vendor[vendor]["total"] += r["total"]
        by_vendor[vendor]["count"] += 1

        month = (r["date"] or "????-??")[:7]
        by_month[month]["total"] += r["total"]
        by_month[month]["count"] += 1

        cat = _categorize(r)
        by_category[cat]["total"] += r["total"]
        by_category[cat]["count"] += 1

        num = r["invoice_number"]
        label = num or r["source_image"]
        if num:
            if num in seen_numbers:
                anomalies.append({
                    "type": "duplicate_invoice_number",
                    "invoice": label,
                    "detail": (f"Invoice number {num} also appears on "
                               f"{seen_numbers[num]} -- possible double-billing."),
                })
            else:
                seen_numbers[num] = r["source_image"]

        # Totals check: line items + tax should equal the printed total.
        items_sum = sum(i["amount"] for i in r["line_items"] if i["amount"])
        tax = r["tax"] or 0.0
        if r["line_items"] and abs((items_sum + tax) - r["total"]) > 0.01:
            anomalies.append({
                "type": "totals_mismatch",
                "invoice": label,
                "detail": (f"Line items (${items_sum:,.2f}) + tax (${tax:,.2f}) = "
                           f"${items_sum + tax:,.2f}, but printed total is "
                           f"${r['total']:,.2f}."),
            })

        if med and r["total"] > 3 * med:
            anomalies.append({
                "type": "outlier_amount",
                "invoice": label,
                "detail": (f"${r['total']:,.2f} is more than 3x the batch median "
                           f"(${med:,.2f}) -- verify before paying."),
            })

        for w in r.get("parse_warnings", []):
            anomalies.append({
                "type": "parse_warning",
                "invoice": label,
                "detail": f"Extraction incomplete: {w}.",
            })

    def _rank(d, key):
        return sorted([{"total": round(v["total"], 2), "count": v["count"], key: k}
                       for k, v in d.items()], key=lambda x: -x["total"])

    dates = sorted(r["date"] for r in records if r["date"])
    return {
        "summary": {
            "invoice_count": len(records),
            "total_spend": round(sum(totals), 2),
            "avg_invoice": round(sum(totals) / len(totals), 2) if totals else 0,
            "date_range": [dates[0], dates[-1]] if dates else [None, None],
        },
        "by_vendor": _rank(by_vendor, "vendor"),
        "by_month": _rank(by_month, "month"),
        "by_category": _rank(by_category, "category"),
        "anomalies": anomalies,
        "records": records,
    }
