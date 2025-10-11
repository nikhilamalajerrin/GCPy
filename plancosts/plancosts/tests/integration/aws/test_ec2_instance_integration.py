# plancosts/tests/integration/aws/test_ec2_instance_integration.py
from __future__ import annotations

import os
from decimal import Decimal

import pytest

from plancosts.internal.testutil import (
    run_tf_cost_breakdown,
    extract_price_hashes,
    price_component_cost_for,
)

# Skip integration if user wants a fast run (similar spirit to Go's -short)
pytestmark = pytest.mark.skipif(
    os.getenv("PLANCOSTS_SKIP_INTEGRATION") == "1",
    reason="skipping integration test (PLANCOSTS_SKIP_INTEGRATION=1)",
)


def test_ec2_instance_integration():
    tf = r'''
resource "aws_instance" "instance1" {
  ami           = "fake_ami"
  instance_type = "m3.medium"

  root_block_device {
    volume_size = 10
  }

  ebs_block_device {
    device_name = "xvdf"
    volume_size = 10
  }

  ebs_block_device {
    device_name = "xvdg"
    volume_type = "standard"
    volume_size = 20
  }

  ebs_block_device {
    device_name = "xvdh"
    volume_type = "sc1"
    volume_size = 30
  }

  ebs_block_device {
    device_name = "xvdi"
    volume_type = "io1"
    volume_size = 40
    iops        = 1000
  }
}
'''

    # Run terraform -> plan.json -> parse -> price queries -> breakdowns
    resource_cost_breakdowns = run_tf_cost_breakdown(tf)

    # These hashes come from the reference Go test; they validate we picked
    # the same product+price as Infracost does. If the upstream pricing DB
    # changes, only these hashes should change—math assertions below still hold.
    expected_price_hashes = [
        ["aws_instance.instance1", "instance hours (m3.medium)", "666e02bbe686f6950fd8a47a55e83a75-d2c98780d7b6e36641b521f1f8145c6f"],
        ["aws_instance.instance1.root_block_device", "GB", "efa8e70ebe004d2e9527fd30d50d09b2-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[0]", "GB", "efa8e70ebe004d2e9527fd30d50d09b2-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[1]", "GB", "0ed17ed1777b7be91f5b5ce79916d8d8-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[2]", "GB", "3122df29367c2460c76537cccf0eadb5-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[3]", "GB", "99450513de8c131ee2151e1b319d8143-ee3dd7e4624338037ca6fea0933a662f"],
        ["aws_instance.instance1.ebs_block_device[3]", "IOPS", "d5c5e1fb9b8ded55c336f6ae87aa2c3b-9c483347596633f8cf3ab7fdd5502b78"],
    ]

    price_hash_results = extract_price_hashes(resource_cost_breakdowns)
    assert price_hash_results == expected_price_hashes

    # === math checks (cost = unit price * quantity) ===
    # instance hours
    pc = price_component_cost_for(resource_cost_breakdowns, "aws_instance.instance1", "instance hours (m3.medium)")
    assert pc is not None
    assert pc.hourly_cost == pc.price_component.price()

    # root volume (10 GB)
    pc = price_component_cost_for(resource_cost_breakdowns, "aws_instance.instance1.root_block_device", "GB")
    assert pc is not None
    assert pc.monthly_cost == pc.price_component.price() * Decimal(10)

    # ebs_block_device[0] (10 GB, default gp2)
    pc = price_component_cost_for(resource_cost_breakdowns, "aws_instance.instance1.ebs_block_device[0]", "GB")
    assert pc is not None
    assert pc.monthly_cost == pc.price_component.price() * Decimal(10)

    # ebs_block_device[1] (20 GB, magnetic/standard)
    pc = price_component_cost_for(resource_cost_breakdowns, "aws_instance.instance1.ebs_block_device[1]", "GB")
    assert pc is not None
    assert pc.monthly_cost == pc.price_component.price() * Decimal(20)

    # ebs_block_device[2] (30 GB, sc1)
    pc = price_component_cost_for(resource_cost_breakdowns, "aws_instance.instance1.ebs_block_device[2]", "GB")
    assert pc is not None
    assert pc.monthly_cost == pc.price_component.price() * Decimal(30)

    # ebs_block_device[3] (40 GB, io1 capacity)
    pc = price_component_cost_for(resource_cost_breakdowns, "aws_instance.instance1.ebs_block_device[3]", "GB")
    assert pc is not None
    assert pc.monthly_cost == pc.price_component.price() * Decimal(40)

    # ebs_block_device[3] (IOPS = 1000)
    pc = price_component_cost_for(resource_cost_breakdowns, "aws_instance.instance1.ebs_block_device[3]", "IOPS")
    assert pc is not None
    assert pc.monthly_cost == pc.price_component.price() * Decimal(1000)
