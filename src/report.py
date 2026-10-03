"""
Step 4 -- Reporting.

Renders the analysis dict from src/analyze.py into a Markdown spend report.
"""

from datetime import date


def _money(v):
    return f"${v:,.2f}"


def render(analysis, mode):
    s = analysis["summary"]
    lines = [
        "# Invoice Intelligence -- Spend Report",
        "",
        f"_Generated {date.today().isoformat()} | extraction mode: **{mode}**_",
        "",
        "## Summary",
        "",
        f"- Invoices processed: **{s['invoice_count']}**",
        f"- Total spend: **{_money(s['total_spend'])}**",
        f"- Average invoice: **{_money(s['avg_invoice'])}**",
        f"- Date range: {s['date_range'][0]} to {s['date_range'][1]}",
        "",
        "## Spend by Vendor",
        "",
        "| Vendor | Invoices | Total |",
        "| --- | ---: | ---: |",
    ]
    for row in analysis["by_vendor"]:
        lines.append(f"| {row['vendor']} | {row['count']} | {_money(row['total'])} |")

    lines += [
        "",
        "## Spend by Month",
        "",
        "| Month | Invoices | Total |",
        "| --- | ---: | ---: |",
    ]
    for row in analysis["by_month"]:
        lines.append(f"| {row['month']} | {row['count']} | {_money(row['total'])} |")

    lines += [
        "",
        "## Spend by Category",
        "",
        "| Category | Invoices | Total |",
        "| --- | ---: | ---: |",
    ]
    for row in analysis["by_category"]:
        lines.append(f"| {row['category']} | {row['count']} | {_money(row['total'])} |")

    lines += ["", "## Anomalies & Data-Quality Flags", ""]
    if analysis["anomalies"]:
        for a in analysis["anomalies"]:
            lines.append(f"- **[{a['type']}]** `{a['invoice']}` -- {a['detail']}")
    else:
        lines.append("No anomalies detected. All invoices parsed cleanly.")

    lines += ["", "## Invoice Detail", ""]
    for r in analysis["records"]:
        lines.append(
            f"### {r['vendor'] or 'Unknown vendor'} -- "
            f"{r['invoice_number'] or '?'} ({r['date'] or 'no date'})"
        )
        lines.append("")
        for item in r["line_items"]:
            lines.append(f"- {item['description']} x{item['qty']:g} -- "
                         f"{_money(item['amount'])}")
        lines.append(f"- **Total: {_money(r['total'])}**  "
                     f"`{r['source_image'].split('/')[-1]}`")
        lines.append("")

    return "\n".join(lines) + "\n"
