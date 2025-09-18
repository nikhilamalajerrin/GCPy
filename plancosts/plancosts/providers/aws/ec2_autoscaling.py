"""
AWS Auto Scaling Group pricing mappings.
Safe guards for missing references/fields.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Dict, Any, Optional

from plancosts.base.filters import Filter
from plancosts.base.mappings import PriceMapping, ResourceMapping
from .ec2 import Ec2BlockDeviceGB, Ec2BlockDeviceIOPS, Ec2InstanceHours


def _first_ebs_block(resource) -> Dict[str, Any]:
    """Return first EBS block mapping dict or {}."""
    ebs = resource.raw_values().get("ebs")
    if isinstance(ebs, list) and ebs:
        first = ebs[0]
        if isinstance(first, dict):
            return first
    return {}

def _num(val, default: Decimal = Decimal(0)) -> Decimal:
    try:
        return Decimal(str(val))
    except Exception:
        return default

# Block device mapping for ASG (reads nested "ebs" fields on the subresource)
Ec2BlockDeviceMappingGB = PriceMapping(
    time_unit=Ec2BlockDeviceGB.time_unit,
    default_filters=list(Ec2BlockDeviceGB.default_filters),
    override_filters=lambda resource: [
        Filter(key="volumeApiName", value=_first_ebs_block(resource).get("volume_type", "gp2"))
    ],
    calculate_cost=lambda price, resource: price * _num(_first_ebs_block(resource).get("volume_size", 0)),
)

Ec2BlockDeviceMappingIOPS = PriceMapping(
    time_unit=Ec2BlockDeviceIOPS.time_unit,
    default_filters=list(Ec2BlockDeviceIOPS.default_filters),
    override_filters=lambda resource: [
        Filter(key="volumeApiName", value=_first_ebs_block(resource).get("volume_type", "gp2"))
    ],
    calculate_cost=lambda price, resource: price * _num(_first_ebs_block(resource).get("iops", 0)),
    should_skip=lambda values: (
        isinstance(values.get("ebs"), list)
        and values["ebs"]
        and isinstance(values["ebs"][0], dict)
        and values["ebs"][0].get("volume_type") != "io1"
    ),
)

Ec2BlockDeviceMapping = ResourceMapping(
    price_mappings={"GB": Ec2BlockDeviceMappingGB, "IOPS": Ec2BlockDeviceMappingIOPS}
)

# ----------------- Launch Configuration variant -----------------
def _asg_lc_override_filters(resource) -> List[Filter]:
    out: List[Filter] = []
    lc = resource.references().get("launch_configuration")
    if lc:
        itype = (lc.raw_values() or {}).get("instance_type")
        if itype:
            out.append(Filter(key="instanceType", value=itype))
        tenancy = (lc.raw_values() or {}).get("placement_tenancy")
        if tenancy:
            out.append(Filter(key="tenancy", value=tenancy))
    return out

def _override_block_device_mappings_from_lc(resource) -> Dict[str, List[dict]]:
    raw: Dict[str, List[dict]] = {}
    lc = resource.references().get("launch_configuration")
    if lc:
        bd = lc.raw_values().get("block_device_mappings")
        if isinstance(bd, list):
            raw["block_device_mappings"] = [x for x in bd if isinstance(x, dict)]
    return raw

AutoscalingGroupLaunchConfigurationInstanceHours = PriceMapping(
    time_unit=Ec2InstanceHours.time_unit,
    default_filters=list(Ec2InstanceHours.default_filters),
    calculate_cost=Ec2InstanceHours.calculate_cost,
    override_filters=_asg_lc_override_filters,
)

AutoscalingGroupLaunchConfiguration = ResourceMapping(
    price_mappings={"Instance hours": AutoscalingGroupLaunchConfigurationInstanceHours},
    sub_resource_mappings={"block_device_mappings": Ec2BlockDeviceMapping},
    override_sub_resource_raw_values=_override_block_device_mappings_from_lc,
)

# ----------------- Launch Template variant -----------------
def _asg_lt_override_filters(resource) -> List[Filter]:
    lt = resource.references().get("launch_template")
    if lt:
        itype = (lt.raw_values() or {}).get("instance_type")
        if itype:
            return [Filter(key="instanceType", value=itype)]
    return []

def _override_block_device_mappings_from_lt(resource) -> Dict[str, List[dict]]:
    raw: Dict[str, List[dict]] = {}
    lt = resource.references().get("launch_template")
    if lt:
        bd = lt.raw_values().get("block_device_mappings")
        if isinstance(bd, list):
            raw["block_device_mappings"] = [x for x in bd if isinstance(x, dict)]
    return raw

def _adjust_by_desired_capacity(resource, cost: Decimal) -> Decimal:
    desired = resource.raw_values().get("desired_capacity")
    try:
        n = Decimal(str(desired)) if desired is not None else Decimal(1)
    except Exception:
        n = Decimal(1)
    return cost * n

AutoscalingGroupLaunchTemplateInstanceHours = PriceMapping(
    time_unit=Ec2InstanceHours.time_unit,
    default_filters=list(Ec2InstanceHours.default_filters),
    calculate_cost=Ec2InstanceHours.calculate_cost,
    override_filters=_asg_lt_override_filters,
)

AutoscalingGroupLaunchTemplate = ResourceMapping(
    price_mappings={"Instance hours": AutoscalingGroupLaunchTemplateInstanceHours},
    sub_resource_mappings={"block_device_mappings": Ec2BlockDeviceMapping},
    override_sub_resource_raw_values=_override_block_device_mappings_from_lt,
    adjust_cost=_adjust_by_desired_capacity,
)
