"""
Typed AWS Auto Scaling Group (ASG) wrapper that reuses LC/LT resources.

Behavior:
- ASG does not define its own pricing filters; instead it *wraps* the referenced
  Launch Configuration or Launch Template resources and:
    • Multiplies all their price components' hourly costs by desired_capacity
    • Exposes the wrapped resource's sub-resources (e.g., block_device_mappings)
- Works even if references are missing (then produces no cost).

This mirrors the Go commit’s WrappedPriceComponent/AutoscaledResource pattern.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from plancosts.base.filters import \
    Filter  # only for type hints; not strictly needed

from .base import BaseAwsPriceComponent, BaseAwsResource

# ---------- Wrapped price component (multiplies by ASG count) ----------


class WrappedPriceComponent(BaseAwsPriceComponent):
    """
    Wraps an existing AwsPriceComponent and multiplies its hourly cost by the
    ASG's instance count (desired_capacity). Filters are delegated to the wrapped PC.
    """

    def __init__(
        self, scaled_resource: "Ec2AutoscalingGroup", wrapped_pc: BaseAwsPriceComponent
    ):
        # Create a "shadow" component with same name/resource/unit as the wrapped one.
        super().__init__(
            name=wrapped_pc.name(),
            resource=wrapped_pc.resource(),
            time_unit=wrapped_pc.time_unit,
        )
        self._scaled_resource = scaled_resource
        self._wrapped_pc = wrapped_pc

    # Delegate query filters directly to the wrapped component so we don't duplicate region/value filters
    def filters(self) -> List[Filter]:
        return self._wrapped_pc.get_filters()

    def get_filters(self) -> List[Filter]:
        return self.filters()

    # When calculate_hourly_cost is called, delegate to wrapped first, then multiply
    def calculate_hourly_cost(self, price: Decimal) -> Decimal:
        base_hourly = self._wrapped_pc.calculate_hourly_cost(price)
        return base_hourly * Decimal(self._scaled_resource.count())

    # When the new path sets a stored price via set_price + hourly_cost, we must also multiply
    def set_price(self, price: Decimal) -> None:
        self._wrapped_pc.set_price(price)

    def hourly_cost(self) -> Decimal:
        return self._wrapped_pc.hourly_cost() * Decimal(self._scaled_resource.count())


# ---------- Wrapper resource that mirrors an LC/LT but scales costs ----------


class AutoscaledWrappedResource(BaseAwsResource):
    """
    A resource that mirrors (wraps) another AwsResource but whose price components
    are all WrappedPriceComponent that multiply by the ASG desired count.
    """

    def __init__(
        self,
        address: str,
        scaled_resource: "Ec2AutoscalingGroup",
        wrapped: BaseAwsResource,
    ):
        super().__init__(
            address=address, region=wrapped.region(), raw_values=wrapped.raw_values()
        )
        self._scaled_resource = scaled_resource
        self._wrapped = wrapped

        # Wrap price components
        wrapped_pcs: List[BaseAwsPriceComponent] = []
        for pc in wrapped.price_components():
            wrapped_pcs.append(WrappedPriceComponent(scaled_resource, pc))
        self._set_price_components(wrapped_pcs)

        # Subresources are also wrapped recursively to preserve addressing and scaling
        subs: List[BaseAwsResource] = []
        for sub in wrapped.sub_resources():
            # Keep suffix of original address to append to ASG's address
            suffix = sub.address().replace(wrapped.address(), "", 1)
            subs.append(
                AutoscaledWrappedResource(
                    f"{self.address()}{suffix}", scaled_resource, sub
                )
            )
        self._set_sub_resources(subs)


# ---------- ASG resource itself ----------


class Ec2AutoscalingGroup(BaseAwsResource):
    """
    ASG that wraps either a Launch Configuration or Launch Template (if referenced).
    The wrapped resource provides instance-hour filters and block device mappings.
    """

    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        self._wrapped: Optional[AutoscaledWrappedResource] = None
        # ASG itself has no direct components; they come from the wrapper when a ref is present.
        self._set_price_components([])

    # Hook for the parser to wire references; when the LC/LT ref arrives, we construct the wrapper
    def add_reference(self, name: str, resource: BaseAwsResource) -> None:
        super().add_reference(name, resource)
        if name in ("launch_configuration", "launch_template") and resource is not None:
            self._wrapped = AutoscaledWrappedResource(self.address(), self, resource)

    # desired_capacity (defaults to 1 if missing/unparseable)
    def count(self) -> int:
        val = self.raw_values().get("desired_capacity")
        try:
            return int(Decimal(str(val)))
        except Exception:
            return 1

    # Expose wrapped components/subresources if present
    def price_components(self) -> List[BaseAwsPriceComponent]:
        if self._wrapped:
            return self._wrapped.price_components()
        return []

    def sub_resources(self) -> List[BaseAwsResource]:
        if self._wrapped:
            return self._wrapped.sub_resources()
        return []
