# plancosts/providers/terraform/aws/ec2_launch_template.py
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Optional

from plancosts.resource.filters import Filter, ValueMapping
from .base import BaseAwsPriceComponent, BaseAwsResource
from .ec2_instance import Ec2BlockDevice


def _lt_quantity_share_factory(
    purchase_option: str, on_demand_base_count: int, on_demand_perc: int
):
    """
    Returns a quantity fn that yields the FRACTION of instances billed under
    this purchase option, relative to the ASG/parent resource count.

    Mirrors Go's ec2LaunchTemplateHoursQuantityFactory:
      - Start with on_demand_base_count
      - Remaining * (on_demand_perc / 100) are also on-demand
      - The rest are spot
      - If purchaseOptionCount == 0 or total == 0 → 0
      - Otherwise return purchaseOptionCount / total
    """
    def _fn(res: BaseAwsResource) -> Decimal:
        total = int(res.ResourceCount()) if hasattr(res, "ResourceCount") else 1
        if total <= 0:
            return Decimal(0)

        on_demand = on_demand_base_count
        remaining = max(total - on_demand, 0)
        on_demand += int(math.ceil(remaining * (on_demand_perc / 100.0)))
        on_demand = min(on_demand, total)
        spot = total - on_demand

        purchase_count = on_demand if purchase_option == "on_demand" else spot
        if purchase_count == 0:
            return Decimal(0)

        return (Decimal(purchase_count) / Decimal(total))
    return _fn


class _LaunchTemplateHours(BaseAwsPriceComponent):
    """
    Price component for LT instance hours (parametrized by purchase option).
    """
    def __init__(
        self,
        resource: "Ec2LaunchTemplate",
        instance_type: str,
        purchase_option: str,  # "on_demand" | "spot"
        on_demand_base_count: int,
        on_demand_perc: int,
        is_spot_label: bool = False,
    ):
        # Label: "instance hours (m5.large)" or "... (m5.large, spot)"
        name = f"instance hours ({instance_type}"
        if is_spot_label:
            name += ", spot"
        name += ")"

        super().__init__(name=name, resource=resource, time_unit="hour")

        # Filters match Go's hoursProductFilter + PriceFilter
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
        ]

        # Purchase option filter (queried by GraphQL layer)
        self.set_price_filter({"purchaseOption": purchase_option})

        # Quantity is the FRACTION of instances billed under this option.
        # BaseAwsPriceComponent.Quantity() will multiply by (month/hour)*ResourceCount().
        self.SetQuantityMultiplierFunc(
            _lt_quantity_share_factory(purchase_option, on_demand_base_count, on_demand_perc)
        )


class Ec2LaunchTemplate(BaseAwsResource):
    """
    Mirrors Go behavior:
      - Adds on-demand hours PC if onDemandBaseCount>0 OR onDemandPerc>0
      - Adds spot hours PC if onDemandPerc != 100
      - Always exposes EBS block devices (root + block_device_mappings[*].ebs)
    """

    def __init__(
        self,
        address: str,
        region: str,
        raw_values: Dict[str, Any],
        on_demand_base_count: int = 0,
        on_demand_perc: int = 0,
    ):
        super().__init__(address=address, region=region, raw_values=raw_values)

        pcs: List[BaseAwsPriceComponent] = []

        it = str(raw_values.get("instance_type") or "")

        # On-demand component (only if base>0 or perc>0)
        if on_demand_base_count > 0 or on_demand_perc > 0:
            pcs.append(
                _LaunchTemplateHours(
                    self,
                    instance_type=it,
                    purchase_option="on_demand",
                    on_demand_base_count=on_demand_base_count,
                    on_demand_perc=on_demand_perc,
                    is_spot_label=False,
                )
            )

        # Spot component (when some share remains for spot)
        if on_demand_perc != 100:
            pcs.append(
                _LaunchTemplateHours(
                    self,
                    instance_type=it,
                    purchase_option="spot",
                    on_demand_base_count=on_demand_base_count,
                    on_demand_perc=on_demand_perc,
                    is_spot_label=True,
                )
            )

        self._set_price_components(pcs)

        # -------- Sub-resources: block devices --------
        subs: List[BaseAwsResource] = []

        # root_block_device (dict or list[0])
        rbd_vals: Dict[str, Any] = {}
        rbd = raw_values.get("root_block_device")
        if isinstance(rbd, list) and rbd and isinstance(rbd[0], dict):
            rbd_vals = rbd[0]
        subs.append(Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), rbd_vals))

        # block_device_mappings[*].ebs (dict or 1-elem list)
        bdm = raw_values.get("block_device_mappings")
        if isinstance(bdm, list):
            for i, entry in enumerate(bdm):
                if not isinstance(entry, dict):
                    continue
                ebs = entry.get("ebs")
                ebs_vals: Optional[Dict[str, Any]] = None
                if isinstance(ebs, dict):
                    ebs_vals = ebs
                elif isinstance(ebs, list) and ebs and isinstance(ebs[0], dict):
                    ebs_vals = ebs[0]
                if ebs_vals is not None:
                    subs.append(
                        Ec2BlockDevice(
                            f"{self.address()}.block_device_mappings[{i}]",
                            self.region(),
                            ebs_vals,
                        )
                    )

        self._set_sub_resources(subs)
