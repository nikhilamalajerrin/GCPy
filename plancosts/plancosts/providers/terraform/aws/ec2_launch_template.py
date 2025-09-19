"""
Typed AWS EC2 Launch Template (aws_terraform).
- Not costed directly (non_costable), but exposes:
  - "Instance hours" price component (for wrapping by ASG)
  - block_device_mappings as typed Ec2BlockDevice subresources
"""

from __future__ import annotations

from typing import Any, Dict, List

from plancosts.base.filters import Filter, ValueMapping

from .base import BaseAwsPriceComponent, BaseAwsResource
from .ec2_instance import Ec2BlockDevice


class Ec2LaunchTemplateHours(BaseAwsPriceComponent):
    def __init__(self, name: str, resource: "Ec2LaunchTemplate"):
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
        ]


class Ec2LaunchTemplate(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)

        # Expose hours component so ASG wrappers can reuse its filters
        self._set_price_components([Ec2LaunchTemplateHours("Instance hours", self)])

        # Build block device subresources from block_device_mappings[*].ebs[0]
        subs: List[BaseAwsResource] = []
        bdm = self.raw_values().get("block_device_mappings")
        if isinstance(bdm, list):
            for i, entry in enumerate(bdm):
                if not isinstance(entry, dict):
                    continue
                ebs = entry.get("ebs")
                if isinstance(ebs, list) and ebs and isinstance(ebs[0], dict):
                    subs.append(
                        Ec2BlockDevice(
                            f"{self.address()}.block_device_mappings[{i}]",
                            self.region(),
                            ebs[0],
                        )
                    )
        self._set_sub_resources(subs)

    # Do not cost LTs directly; they’re used via ASG wrapping
    def non_costable(self) -> bool:
        return True
