from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from plancosts.resource.filters import Filter, ValueMapping

from .base import (
    DEFAULT_VOLUME_SIZE,
    BaseAwsPriceComponent,
    BaseAwsResource,
    _to_decimal,
)

def _normalize_tenancy(v: Any) -> str:
    return "Dedicated" if f"{v}" == "dedicated" else "Shared"

def _bd_size(raw: Dict[str, Any]) -> Decimal:
    if "size" in raw:
        return _to_decimal(raw.get("size"), Decimal(DEFAULT_VOLUME_SIZE))
    return _to_decimal(raw.get("volume_size"), Decimal(DEFAULT_VOLUME_SIZE))

def _bd_type(raw: Dict[str, Any]) -> str:
    return str(raw.get("volume_type") or raw.get("type") or "gp2")

def _bd_iops(raw: Dict[str, Any]) -> Decimal:
    return _to_decimal(raw.get("iops"), Decimal(0))

class Ec2BlockDeviceGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "Ec2BlockDevice"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Storage"),
            Filter(key="volumeApiName", value="gp2"),
        ]
        self.value_mappings = [
            ValueMapping(from_key="volume_type", to_key="volumeApiName"),
            ValueMapping(from_key="type", to_key="volumeApiName"),
        ]
        self.unit_ = "GB/month"
        self.SetQuantityMultiplierFunc(lambda r: _bd_size(r.RawValues()))

    def hourly_cost(self) -> Decimal:
        base_hourly = super().hourly_cost()
        size = _bd_size(self.resource().raw_values())
        return base_hourly * size

class Ec2BlockDeviceIOPS(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "Ec2BlockDevice"):
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            Filter(key="usagetype", value="/EBS:VolumeP-IOPS.piops/", operation="REGEX"),
            Filter(key="volumeApiName", value="gp2"),
        ]
        self.value_mappings = [
            ValueMapping(from_key="volume_type", to_key="volumeApiName"),
            ValueMapping(from_key="type", to_key="volumeApiName"),
        ]
        self.unit_ = "IOPS/month"
        self.SetQuantityMultiplierFunc(lambda r: _bd_iops(r.RawValues()))

    def hourly_cost(self) -> Decimal:
        base_hourly = super().hourly_cost()
        iops = _bd_iops(self.resource().raw_values())
        return base_hourly * iops

class Ec2BlockDevice(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        pcs: List[BaseAwsPriceComponent] = [Ec2BlockDeviceGB("GB", self)]
        if _bd_type(self.raw_values()) == "io1":
            pcs.append(Ec2BlockDeviceIOPS("IOPS", self))
        self._set_price_components(pcs)

class Ec2InstanceHours(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "Ec2Instance"):
        super().__init__(name=name, resource=resource, time_unit="hour")
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
            ValueMapping(from_key="tenancy", to_key="tenancy", map_func=_normalize_tenancy),
        ]
        self.unit_ = "hour"
        self.SetQuantityMultiplierFunc(lambda r: Decimal(1))

class Ec2Instance(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        self._set_price_components([Ec2InstanceHours("Instance hours", self)])

        subs: List[BaseAwsResource] = []
        rbd = self.raw_values().get("root_block_device")
        if isinstance(rbd, dict) and rbd:
            subs.append(Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), rbd))
        elif isinstance(rbd, list) and rbd and isinstance(rbd[0], dict):
            subs.append(Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), rbd[0]))
        else:
            subs.append(Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), {}))

        ebs_list = self.raw_values().get("ebs_block_device") or []
        if isinstance(ebs_list, list):
            for i, item in enumerate(ebs_list):
                if isinstance(item, dict):
                    subs.append(Ec2BlockDevice(f"{self.address()}.ebs_block_device[{i}]", self.region(), item))
        self._set_sub_resources(subs)
