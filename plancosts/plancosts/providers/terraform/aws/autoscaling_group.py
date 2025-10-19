from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple

from plancosts.resource.filters import Filter, ValueMapping
from .base import BaseAwsPriceComponent, BaseAwsResource, _to_decimal

if TYPE_CHECKING:
    from plancosts.schema.resource_data import ResourceData


# ---------------------------------------------------------------------------
# Compute hours (On-Demand / Spot).
# We select Spot/On-Demand by adding a PRICE-LEVEL term filter ("Spot"/"OnDemand").
# ---------------------------------------------------------------------------

class _ASGComputeHours(BaseAwsPriceComponent):
    def __init__(self, resource: "BaseAwsResource", instance_type: str, purchase_option: str, hourly_qty: Decimal):
        opt = (purchase_option or "").strip().lower()

        if opt in ("on_demand", "on-demand", "ondemand", "on demand", ""):
            opt_label = "on-demand"
            is_spot = False
        elif opt == "spot":
            opt_label = "spot"
            is_spot = True
        else:
            opt_label = "on-demand"
            is_spot = False

        label = f"Compute ({opt_label}, {instance_type})" if instance_type else f"Compute ({opt_label})"
        super().__init__(name=label, resource=resource, time_unit="hour")

        # Product-level filters common to both on-demand and spot
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Compute Instance"),
            Filter(key="operatingSystem", value="Linux"),
            Filter(key="preInstalledSw", value="NA"),
            Filter(key="tenancy", value="Shared"),
        ]

        # capacitystatus only for On-Demand (Spot SKUs typically don't have it)
        if not is_spot:
            self.default_filters.append(Filter(key="capacitystatus", value="Used"))

        # (Optional) Some catalogs expose marketoption at the product level; harmless to include.
        self.default_filters.append(Filter(key="marketoption", value="Spot" if is_spot else "OnDemand"))

        # Map instance type
        self.value_mappings = [ValueMapping(from_key="instance_type", to_key="instanceType")]

        # >>> Crucial fix: ensure price lookup matches the correct purchase term <<<
        # Tests expect Spot components to yield a non-empty priceHash; without this, products match
        # but no prices are found (price=0, empty hash).
        self.set_price_filter({"term": "Spot" if is_spot else "OnDemand"})

        # Keep qty = 1; scaling is applied by _ScaledPriceComponent
        self.SetQuantityMultiplierFunc(lambda _r: Decimal(1))



# ------------------------------
# EBS block devices
# -----------------------------------

class _BlockDeviceGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "BaseAwsResource"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage"),
        ]
        self.value_mappings = [ValueMapping(from_key="volume_type", to_key="volumeApiName")]

        self.SetQuantityMultiplierFunc(
            lambda r: _to_decimal((r.raw_values() or {}).get("volume_size") or 8)
        )
        self.unit_ = "GB-months"

        vt = (resource.raw_values() or {}).get("volume_type") or "gp2"
        self.default_filters.append(Filter(key="volumeApiName", value=str(vt)))

        # Correct usagetype mapping:
        #  - standard  -> EBS:VolumeUsage
        #  - io1       -> EBS:VolumeUsage.piops
        #  - others    -> EBS:VolumeUsage.<volumeApiName>
        vts = str(vt)
        if vts == "standard":
            usage = "EBS:VolumeUsage"
        elif vts == "io1":
            usage = "EBS:VolumeUsage.piops"
        else:
            usage = f"EBS:VolumeUsage.{vts}"
        self.default_filters.append(Filter(key="usagetype", value=usage))



class _BlockDeviceIOPS(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "BaseAwsResource"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            Filter(key="usagetype", value="EBS:VolumeP-IOPS.piops"),
        ]
        self.value_mappings = [ValueMapping(from_key="volume_type", to_key="volumeApiName")]
        self.SetQuantityMultiplierFunc(lambda r: _to_decimal((r.raw_values() or {}).get("iops") or 8))
        self.unit_ = "IOPS-months"
        self.set_price_filter({})


