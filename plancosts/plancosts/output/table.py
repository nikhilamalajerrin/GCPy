from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import List, Any, Iterable, Optional

from plancosts.schema.resource import Resource
from plancosts.schema.cost_component import CostComponent

FMT_4DP = "{:.4f}"


# ---- helpers ------------------------------

def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _fmt_4dp(val: Any) -> str:
    try:
        return FMT_4DP.format(float(_d(val)))
    except Exception:
        return "0.0000"


def _fmt_qty(val: Any) -> str:
    try:
        s = "{:f}".format(float(_d(val)))
    except Exception:
        return "0"
    s = s.rstrip("0").rstrip(".")
    return s or "0"


def _branch(i: int, total: int) -> str:
    return "└─" if i == total else "├─"


def _ensure_list(x: Optional[Iterable[Any]]) -> List[Any]:
    return list(x) if x else []


def _flattened_subresources(res: Resource) -> List[Resource]:
    out: List[Resource] = []
    stack = _ensure_list(res.sub_resources)[:]
    while stack:
        sr = stack.pop(0)
        out.append(sr)
        children = _ensure_list(getattr(sr, "sub_resources", None))
        if children:
            stack[0:0] = children
    return out


def _line_item_count(res: Resource) -> int:
    count = len(_ensure_list(res.cost_components))
    for sr in _flattened_subresources(res):
        count += len(_ensure_list(sr.cost_components))
    return count


def _cc_name(cc: CostComponent) -> str:
    return getattr(cc, "name", None) or getattr(cc, "Name", None) or "<component>"


def _cc_unit(cc: CostComponent) -> str:
    return getattr(cc, "unit", None) or getattr(cc, "Unit", None) or ""


def _monthly_quantity_of(cc: CostComponent) -> Decimal:
    if hasattr(cc, "MonthlyQuantity") and callable(cc.MonthlyQuantity):
        try:
            mq = cc.MonthlyQuantity()
            if mq is not None:
                return _d(mq)
        except Exception:
            pass
    if hasattr(cc, "Quantity") and callable(cc.Quantity):
        try:
            return _d(cc.Quantity())
        except Exception:
            pass
    for attr in ("monthly_quantity", "_monthly_quantity", "quantity"):
        if hasattr(cc, attr):
            return _d(getattr(cc, attr))
    return Decimal("0")


def _unit_price_of(cc: CostComponent) -> Decimal:
    if hasattr(cc, "Price") and callable(cc.Price):
        try:
            return _d(cc.Price())
        except Exception:
            pass
    if hasattr(cc, "price"):
        return _d(getattr(cc, "price"))
    return Decimal("0")


def _hourly_cost_of(cc: CostComponent) -> Decimal:
    if hasattr(cc, "HourlyCost") and callable(cc.HourlyCost):
        try:
            return _d(cc.HourlyCost())
        except Exception:
            pass
    return _d(getattr(cc, "hourly_cost", 0))


def _monthly_cost_of(cc: CostComponent) -> Decimal:
    if hasattr(cc, "MonthlyCost") and callable(cc.MonthlyCost):
        try:
            return _d(cc.MonthlyCost())
        except Exception:
            pass
    return _d(getattr(cc, "monthly_cost", 0))


# ---- skipped message -----------------------

def _skipped_resources_message(resources: List[Resource]) -> str:
    skipped = [r for r in resources if getattr(r, "is_skipped", False)]
    if not skipped:
        return ""

    grouped: dict[str, List[str]] = {}
    for r in skipped:
        rtype = getattr(r, "resource_type", None) or "<unknown>"
        grouped.setdefault(rtype, []).append(
            getattr(r, "skip_message", None) or "unsupported resource"
        )

    parts: List[str] = ["", "", "The following resources were skipped:"]
    for rtype, msgs in grouped.items():
        parts.append(f"  - {rtype}: {len(msgs)} unsupported resources")
    parts.append("")
    return "\n".join(parts)


# ---- table rendering -----------------------

def _render_table(rows: List[List[str]]) -> str:
    headers = ["NAME", "MONTHLY QTY", "UNIT", "PRICE", "HOURLY COST", "MONTHLY COST"]
    all_rows = [headers] + rows

    name_w   = max(len(r[0]) for r in all_rows)
    qty_w    = max(len(r[1]) for r in all_rows)
    unit_w   = max(len(r[2]) for r in all_rows)
    price_w  = max(len(r[3]) for r in all_rows)
    hourly_w = max(len(r[4]) for r in all_rows)
    month_w  = max(len(r[5]) for r in all_rows)

    header_fmt = (
        f"{{:<{name_w}}}  {{:>{qty_w}}}  {{:<{unit_w}}}  "
        f"{{:>{price_w}}}  {{:>{hourly_w}}}  {{:>{month_w}}}"
    )
    row_fmt = header_fmt

    out = [header_fmt.format(*headers)]
    out += [row_fmt.format(*r) for r in rows]
    return "\n".join(out)


def to_table(resources: List[Resource], show_skipped: bool = False) -> str:
    """
    Equivalent of ToTable(resources, c *cli.Context) in Go.
    """
    rows: List[List[str]] = []
    overall_h = Decimal("0")
    overall_m = Decimal("0")

    for res in resources or []:
        # Skip if resource marked skipped
        if getattr(res, "is_skipped", False):
            continue

        display = getattr(res, "name", None) or getattr(res, "address", None) or "<resource>"
        rows.append([display, "", "", "", "", ""])

        line_total = _line_item_count(res)
        line_no = 0
        res_h = Decimal("0")
        res_m = Decimal("0")

        for cc in _ensure_list(res.cost_components):
            line_no += 1
            rows.append([
                f"{_branch(line_no, line_total)} {_cc_name(cc)}",
                _fmt_qty(_monthly_quantity_of(cc)),
                _cc_unit(cc),
                _fmt_4dp(_unit_price_of(cc)),
                _fmt_4dp(_hourly_cost_of(cc)),
                _fmt_4dp(_monthly_cost_of(cc)),
            ])
            res_h += _hourly_cost_of(cc)
            res_m += _monthly_cost_of(cc)

        for sr in _flattened_subresources(res):
            sr_name = getattr(sr, "name", None) or getattr(sr, "address", None) or ""
            for cc in _ensure_list(sr.cost_components):
                line_no += 1
                rows.append([
                    f"{_branch(line_no, line_total)} {_cc_name(cc)} ({sr_name})",
                    _fmt_qty(_monthly_quantity_of(cc)),
                    _cc_unit(cc),
                    _fmt_4dp(_unit_price_of(cc)),
                    _fmt_4dp(_hourly_cost_of(cc)),
                    _fmt_4dp(_monthly_cost_of(cc)),
                ])
                res_h += _hourly_cost_of(cc)
                res_m += _monthly_cost_of(cc)

        rows.append(["Total", "", "", "", _fmt_4dp(res_h), _fmt_4dp(res_m)])
        rows.append(["", "", "", "", "", ""])
        overall_h += res_h
        overall_m += res_m

    rows.append(["OVERALL TOTAL", "", "", "", _fmt_4dp(overall_h), _fmt_4dp(overall_m)])
    table_str = _render_table(rows)

    # append skipped summary if needed
    if show_skipped:
        msg = _skipped_resources_message(resources)
        if msg:
            table_str += "\n" + msg

    return table_str
