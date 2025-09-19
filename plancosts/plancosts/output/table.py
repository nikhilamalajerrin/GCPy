"""
ASCII table rendering that mirrors the Go output.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List
import json

from plancosts.output.json import to_json

def _fmt(val: Decimal | float | int, pattern: str = "{:.4f}") -> str:
    try:
        return pattern.format(float(val))
    except Exception:
        return str(val)

def _branch(i: int, total: int) -> str:
    return "└─" if i == total else "├─"

def _render(rows: List[List[str]]) -> str:
    name_w   = max((len(r[0]) for r in rows), default=4)
    hourly_w = max((len(r[1]) for r in rows), default=11)
    month_w  = max((len(r[2]) for r in rows), default=12)
    line = f"{{:<{name_w}}}  {{:>{hourly_w}}}  {{:>{month_w}}}"
    out = [line.format("NAME", "HOURLY COST", "MONTHLY COST")]
    out += [line.format(*r) for r in rows]
    return "\n".join(out)

def to_table(breakdowns: Any) -> str:
    data: List[Dict[str, Any]] = json.loads(to_json(breakdowns))

    rows: List[List[str]] = []
    overall_h = Decimal("0")
    overall_m = Decimal("0")

    for res in data:
        title = res.get("resource", "")
        rows.append([title, "", ""])

        # flatten items to compute totals/order
        items = list(res.get("breakdown", []))
        for sub in res.get("subresources", []) or []:
            items.extend(sub.get("breakdown", []))
        total_items = len(items)

        i = 0
        th = Decimal("0")
        tm = Decimal("0")

        for pc in res.get("breakdown", []):
            i += 1
            h = Decimal(str(pc.get("hourlyCost", 0)))
            m = Decimal(str(pc.get("monthlyCost", 0)))
            th += h
            tm += m
            rows.append([f"{_branch(i, total_items)} {pc.get('priceComponent','')}", _fmt(h), _fmt(m)])

        for sub in res.get("subresources", []) or []:
            short = sub.get("resource", "").replace(f"{title}.", "", 1)
            for pc in sub.get("breakdown", []):
                i += 1
                h = Decimal(str(pc.get("hourlyCost", 0)))
                m = Decimal(str(pc.get("monthlyCost", 0)))
                th += h
                tm += m
                rows.append([f"{_branch(i, total_items)} {short} {pc.get('priceComponent','')}", _fmt(h), _fmt(m)])

        rows.append(["Total", _fmt(th), _fmt(tm)])
        rows.append(["", "", ""])

        overall_h += th
        overall_m += tm

    rows.append(["OVERALL TOTAL", _fmt(overall_h), _fmt(overall_m)])
    return _render(rows)
