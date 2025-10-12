"""
AWS Lambda resource constructor — Python port of internal/terraform/aws/lambda.go

Creates a Lambda Function resource with a placeholder "Requests" price component.
The quantity multiplier emulates 1/730 per-hour placeholder used in the Go code.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Callable

# These imports assume your core resource layer exposes the same factories/classes
# used across the other AWS resources you've already ported.
from plancosts.resource.resource import (
    Resource,
    PriceComponent,
    ProductFilter,
    new_base_resource,
    new_base_price_component,
)


_HOURS_IN_MONTH = Decimal(730)


def _placeholder_quantity(_resource: Resource) -> Decimal:
    """
    Matches the Go logic:
      quantity := decimal.NewFromInt(1).Div(decimal.NewFromInt(730))
    """
    return Decimal(1) / _HOURS_IN_MONTH


def new_lambda_function(
    address: str,
    region: str,
    raw_values: Dict[str, Any],
) -> Resource:
    """
    Port of:
      func NewLambdaFunction(address string, region string, rawValues map[string]interface{}) resource.Resource
    """
    r: Resource = new_base_resource(address=address, raw_values=raw_values, has_cost=True)

    hours_product_filter = ProductFilter(
        vendor_name="aws",
        region=region,
        service="AWS Lambda",
        product_family="Lambda",
    )

    # Name/unit match the Go version's intent:
    # NewBasePriceComponent("Requests", r, "request", "hour", productFilter, nil)
    requests_pc: PriceComponent = new_base_price_component(
        name="Requests",
        resource=r,
        unit="request",
        hourly_unit="hour",
        product_filter=hours_product_filter,
        usage_filter=None,  # nil in Go
    )

    # Label + quantity multiplier ports:
    # requestsPlaceHolder.SetPriceOverrideLabel("coming soon")
    # requestsPlaceHolder.SetQuantityMultiplierFunc(placeHolderQuantity)
    requests_pc.set_price_override_label("coming soon")
    requests_pc.set_quantity_multiplier_func(_placeholder_quantity)

    r.add_price_component(requests_pc)
    return r
