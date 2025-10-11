from __future__ import annotations

import os
import pytest

from plancosts.internal import testutil


@pytest.mark.skipif(
    os.getenv("SHORT") in ("1", "true", "True"),
    reason="skipping integration test in short mode",
)
def test_nat_gateway_integration():
    tf = r'''
resource "aws_nat_gateway" "nat" {
  allocation_id = "eip-12345678"
  subnet_id     = "subnet-12345678"
}
'''

    # Run the Terraform->plan->parse->price pipeline
    breakdowns = testutil.run_tf_cost_breakdown(tf)

    # Expected price hashes (API-dependent). This mirrors the Go test.
    expected_price_hashes = [
        ["aws_nat_gateway.nat", "hours", "6e137a9da0718f0ec80fb60866730ba9-d2c98780d7b6e36641b521f1f8145c6f"],
    ]

    # Extract produced hashes and compare (order-insensitive)
    got_hashes = testutil.extract_price_hashes(breakdowns)
    assert sorted(got_hashes, key=lambda x: (x[0], x[1])) == sorted(
        expected_price_hashes, key=lambda x: (x[0], x[1])
    )

    # Also assert the hourly cost equals the underlying unit price (like the Go test)
    pc_cost = testutil.price_component_cost_for(
        breakdowns, "aws_nat_gateway.nat", "hours"
    )
    assert pc_cost is not None, "price component cost not found for aws_nat_gateway.nat hours"
    assert pc_cost.hourly_cost == pc_cost.price_component.price()