class _AwsBlockDevice(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        pcs: List[BaseAwsPriceComponent] = [_BlockDeviceGB("Storage", self)]
        if (raw_values or {}).get("volume_type") == "io1":
            pcs.append(_BlockDeviceIOPS("Storage IOPS", self))
        self._set_price_components(pcs)


# ----------------------------------------
# Quantity scaling wrappers 
# -----------------------------------------

class _ScaledPriceComponent(BaseAwsPriceComponent):
    """
    Scales costs/quantities but delegates all filter logic to the wrapped component.
    Keeps price / price_hash mirrored so tests can read the hash from the wrapper.
    """
    def __init__(self, wrapped: BaseAwsPriceComponent, multiplier: Decimal):
        self._wrapped = wrapped
        self._multiplier = Decimal(str(multiplier or 1))
        super().__init__(name=wrapped.name(), resource=wrapped.resource(), time_unit=wrapped.time_unit_)
        self.time_unit_ = wrapped.time_unit_
        self.unit_ = wrapped.unit()
        self.SetQuantityMultiplierFunc(lambda _r: wrapped.Quantity() * self._multiplier)

    def filters(self):  # type: ignore[override]
        return self._wrapped.filters()

    def product_filter(self):  # type: ignore[override]
        return self._wrapped.product_filter()

    def price_filter(self):  # type: ignore[override]
        return self._wrapped.price_filter()

    def SetPrice(self, price: Decimal) -> None:
        self._wrapped.SetPrice(price)

    def Price(self) -> Decimal:
        return self._wrapped.Price()

    def SetPriceHash(self, h: str) -> None:
        self._wrapped.SetPriceHash(h)
        super().SetPriceHash(h)

    def PriceHash(self) -> str:
        return self._wrapped.PriceHash()

    @property
    def price_hash(self) -> str:  # type: ignore[override]
        return getattr(self._wrapped, "price_hash", super().PriceHash())

    @price_hash.setter
    def price_hash(self, h: str) -> None:  # type: ignore[override]
        try:
            setattr(self._wrapped, "price_hash", h)
        except Exception:
            self._wrapped.SetPriceHash(h)
        super().SetPriceHash(h)

    def HourlyCost(self) -> Decimal:
        return (self._wrapped.HourlyCost() * self._multiplier).quantize(Decimal("0.0000000000"))

    def MonthlyCost(self) -> Decimal:
        return (self._wrapped.MonthlyCost() * self._multiplier).quantize(Decimal("0.0000000000"))


class _QuantitiesScaledResource(BaseAwsResource):
    def __init__(self, base: BaseAwsResource, multiplier: Decimal):
        super().__init__(address=base.address(), region=base.region(), raw_values=base.raw_values())
        wrapped_pcs: List[BaseAwsPriceComponent] = [
            _ScaledPriceComponent(pc, multiplier) for pc in base.price_components()
        ]
        self._set_price_components(wrapped_pcs)

        if hasattr(base, "sub_resources"):
            children = base.sub_resources()
        else:
            children = base.subresources()  # type: ignore[attr-defined]

        wrapped_subs: List[BaseAwsResource] = [
            _QuantitiesScaledResource(sr, multiplier) for sr in children
        ]
        self._set_sub_resources(wrapped_subs)


def _multiply_quantities(resource: BaseAwsResource, multiplier: Decimal) -> BaseAwsResource:
    mult = multiplier if isinstance(multiplier, Decimal) else _to_decimal(multiplier, Decimal(0))
    return _QuantitiesScaledResource(resource, mult)


# ---------------------------------------------------------------------------
# Helpers to read block device values
# ---------------------------------------------------------------------------

def _extract_block_values(gjson_like: Any) -> Dict[str, Any]:
    raw = {"volume_type": None, "volume_size": None, "iops": None}
    try:
        if gjson_like is not None and gjson_like.Exists():
            vt = gjson_like.Get("volume_type").String() if gjson_like.Get("volume_type").Exists() else None
            vs = None
            if gjson_like.Get("volume_size").Exists():
                try:
                    vs = gjson_like.Get("volume_size").Float()
                except Exception:
                    vs = gjson_like.Get("volume_size").Int()
            io = None
            if gjson_like.Get("iops").Exists():
                try:
                    io = gjson_like.Get("iops").Float()
                except Exception:
                    io = gjson_like.Get("iops").Int()
            raw["volume_type"] = vt or "gp2"
            raw["volume_size"] = vs
            raw["iops"] = io
    except Exception:
        pass
    if not raw["volume_type"]:
        raw["volume_type"] = "gp2"
    return {k: v for k, v in raw.items() if v not in (None, "", 0)}


def _root_block_device_from_rd(rd: "ResourceData", region: str, parent_addr: str) -> BaseAwsResource:
    # Try gjson path first
    raw: Dict[str, Any] = {}
    try:
        r = rd.Get("root_block_device.0")
        raw = _extract_block_values(r)
    except Exception:
        pass

    # Fallback to raw_values → planned values
    if not raw or "volume_size" not in raw:
        try:
            rv = rd.raw_values() or {}
            lst = (rv.get("root_block_device") or [])
            if isinstance(lst, list) and lst:
                v = lst[0] or {}
                vt = v.get("volume_type") or "gp2"
                vs = v.get("volume_size")
                io = v.get("iops")
                raw = {k: v for k, v in {"volume_type": vt, "volume_size": vs, "iops": io}.items() if v not in (None, "", 0)}
                if "volume_type" not in raw:
                    raw["volume_type"] = "gp2"
        except Exception:
            pass

    if not raw:
        raw = {"volume_type": "gp2"}

    return _AwsBlockDevice(f"{parent_addr}.root_block_device", region, raw)


def _ebs_block_devices_from_rd(rd: "ResourceData", region: str, parent_addr: str) -> List[BaseAwsResource]:
    out: List[BaseAwsResource] = []
    # LT shape via flatten (may return empty on some gjson impls)
    try:
        arr = rd.Get("block_device_mappings.#.ebs|@flatten").Array()
        for i, ebs in enumerate(arr):
            raw = _extract_block_values(ebs)
            if not raw or "volume_size" not in raw:
                try:
                    rv = rd.raw_values() or {}
                    bdm = (rv.get("block_device_mappings") or [])
                    if isinstance(bdm, list) and len(bdm) > i:
                        v = (bdm[i] or {}).get("ebs") or {}
                        vt = v.get("volume_type") or "gp2"
                        vs = v.get("volume_size")
                        io = v.get("iops")
                        raw = {k: v for k, v in {"volume_type": vt, "volume_size": vs, "iops": io}.items() if v not in (None, "", 0)}
                        if "volume_type" not in raw:
                            raw["volume_type"] = "gp2"
                except Exception:
                    pass
            out.append(_AwsBlockDevice(f"{parent_addr}.block_device_mapping[{i}]", region, raw or {"volume_type": "gp2"}))
    except Exception:
        pass

    # If flatten returned nothing, try planned_values directly for LT shape
    if not out:
        try:
            rv = rd.raw_values() or {}
            bdm = (rv.get("block_device_mappings") or [])
            if isinstance(bdm, list) and bdm:
                for i, item in enumerate(bdm):
                    v = (item or {}).get("ebs") or {}
                    vt = v.get("volume_type") or "gp2"
                    vs = v.get("volume_size")
                    io = v.get("iops")
                    raw = {k: v for k, v in {"volume_type": vt, "volume_size": vs, "iops": io}.items() if v not in (None, "", 0)}
                    if "volume_type" not in raw:
                        raw["volume_type"] = "gp2"
                    out.append(_AwsBlockDevice(f"{parent_addr}.block_device_mapping[{i}]", region, raw or {"volume_type": "gp2"}))
        except Exception:
            pass

    if out:
        return out

    # LC shape
    try:
        ebs_list = rd.Get("ebs_block_device").Array()
        for i, item in enumerate(ebs_list):
            raw = _extract_block_values(item)
            if not raw or "volume_size" not in raw:
                try:
                    rv = rd.raw_values() or {}
                    lst = (rv.get("ebs_block_device") or [])
                    if isinstance(lst, list) and len(lst) > i:
                        v = lst[i] or {}
                        vt = v.get("volume_type") or "gp2"
                        vs = v.get("volume_size")
                        io = v.get("iops")
                        raw = {k: v for k, v in {"volume_type": vt, "volume_size": vs, "iops": io}.items() if v not in (None, "", 0)}
                        if "volume_type" not in raw:
                            raw["volume_type"] = "gp2"
                except Exception:
                    pass
            out.append(_AwsBlockDevice(f"{parent_addr}.ebs_block_device[{i}]", region, raw or {"volume_type": "gp2"}))
    except Exception:
        pass

    # Expressions-only fallback (when not present in planned values yet)
    if not out:
        try:
            exprs = getattr(rd, "_config_expressions", {}) or {}
            bdm_expr = (exprs.get("block_device_mappings") or [])
            for i, item in enumerate(bdm_expr):
                ebs_list = (item or {}).get("ebs") or []
                e0 = (ebs_list[0] or {}) if ebs_list else {}
                def _const(d, k, default=None):
                    v = (d.get(k) or {}).get("constant_value")
                    return v if v is not None else default
                vt = _const(e0, "volume_type", "gp2")
                vs = _const(e0, "volume_size", None)
                io = _const(e0, "iops", None)
                raw = {k: v for k, v in {"volume_type": vt, "volume_size": vs, "iops": io}.items() if v not in (None, "", 0)}
                if "volume_type" not in raw:
                    raw["volume_type"] = "gp2"
                out.append(_AwsBlockDevice(f"{parent_addr}.block_device_mapping[{i}]", region, raw or {"volume_type": "gp2"}))
        except Exception:
            pass

    return out



# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _aws_launch_configuration(name: str, d: "ResourceData", region: str) -> BaseAwsResource:
    instance_type = d.Get("instance_type").String()
    res = BaseAwsResource(address=name, region=region, raw_values=d.raw_values())
    compute = _ASGComputeHours(res, instance_type, "on_demand", Decimal(1))

    subs: List[BaseAwsResource] = []
    subs.append(_root_block_device_from_rd(d, region, name))
    subs.extend(_ebs_block_devices_from_rd(d, region, name))

    res._set_price_components([compute])
    res._set_sub_resources(subs)
    return res


def _aws_launch_template(
    name: str,
    d: "ResourceData",
    region: str,
    on_demand_count: Decimal,
    spot_count: Decimal,
    instance_type_override: Optional[str] = None,
) -> BaseAwsResource:
    instance_type = instance_type_override or d.Get("instance_type").String()

    # Make a concrete raw_values dict and inject the override so mappings see it
    try:
        rv_obj = getattr(d, "raw_values", None)
        raw = rv_obj() if callable(rv_obj) else dict(rv_obj or {})
    except Exception:
        raw = {}
    if instance_type_override:
        raw["instance_type"] = instance_type_override

    rt = BaseAwsResource(address=name, region=region, raw_values=raw)

    pcs: List[BaseAwsPriceComponent] = []
    if on_demand_count > 0:
        base = _ASGComputeHours(rt, instance_type, "on_demand", Decimal(1))
        pcs.append(_ScaledPriceComponent(base, on_demand_count))
    if spot_count > 0:
        base = _ASGComputeHours(rt, instance_type, "spot", Decimal(1))
        pcs.append(_ScaledPriceComponent(base, spot_count))

    # Subresources (root + any EBS mappings), scaled by total instance count
    subs: List[BaseAwsResource] = []
    total = on_demand_count + spot_count
    rbd = _root_block_device_from_rd(d, region, name)
    subs.append(_multiply_quantities(rbd, total))
    for s in _ebs_block_devices_from_rd(d, region, name):
        subs.append(_multiply_quantities(s, total))

    rt._set_price_components(pcs)
    rt._set_sub_resources(subs)
    return rt


# ---------------------------------------------------------------------------
# Mixed Instances helpers
# ---------------------------------------------------------------------------

def _get_instance_type_and_count(container: Any, capacity: Decimal) -> Tuple[str, Decimal]:
    from decimal import ROUND_CEILING as RC

    instance_type = ""
    weighted = Decimal(1)
    count = capacity

    def _read_override_node(n) -> Tuple[str, Optional[Decimal]]:
        if n is None or not hasattr(n, "Exists") or not n.Exists():
            return "", None
        it = n.Get("instance_type").String() if n.Get("instance_type").Exists() else ""
        wc: Optional[Decimal] = None
        if n.Get("weighted_capacity").Exists():
            try:
                s = n.Get("weighted_capacity").String()
                wc = Decimal(s) if s else Decimal(n.Get("weighted_capacity").Int() or 1)
            except Exception:
                wc = Decimal(1)
        return it, wc

    try:
        n = None
        if hasattr(container, "Get"):
            n = container.Get("mixed_instances_policy.0.launch_template.0.override.0")
            if not (n and n.Exists()):
                n = container.Get("launch_template.0.override.0")
        it, wc = _read_override_node(n)
        if it:
            instance_type = it
        if wc is not None and wc > 0:
            weighted = wc
    except Exception:
        pass

    if not instance_type and hasattr(container, "Get"):
        try:
            n = container.Get("mixed_instances_policy.0.launch_template.0.override|@flatten.0")
            it, wc = _read_override_node(n)
            if it:
                instance_type = it
            if wc is not None and wc > 0:
                weighted = wc
        except Exception:
            pass

    if not instance_type and hasattr(container, "Get"):
        try:
            ov_arr_node = container.Get("mixed_instances_policy.0.launch_template.0.override")
            ov_arr = ov_arr_node.Array() if ov_arr_node and ov_arr_node.Exists() else []
            if ov_arr:
                it, wc = _read_override_node(ov_arr[0])
                if it:
                    instance_type = it
                if wc is not None and wc > 0:
                    weighted = wc
        except Exception:
            pass

    if not instance_type and hasattr(container, "__dict__"):
        try:
            expr = getattr(container, "_config_expressions", {}) or {}
            mip = (expr.get("mixed_instances_policy") or [])
            if mip:
                lt_list = (mip[0].get("launch_template") or [])
                if lt_list:
                    ovs = (lt_list[0].get("override") or [])
                    if ovs:
                        first = ovs[0] or {}
                        it = ((first.get("instance_type") or {}).get("constant_value")) or ""
                        if it:
                            instance_type = it
                        wc_raw = (first.get("weighted_capacity") or {}).get("constant_value")
                        if wc_raw is not None:
                            try:
                                weighted = Decimal(str(wc_raw))
                            except Exception:
                                pass
        except Exception:
            pass

    if not instance_type and hasattr(container, "raw_values"):
        try:
            rv = container.raw_values() or {}
            mip = (rv.get("mixed_instances_policy") or [])
            if mip:
                lts = (mip[0].get("launch_template") or [])
                if lts:
                    ovs = (lts[0].get("override") or [])
                    if ovs:
                        first = ovs[0]
                        it = first.get("instance_type") or ""
                        if it:
                            instance_type = it
                        wc = first.get("weighted_capacity")
                        if wc is not None:
                            try:
                                weighted = Decimal(str(wc))
                            except Exception:
                                pass
        except Exception:
            pass

    if weighted <= 0:
        weighted = Decimal(1)

    try:
        count = (capacity / weighted).to_integral_value(rounding=RC)
    except Exception:
        count = capacity

    return instance_type, count


def _calculate_on_demand_and_spot_counts(container: Any, total_count: Decimal) -> Tuple[Decimal, Decimal]:
    od_base = Decimal(0)
    od_perc = Decimal(100)

    try:
        n = getattr(container, "Get", None)
        if callable(n):
            dist = container.Get("mixed_instances_policy.0.instances_distribution.0")
            if dist and dist.Exists():
                if dist.Get("on_demand_base_capacity").Exists():
                    od_base = Decimal(dist.Get("on_demand_base_capacity").Int())
                if dist.Get("on_demand_percentage_above_base_capacity").Exists():
                    od_perc = Decimal(dist.Get("on_demand_percentage_above_base_capacity").Int())
    except Exception:
        pass

    if od_perc == Decimal(100) and od_base == Decimal(0):
        try:
            exprs = getattr(container, "_config_expressions", {}) or {}
            mip_list = (exprs.get("mixed_instances_policy") or [])
            if isinstance(mip_list, list) and mip_list:
                dist_list = (mip_list[0].get("instances_distribution") or [])
                if dist_list:
                    dist0 = dist_list[0]
                    ob = ((dist0.get("on_demand_base_capacity") or {}).get("constant_value"))
                    op = ((dist0.get("on_demand_percentage_above_base_capacity") or {}).get("constant_value"))
                    if ob is not None:
                        try:
                            od_base = Decimal(str(ob))
                        except Exception:
                            pass
                    if op is not None:
                        try:
                            od_perc = Decimal(str(op))
                        except Exception:
                            pass
        except Exception:
            pass

    remaining = total_count - od_base
    if remaining < 0:
        remaining = Decimal(0)

    addl = (remaining * od_perc / Decimal(100)).to_integral_value(rounding=ROUND_CEILING)
    on_demand_count = od_base + addl
    spot_count = total_count - on_demand_count
    if spot_count < 0:
        spot_count = Decimal(0)

    return on_demand_count, spot_count


# ---------------------------------------------------------------------------
# Top-level resource: Autoscaling Group
# ---------------------------------------------------------------------------

class AwsAutoscalingGroup(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any], rd: Optional["ResourceData"] = None):
        super().__init__(address, region, raw_values)
        self._set_price_components([])

        if rd is None:
            self._set_sub_resources([])
            return

        desired_capacity = Decimal(0)
        try:
            desired_capacity = Decimal(rd.Get("desired_capacity").Int())
        except Exception:
            desired_capacity = Decimal(_to_decimal((raw_values or {}).get("desired_capacity") or 0))

        sub_resources: List[BaseAwsResource] = []

        launch_config_refs = rd.References("launch_configuration")
        launch_template_refs = rd.References("launch_template.0.id")
        mixed_lt_refs = rd.References(
            "mixed_instances_policy.0.launch_template.0.launch_template_specification.0.launch_template_id"
        )

        if launch_config_refs:
            lc_rd = launch_config_refs[0]
            lc_res = _aws_launch_configuration(lc_rd.Address, lc_rd, region)
            sub_resources.append(_multiply_quantities(lc_res, desired_capacity))

        elif launch_template_refs:
            lt_rd = launch_template_refs[0]
            sub_resources.append(_aws_launch_template(lt_rd.Address, lt_rd, region, desired_capacity, Decimal(0)))

        elif mixed_lt_refs:
            lt_rd = mixed_lt_refs[0]
            override_type, total_count = _get_instance_type_and_count(rd, desired_capacity)
            on_demand_count, spot_count = _calculate_on_demand_and_spot_counts(rd, total_count)

            sub_resources.append(
                _aws_launch_template(
                    lt_rd.Address,
                    lt_rd,
                    region,
                    on_demand_count,
                    spot_count,
                    instance_type_override=override_type or lt_rd.Get("instance_type").String(),
                )
            )

        self._set_sub_resources(sub_resources)


def NewAutoscalingGroup(d: "ResourceData", u: "ResourceData") -> AwsAutoscalingGroup:
    def _val(x, default=None):
        if x is None:
            return default
        return x() if callable(x) else x

    addr = _val(getattr(d, "Address", None)) or _val(getattr(d, "address", None)) or "aws_autoscaling_group.unknown"
    region = _val(getattr(d, "Region", None)) or _val(getattr(d, "region", None)) or "us-east-1"

    raw_vals_attr = getattr(d, "raw_values", None)
    raw = raw_vals_attr() if callable(raw_vals_attr) else (raw_vals_attr or {})

    return AwsAutoscalingGroup(addr, region, raw, rd=d)


NewASG = NewAutoscalingGroup
