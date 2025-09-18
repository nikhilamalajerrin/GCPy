# plancosts/outputs/table.py
from __future__ import annotations

from decimal import Decimal
from typing import List, Dict, Any

from plancosts.outputs.json import to_json  # reuse the stable JSON layout
import json


def _fmt_decimal(val: Decimal | float | int, fmt: str = "{:.4f}") -> str:
    # ensure Decimal-friendly formatting but accept floats too
    if isinstance(val, Decimal):
        return fmt.format(float(val))
    try:
        return fmt.format(float(val))
    except Exception:
        return str(val)


def _line_prefix(i: int, total: int) -> str:
    return "└─" if i == total else "├─"


def _render_table(rows: List[List[str]]) -> str:
    # simple left/right columns with minimal styling; no third-party libs
    # columns: NAME (left), HOURLY (right), MONTHLY (right)
    name_w = max((len(r[0]) for r in rows), default=4)
    hourly_w = max((len(r[1]) for r in rows), default=11)
    monthly_w = max((len(r[2]) for r in rows), default=12)

    out_lines = []
    header = ["NAME", "HOURLY COST", "MONTHLY COST"]
    header_fmt = f"{{:<{name_w}}}  {{:>{hourly_w}}}  {{:>{monthly_w}}}"
    out_lines.append(header_fmt.format(*header))

    for name, hourly, monthly in rows:
        out_lines.append(header_fmt.format(name, hourly, monthly))

    return "\n".join(out_lines)


def to_table(resource_cost_breakdowns: Any) -> str:
    """
    Render the same tree-style table as the Go commit:
    - Resource title row
    - Child rows for each price component (with ├─/└─)
    - Includes subresource line items
    - Per-resource total and an overall total
    """
    # Normalize via JSON serializer we already trust
    # to_json() returns a JSON string; parse it to a dict we can walk.
    data: List[Dict[str, Any]] = json.loads(to_json(resource_cost_breakdowns))

    all_rows: List[List[str]] = []
    overall_hourly = Decimal("0")
    overall_monthly = Decimal("0")

    for res in data:
        resource_name = res.get("resource", "")
        all_rows.append([resource_name, "", ""])

        # Count total line items (resource-level + subresources)
        line_items = res.get("breakdown", [])[:]
        sub_list = res.get("subresources", []) or []
        for sub in sub_list:
            line_items.extend(sub.get("breakdown", []))
        total_items = len(line_items)

        i = 0
        total_hourly = Decimal("0")
        total_monthly = Decimal("0")

        # resource-level components
        for pc in res.get("breakdown", []):
            i += 1
            hourly = Decimal(str(pc.get("hourlyCost", 0)))
            monthly = Decimal(str(pc.get("monthlyCost", 0)))
            total_hourly += hourly
            total_monthly += monthly
            all_rows.append([
                f"{_line_prefix(i, total_items)} {pc.get('priceComponent','')}",
                _fmt_decimal(hourly),
                _fmt_decimal(monthly),
            ])

        # sub-resources
        for sub in sub_list:
            sub_addr = sub.get("resource", "")
            # shorten label like Go code (show portion after "<parent>.")
            short = sub_addr.replace(f"{resource_name}.", "", 1)
            for pc in sub.get("breakdown", []):
                i += 1
                hourly = Decimal(str(pc.get("hourlyCost", 0)))
                monthly = Decimal(str(pc.get("monthlyCost", 0)))
                total_hourly += hourly
                total_monthly += monthly
                all_rows.append([
                    f"{_line_prefix(i, total_items)} {short} {pc.get('priceComponent','')}",
                    _fmt_decimal(hourly),
                    _fmt_decimal(monthly),
                ])

        # totals for this resource
        all_rows.append([
            "Total",
            _fmt_decimal(total_hourly),
            _fmt_decimal(total_monthly),
        ])
        all_rows.append(["", "", ""])  # blank spacer

        overall_hourly += total_hourly
        overall_monthly += total_monthly

    # overall total
    all_rows.append([
        "OVERALL TOTAL",
        _fmt_decimal(overall_hourly),
        _fmt_decimal(overall_monthly),
    ])

    return _render_table(all_rows)
