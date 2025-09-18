"""
AWS EC2 instance pricing mappings.
"""
from __future__ import annotations

from plancosts.base.filters import Filter
from plancosts.base.mappings import PriceMapping, ResourceMapping, ValueMapping
from . import ebs as aws_ebs

Ec2BlockDeviceGB = PriceMapping(
    time_unit=aws_ebs.EbsVolumeGB.time_unit,
    default_filters=list(aws_ebs.EbsVolumeGB.default_filters),
    calculate_cost=aws_ebs.EbsVolumeGB.calculate_cost,
    value_mappings=[ValueMapping(from_key="volume_type", to_key="volumeApiName")],
)

Ec2BlockDeviceIOPS = PriceMapping(
    time_unit=aws_ebs.EbsVolumeIOPS.time_unit,
    default_filters=list(aws_ebs.EbsVolumeIOPS.default_filters),
    calculate_cost=aws_ebs.EbsVolumeIOPS.calculate_cost,
    value_mappings=[ValueMapping(from_key="volume_type", to_key="volumeApiName")],
)

Ec2BlockDevice = ResourceMapping(price_mappings={"GB": Ec2BlockDeviceGB, "IOPS": Ec2BlockDeviceIOPS})

# Exportable instance-hours mapping (used by ASG)
Ec2InstanceHours = PriceMapping(
    time_unit="hour",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="Compute Instance"),
        Filter(key="operatingSystem", value="Linux"),
        Filter(key="preInstalledSw", value="NA"),
        Filter(key="capacitystatus", value="Used"),
        Filter(key="tenancy", value="Shared"),
    ],
    value_mappings=[
        ValueMapping(from_key="instance_type", to_key="instanceType"),
        ValueMapping(from_key="tenancy", to_key="tenancy"),
    ],
)

Ec2Instance = ResourceMapping(
    price_mappings={"Instance hours": Ec2InstanceHours},
    sub_resource_mappings={
        "root_block_device": Ec2BlockDevice,
        "ebs_block_device": Ec2BlockDevice,
    },
)
