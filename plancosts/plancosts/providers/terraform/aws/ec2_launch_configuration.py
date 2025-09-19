from __future__ import annotations

from typing import Any, Dict, List

from plancosts.base.filters import Filter, ValueMapping
from plancosts.base.resource import Resource
from plancosts.providers.terraform.aws.base import (BaseAwsPriceComponent,
                                                    BaseAwsResource)
from plancosts.providers.terraform.aws.ec2_instance import Ec2BlockDevice


def _normalize_tenancy(v: object) -> str:
    return "Dedicated" if f"{v}" == "dedicated" else "Shared"


class Ec2LaunchConfigurationHours(BaseAwsPriceComponent):
    def __init__(self, resource: "Ec2LaunchConfiguration") -> None:
        super().__init__(name="Instance hours", resource=resource, time_unit="hour")
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
            ValueMapping(
                from_key="placement_tenancy",
                to_key="tenancy",
                map_func=_normalize_tenancy,
            ),
        ]


class Ec2LaunchConfiguration(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]) -> None:
        super().__init__(address, region, raw_values)
        self._set_price_components([Ec2LaunchConfigurationHours(self)])

        subs: List[Resource] = []

        # root_block_device (default to 8GB if missing/empty)
        root_bds = self.raw_values().get("root_block_device")
        if isinstance(root_bds, list) and root_bds and isinstance(root_bds[0], dict):
            subs.append(
                Ec2BlockDevice(
                    f"{self.address()}.root_block_device", self.region(), root_bds[0]
                )
            )
        else:
            subs.append(
                Ec2BlockDevice(f"{self.address()}.root_block_device", self.region(), {})
            )

        # ebs_block_device (0..n)
        ebs_bds = self.raw_values().get("ebs_block_device") or []
        if isinstance(ebs_bds, list):
            for i, bd in enumerate(ebs_bds):
                if isinstance(bd, dict):
                    subs.append(
                        Ec2BlockDevice(
                            f"{self.address()}.ebs_block_device[{i}]", self.region(), bd
                        )
                    )

        # legacy block_device_mappings[].ebs[0]
        bdm = self.raw_values().get("block_device_mappings") or []
        if isinstance(bdm, list):
            for i, m in enumerate(bdm):
                if isinstance(m, dict):
                    ebs = m.get("ebs")
                    if isinstance(ebs, list) and ebs and isinstance(ebs[0], dict):
                        subs.append(
                            Ec2BlockDevice(
                                f"{self.address()}.block_device_mappings[{i}]",
                                self.region(),
                                ebs[0],
                            )
                        )
        self._set_sub_resources(subs)

    def price_components(self):
        return list(self._price_components)

    def sub_resources(self):
        return list(self._sub_resources)
