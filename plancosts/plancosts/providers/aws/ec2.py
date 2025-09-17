"""
AWS EC2 instance pricing mappings.
"""
from plancosts.base.filters import Filter
from plancosts.base.mappings import PriceMapping, ResourceMapping, ValueMapping


# Block device mappings
block_device_gb = PriceMapping(
    time_unit="hour",
    value_mappings=[
        ValueMapping(from_key="volume_type", to_key="volumeApiName")
    ]
)

block_device_iops = PriceMapping(
    time_unit="hour",
    value_mappings=[
        ValueMapping(from_key="volume_type", to_key="volumeApiName")
    ],
    should_skip=lambda values: values.get("volume_type") != "io1"
)

block_device = ResourceMapping(
    price_mappings={
        "GB": block_device_gb,
        "IOPS": block_device_iops
    }
)

# EC2 instance mappings
ec2_instance_hours = PriceMapping(
    time_unit="hour",
    default_filters=[
        Filter(key="servicecode", value="AmazonEC2"),
        Filter(key="productFamily", value="Compute Instance"),
        Filter(key="operatingSystem", value="Linux"),
        Filter(key="preInstalledSw", value="NA"),
        Filter(key="capacitystatus", value="Used"),
        Filter(key="tenancy", value="Shared")
    ],
    value_mappings=[
        ValueMapping(from_key="instance_type", to_key="instanceType"),
        ValueMapping(from_key="tenancy", to_key="tenancy")
    ]
)

ec2_instance = ResourceMapping(
    price_mappings={
        "Instance hours": ec2_instance_hours
    },
    sub_resource_mappings={
        "root_block_device": block_device,
        "ebs_block_device": block_device
    }
)