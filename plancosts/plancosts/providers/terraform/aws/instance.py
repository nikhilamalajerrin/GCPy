# plancosts/providers/terraform/aws/instance.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple

from plancosts.resource.filters import Filter, ValueMapping
from .base import (
    DEFAULT_VOLUME_SIZE,
    BaseAwsPriceComponent,
    BaseAwsResource,
    _to_decimal,
)

if TYPE_CHECKING:
    from plancosts.schema.resource_data import ResourceData


def _vals(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "raw_values"):
        attr = getattr(obj, "raw_values")
        try:
            return attr() if callable(attr) else (attr or {})
        except TypeError:
            return attr if isinstance(attr, dict) else {}
    return {}


def _extract_tuple_from_any(*args) -> Tuple[str, str, Dict[str, Any], Optional["ResourceData"]]:
    if len(args) >= 3 and isinstance(args[0], str) and isinstance(args[1], str) and isinstance(args[2], dict):
        address = args[0]
        region = args[1]
        raw_values: Dict[str, Any] = dict(args[2] or {})
        rd: Optional["ResourceData"] = args[3] if len(args) >= 4 else None
        return address, region, raw_values, rd

    if len(args) >= 1 and not isinstance(args[0], str):
        rd = args[0]
        try:
            address = getattr(rd, "Address", None) or getattr(rd, "address", "")
            rtype = getattr(rd, "Type", None) or getattr(rd, "type", "")
            raw_obj = getattr(rd, "raw_values", {})
            raw_values = raw_obj() if callable(raw_obj) else (raw_obj or {})
            region = raw_values.get("region") or "us-east-1"
            address = address or f"{rtype or 'aws_instance'}.instance"
        except Exception:
            address, region, raw_values = "aws_instance.instance", "us-east-1", {}
        return str(address), str(region), dict(raw_values or {}), rd
    raise TypeError("Unsupported AwsInstance constructor signature")


def _tenancy_to_api(val: Any) -> str:
    return "Dedicated" if f"{val}".strip().lower() == "dedicated" else "Shared"


def _bd_volume_type(values: Dict[str, Any]) -> str:
    t = values.get("volume_type")
    return str(t) if t else "gp2"


def _bd_volume_size(values: Dict[str, Any]) -> Decimal:
    return _to_decimal(values.get("volume_size"), Decimal(DEFAULT_VOLUME_SIZE))


def _bd_iops(values: Dict[str, Any]) -> Decimal:
    return _to_decimal(values.get("iops"), Decimal(0))


class _BlockDeviceGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "AwsBlockDevice"):
        super().__init__(name=name, resource=resource, time_unit="month")
        v = _vals(resource)
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage"),
            Filter(key="volumeApiName", value=_bd_volume_type(v)),
        ]
        self.value_mappings = [
            ValueMapping(from_key="volume_type", to_key="volumeApiName"),
        ]
        self.SetQuantityMultiplierFunc(lambda r: _bd_volume_size(_vals(r)))
        self.unit_ = "GB-months"


class _BlockDeviceIOPS(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "AwsBlockDevice"):
        super().__init__(name=name, resource=resource, time_unit="month")
        v = _vals(resource)
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            Filter(key="volumeApiName", value=_bd_volume_type(v)),
        ]
        self.value_mappings = [
            ValueMapping(from_key="volume_type", to_key="volumeApiName"),
        ]
        self.set_price_filter({
            "purchaseOption": "on_demand",
            "unit": "IOPS-Mo",
        })
        self.SetQuantityMultiplierFunc(lambda r: _bd_iops(_vals(r)))
        self.unit_ = "IOPS-Mo"


class AwsBlockDevice(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address, region, raw_values)
        v = _vals(self)
        vol_type = _bd_volume_type(v).lower()
        iops = _bd_iops(v)

        pcs: List[BaseAwsPriceComponent] = [_BlockDeviceGB("Storage", self)]
        if vol_type in {"io1", "io2"} and iops > 0:
            pcs.append(_BlockDeviceIOPS("Storage IOPS", self))
        self._set_price_components(pcs)


class _ComputeHours(BaseAwsPriceComponent):
    def __init__(self, resource: "AwsInstance"):
        v = _vals(resource)
        it = (v.get("instance_type") or "").strip()
        label = f"Compute (on-demand, {it})" if it else "Compute (on-demand)"
        super().__init__(name=label, resource=resource, time_unit="hour")

        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Compute Instance"),
            Filter(key="operatingSystem", value="Linux"),
            Filter(key="preInstalledSw", value="NA"),
            Filter(key="capacitystatus", value="Used"),
            Filter(key="tenancy", value="Shared"),
        ]
        self.value_mappings = [
            ValueMapping(from_key="instance_type", to_key="instanceType"),
            ValueMapping(from_key="tenancy", to_key="tenancy", map_func=_tenancy_to_api),
        ]
        self.set_price_filter({"purchaseOption": "on_demand"})
        self.unit_ = "hours"
        self.SetQuantityMultiplierFunc(lambda _r: Decimal(1))


class AwsInstance(BaseAwsResource):
    def __init__(self, *args, **_kwargs):
        address, region, raw_values, _rd = _extract_tuple_from_any(*args)
        super().__init__(address, region, raw_values)

        self._set_price_components([_ComputeHours(self)])
        subs: List[BaseAwsResource] = []

        rbd = _vals(self).get("root_block_device")
        if isinstance(rbd, dict):
            subs.append(AwsBlockDevice(f"{self.address()}.root_block_device", self.region(), rbd))
        elif isinstance(rbd, list) and rbd and isinstance(rbd[0], dict):
            subs.append(AwsBlockDevice(f"{self.address()}.root_block_device", self.region(), rbd[0]))
        else:
            subs.append(AwsBlockDevice(f"{self.address()}.root_block_device", self.region(), {}))

        ebs_list = _vals(self).get("ebs_block_device") or []
        if isinstance(ebs_list, list):
            for i, item in enumerate(ebs_list):
                if isinstance(item, dict):
                    subs.append(AwsBlockDevice(f"{self.address()}.ebs_block_device[{i}]", self.region(), item))

        self._set_sub_resources(subs)


NewInstance = AwsInstance
AwsInstance = AwsInstance
