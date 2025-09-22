# plancosts/output/table.py
"""
ASCII table rendering that mirrors the Go output (Quantity + Unit columns, flattened subresources).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List

from plancosts.output.json import to_json


def _fmt_cost(val: Decimal | float | int, pattern: str = "{:.4f}") -> str:
    try:
        return pattern.format(float(val))
    except Exception:
        return str(val)


def _fmt_qty(val: Any) -> str:
    try:
        s = "{:f}".format(float(val))
    except Exception:
        return str(val)
    s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def _branch(i: int, total: int) -> str:
    return "└─" if i == total else "├─"


def _render(rows: List[List[str]]) -> str:
    name_w   = max((len(r[0]) for r in rows), default=4)
    qty_w    = max((len(r[1]) for r in rows), default=8)
    unit_w   = max((len(r[2]) for r in rows), default=4)
    hourly_w = max((len(r[3]) for r in rows), default=11)
    month_w  = max((len(r[4]) for r in rows), default=12)

    line = f"{{:<{name_w}}}  {{:>{qty_w}}}  {{:<{unit_w}}}  {{:>{hourly_w}}}  {{:>{month_w}}}"
    out = [line.format("NAME", "QUANTITY", "UNIT", "HOURLY COST", "MONTHLY COST")]
    out += [line.format(*r) for r in rows]
    return "\n".join(out)


def to_table(breakdowns: Any, no_color: bool = False) -> str:
    data: List[Dict[str, Any]] = json.loads(to_json(breakdowns))
    rows: List[List[str]] = []
    overall_h = Decimal("0")
    overall_m = Decimal("0")

    for res in data:
        title = res.get("resource", "")
        rows.append([title, "", "", "", ""])

        subs = list(res.get("subresources", []) or [])

        items = list(res.get("breakdown", []))
        for sub in subs:
            items.extend(sub.get("breakdown", []))
        total_items = len(items)

        i = 0
        th = Decimal("0")
        tm = Decimal("0")

        for pc in res.get("breakdown", []):
            i += 1
            h = Decimal(str(pc.get("hourlyCost", 0)))
            m = Decimal(str(pc.get("monthlyCost", 0)))
            q = pc.get("quantity", 0)
            u = pc.get("unit", "")

            th += h
            tm += m
            rows.append(
                [
                    f"{_branch(i, total_items)} {pc.get('priceComponent','')}",
                    _fmt_qty(q),
                    str(u or ""),
                    _fmt_cost(h),
                    _fmt_cost(m),
                ]
            )

        for sub in subs:
            short = sub.get("resource", "").replace(f"{title}.", "", 1)
            for pc in sub.get("breakdown", []):
                i += 1
                h = Decimal(str(pc.get("hourlyCost", 0)))
                m = Decimal(str(pc.get("monthlyCost", 0)))
                q = pc.get("quantity", 0)
                u = pc.get("unit", "")

                th += h
                tm += m
                rows.append(
                    [
                        f"{_branch(i, total_items)} {short} {pc.get('priceComponent','')}",
                        _fmt_qty(q),
                        str(u or ""),
                        _fmt_cost(h),
                        _fmt_cost(m),
                    ]
                )

        rows.append(["Total", "", "", _fmt_cost(th), _fmt_cost(tm)])
        rows.append(["", "", "", "", ""])

        overall_h += th
        overall_m += tm

    rows.append(["OVERALL TOTAL", "", "", _fmt_cost(overall_h), _fmt_cost(overall_m)])
    return _render(rows)
