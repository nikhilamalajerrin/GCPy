# plancosts/output/table_rich.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, List, Optional
import shutil

from rich.console import Console
from rich.table import Table

# ---------- tiny duck-typing helpers (same idea as in main) ----------

def _call_maybe(obj: Any, *names: str, default=None):
    for n in names:
        if hasattr(obj, n):
            attr = getattr(obj, n)
            if callable(attr):
                try:
                    return attr()
                except TypeError:
                    pass
            else:
                return attr
    return default

def _d(x) -> Decimal:
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0")

def _name_of_resource(r: Any) -> str:
    # Go uses resource.Name; fall back to address.
    return (
        _call_maybe(r, "name", "Name")
        or _call_maybe(r, "address", "Address")
        or "<resource>"
    )

def _subresources(r: Any) -> List[Any]:
    out = _call_maybe(r, "sub_resources", "SubResources", default=[])
    return list(out) if isinstance(out, Iterable) else []

def _price_components(r: Any) -> List[Any]:
    pcs = _call_maybe(
        r,
        "price_components", "PriceComponents",
        "cost_components", "CostComponents",
        default=[]
    )
    return list(pcs) if isinstance(pcs, Iterable) else []

def _component_name(pc: Any) -> str:
    return _call_maybe(pc, "name", "Name") or "<component>"

def _component_unit(pc: Any) -> str:
    return _call_maybe(pc, "unit", "Unit") or ""

def _component_qty_monthly(pc: Any) -> Decimal:
    q = _call_maybe(pc, "MonthlyQuantity", "monthly_quantity", "Quantity", "quantity", default=Decimal("0"))
    return _d(q)

def _component_unit_price(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "Price", "price", default=Decimal("0")))

def _component_hourly_cost(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "HourlyCost", "hourly_cost", default=Decimal("0")))

def _component_monthly_cost(pc: Any) -> Decimal:
    return _d(_call_maybe(pc, "MonthlyCost", "monthly_cost", default=Decimal("0")))

def _flattened_subresources(res: Any) -> List[Any]:
    """
    Full recursive flatten like Go's FlattenedSubResources(), preserving
    original order (depth-first).
    """
    out: List[Any] = []
    stack: List[Any] = list(_subresources(res))
    # Use a queue-like walk to keep input order; extend with children in-order.
    i = 0
    while i < len(stack):
        sr = stack[i]
        out.append(sr)
        children = _subresources(sr)
        if children:
            # insert children immediately after current to emulate depth-first
            stack[i+1:i+1] = children
        i += 1
    return out

def _branch(i: int, total: int) -> str:
    return "└─" if i == total else "├─"

def _fmt_qty(x: Decimal) -> str:
    s = f"{float(x):f}"
    s = s.rstrip("0").rstrip(".")
    return s or "0"

def _fmt4(x: Decimal) -> str:
    return f"{float(x):.4f}"


# ---------- public API ----------

def render_table(resources: List[Any], *, no_color: bool = False, width: Optional[int] = None) -> str:
    """
    Return a string containing a Rich-rendered table.

    Parity with Go's table:
      - NAME (resource line) + blank columns
      - For components: "├─/└─ <ComponentName>"
      - For subresources: "├─/└─ <ComponentName> (<SubresourceName>)"
      - Per-resource "Total" and final "OVERALL TOTAL"
      - Recursive flatten of subresources; original order preserved.
    """
    table = Table(
        show_header=True,
        header_style=None if no_color else "bold",
        box=None,        # closer to infracost look; use box.SIMPLE for borders
        pad_edge=False,
    )
    table.add_column("NAME", justify="left", no_wrap=True)
    table.add_column("MONTHLY QTY", justify="right")
    table.add_column("UNIT", justify="left")
    table.add_column("PRICE", justify="right")
    table.add_column("HOURLY COST", justify="right")
    table.add_column("MONTHLY COST", justify="right")

    # Preserve incoming order like Go (no sorting).
    resources = list(resources or [])

    overall_h = Decimal("0")
    overall_m = Decimal("0")

    for r in resources:
        rname = _name_of_resource(r)
        table.add_row(rname, "", "", "", "", "")

        # Count all components including recursively-flattened subresources
        total_items = len(_price_components(r))
        flat_subs = _flattened_subresources(r)
        for s in flat_subs:
            total_items += len(_price_components(s))

        line_no = 0
        res_h = Decimal("0")
        res_m = Decimal("0")

        # Top-level components (preserve order)
        for pc in _price_components(r):
            line_no += 1
            table.add_row(
                f"{_branch(line_no, total_items)} {_component_name(pc)}",
                _fmt_qty(_component_qty_monthly(pc)),
                _component_unit(pc),
                _fmt4(_component_unit_price(pc)),
                _fmt4(_component_hourly_cost(pc)),
                _fmt4(_component_monthly_cost(pc)),
            )
            res_h += _component_hourly_cost(pc)
            res_m += _component_monthly_cost(pc)

        # All sub-resources (recursive, preserve order)
        for s in flat_subs:
            sname = _name_of_resource(s)
            for pc in _price_components(s):
                line_no += 1
                table.add_row(
                    f"{_branch(line_no, total_items)} {_component_name(pc)} ({sname})",
                    _fmt_qty(_component_qty_monthly(pc)),
                    _component_unit(pc),
                    _fmt4(_component_unit_price(pc)),
                    _fmt4(_component_hourly_cost(pc)),
                    _fmt4(_component_monthly_cost(pc)),
                )
                res_h += _component_hourly_cost(pc)
                res_m += _component_monthly_cost(pc)

        table.add_row("Total", "", "", "", _fmt4(res_h), _fmt4(res_m))
        table.add_row("", "", "", "", "", "")

        overall_h += res_h
        overall_m += res_m

    table.add_row("OVERALL TOTAL", "", "", "", _fmt4(overall_h), _fmt4(overall_m))

    # Render to text
    if width is None:
        width = shutil.get_terminal_size((100, 20)).columns
    console = Console(no_color=no_color, force_terminal=True, width=width)
    with console.capture() as cap:
        console.print(table)
    return cap.get()
