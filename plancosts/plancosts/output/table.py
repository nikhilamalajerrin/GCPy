"""
ASCII table rendering that mirrors the Go output in pkg/output/table.go:
- Columns: NAME, QUANTITY, UNIT, HOURLY COST, MONTHLY COST
- Shallow flatten of sub-resources (current resource + its immediate sub-resources)
- Branch glyphs: '├─' for intermediate rows, '└─' for the last row
- Totals per resource and an OVERALL TOTAL footer
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from plancosts.output.json import to_json


def _to_decimal(x: Any) -> Decimal:
    if isinstance(x, Decimal):
        return x
    try:
        # Handle numbers/strings cleanly; fall back to 0
        return Decimal(str(x))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _fmt_cost(val: Any, pattern: str = "{:.4f}") -> str:
    try:
        return pattern.format(float(_to_decimal(val)))
    except Exception:
        return "0.0000"


def _fmt_qty(val: Any) -> str:
    """
    Go uses: strconv.FormatFloat(f, 'f', -1, 64)
    That’s: decimal without trailing zeros.
    """
    try:
        s = "{:f}".format(float(_to_decimal(val)))
    except Exception:
        return "0"
    s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def _branch(i: int, total: int) -> str:
    return "└─" if i == total else "├─"


def _render(rows: List[List[str]]) -> str:
    # Compute column widths from content (no colors/borders, like our port)
    name_w   = max((len(r[0]) for r in rows), default=4)
    qty_w    = max((len(r[1]) for r in rows), default=8)
    unit_w   = max((len(r[2]) for r in rows), default=4)
    hourly_w = max((len(r[3]) for r in rows), default=11)
    month_w  = max((len(r[4]) for r in rows), default=12)

    line = f"{{:<{name_w}}}  {{:>{qty_w}}}  {{:<{unit_w}}}  {{:>{hourly_w}}}  {{:>{month_w}}}"
    out = [line.format("NAME", "QUANTITY", "UNIT", "HOURLY COST", "MONTHLY COST")]
    out += [line.format(*r) for r in rows]
    return "\n".join(out)


def to_table(breakdowns: Any, no_color: bool = False, stable_sort: bool = False) -> str:
    """
    Render an ASCII table from the list returned by base.costs.generate_cost_breakdowns.

    Parameters
    ----------
    breakdowns : list[ResourceCostBreakdown] | JSON-serializable
        The cost breakdowns.
    no_color : bool
        Accepted for API parity; colors are not used in this renderer.
    stable_sort : bool
        If True, sorts resources and subresources by their address for deterministic output
        (useful in tests/snapshots). Default False to mirror the Go loop order.
    """
    data: List[Dict[str, Any]] = json.loads(to_json(breakdowns))

    if stable_sort:
        data.sort(key=lambda r: r.get("resource", ""))

    rows: List[List[str]] = []
    overall_h = Decimal("0")
    overall_m = Decimal("0")

    for res in data:
        title = res.get("resource", "") or ""
        rows.append([title, "", "", "", ""])

        subs = list(res.get("subresources", []) or [])
        if stable_sort:
            subs.sort(key=lambda s: s.get("resource", ""))

        # Compute total line items like Go:
        # len(res.PriceComponentCosts) + sum(len(sub.PriceComponentCosts) for sub in flattenSubResourceBreakdowns(...))
        # The Go flatten is shallow: include each immediate sub’s PriceComponentCosts only.
        items = list(res.get("breakdown", []) or [])
        for sub in subs:
            items.extend(sub.get("breakdown", []) or [])
        total_items = len(items)

        i = 0
        th = Decimal("0")
        tm = Decimal("0")

        # Top-level price components
        for pc in (res.get("breakdown", []) or []):
            i += 1
            h = _to_decimal(pc.get("hourlyCost", 0))
            m = _to_decimal(pc.get("monthlyCost", 0))
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

        # Immediate sub-resources’ price components, label = "<short-sub-addr> <pc-name>"
        for sub in subs:
            short = (sub.get("resource", "") or "").replace(f"{title}.", "", 1)
            for pc in (sub.get("breakdown", []) or []):
                i += 1
                h = _to_decimal(pc.get("hourlyCost", 0))
                m = _to_decimal(pc.get("monthlyCost", 0))
                q = pc.get("quantity", 0)
                u = pc.get("unit", "")

                th += h
                tm += m
                rows.append(
                    [
                        f"{_branch(i, total_items)} {short} {pc.get('priceComponent','')}".strip(),
                        _fmt_qty(q),
                        str(u or ""),
                        _fmt_cost(h),
                        _fmt_cost(m),
                    ]
                )

        # Resource totals
        rows.append(["Total", "", "", _fmt_cost(th), _fmt_cost(tm)])
        rows.append(["", "", "", "", ""])

        overall_h += th
        overall_m += tm

    # Overall footer
    rows.append(["OVERALL TOTAL", "", "", _fmt_cost(overall_h), _fmt_cost(overall_m)])
    return _render(rows)
