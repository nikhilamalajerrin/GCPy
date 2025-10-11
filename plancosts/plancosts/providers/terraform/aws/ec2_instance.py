# plancosts/providers/terraform/aws/ec2_instance.py
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
    # Terraform can emit "size" (for volumes) or "volume_size" (for block devices)
    if "size" in raw and raw.get("size") not in (None, ""):
        return _to_decimal(raw.get("size"), Decimal(DEFAULT_VOLUME_SIZE))
    return _to_decimal(raw.get("volume_size"), Decimal(DEFAULT_VOLUME_SIZE))


def _bd_type(raw: Dict[str, Any]) -> str:
    # Terraform uses "volume_type" for instance block devices; EBS volume uses "type"
    return str(raw.get("volume_type") or raw.get("type") or "gp2")


def _bd_iops(raw: Dict[str, Any]) -> Decimal:
    return _to_decimal(raw.get("iops"), Decimal(0))


# ---------------- EBS Block Device Price Components ----------------


class Ec2BlockDeviceGB(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "Ec2BlockDevice"):
        # time_unit="month" → unit shown as GB/month in table renderer
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
        # Quantity = GB size of the device (default 8GB)
        self.SetQuantityMultiplierFunc(lambda r: _bd_size(r.raw_values()))
        self.unit_ = "GB/month"


class Ec2BlockDeviceIOPS(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "Ec2BlockDevice"):
        # time_unit="month" → unit shown as IOPS/month
        super().__init__(name=name, resource=resource, time_unit="month")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="System Operation"),
            # Target Provisioned IOPS usage directly; do NOT filter by volumeApiName here.
            Filter(key="usagetype", value="EBS:VolumeP-IOPS.piops"),
        ]
        # Quantity = IOPS value
        self.SetQuantityMultiplierFunc(lambda r: _bd_iops(r.raw_values()))
        self.unit_ = "IOPS/month"


class Ec2BlockDevice(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        pcs: List[BaseAwsPriceComponent] = [Ec2BlockDeviceGB("GB", self)]
        # Add IOPS component for both io1 and io2 devices
        if _bd_type(self.raw_values()) in ("io1", "io2"):
            pcs.append(Ec2BlockDeviceIOPS("IOPS", self))
        self._set_price_components(pcs)


# ---------------- EC2 Instance ----------------


class Ec2InstanceHours(BaseAwsPriceComponent):
    def __init__(self, resource: "Ec2Instance"):
        # Match Go label exactly: "instance hours (<type>)"
        it = resource.raw_values().get("instance_type") or ""
        name = f"instance hours ({it})" if it else "instance hours"
        super().__init__(name=name, resource=resource, time_unit="hour")
        self.default_filters = [
            Filter(key="servicecode", value="AmazonEC2"),
            Filter(key="productFamily", value="Compute Instance"),
            Filter(key="operatingSystem", value="Linux"),
            Filter(key="preInstalledSw", value="NA"),
            Filter(key="capacitystatus", value="Used"),
            # default tenancy; mapping may override
            Filter(key="tenancy", value="Shared"),
        ]
        self.value_mappings = [
            ValueMapping(from_key="instance_type", to_key="instanceType"),
            ValueMapping(from_key="tenancy", to_key="tenancy", map_func=_normalize_tenancy),
        ]
        # 1 unit per hour
        self.SetQuantityMultiplierFunc(lambda r: Decimal(1))


class Ec2Instance(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)

        # Top-level instance hours
        self._set_price_components([Ec2InstanceHours(self)])

        # ---- Sub-resources: root + additional EBS volumes ----
        subs: List[BaseAwsResource] = []

        # root_block_device can be dict or list[0] (Terraform JSON variants)
        rbd = self.raw_values().get("root_block_device")
        if isinstance(rbd, dict) and rbd:
            subs.append(Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), rbd))
        elif isinstance(rbd, list) and rbd and isinstance(rbd[0], dict):
            subs.append(Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), rbd[0]))
        else:
            # create empty one to trigger default 8GB logic in pricing
            subs.append(Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), {}))

        # ebs_block_device[*]
        ebs_list = self.raw_values().get("ebs_block_device") or []
        if isinstance(ebs_list, list):
            for i, item in enumerate(ebs_list):
                if isinstance(item, dict):
                    subs.append(Ec2BlockDevice(f"{self.address()}.ebs_block_device[{i}]", self.region(), item))

        self._set_sub_resources(subs)
