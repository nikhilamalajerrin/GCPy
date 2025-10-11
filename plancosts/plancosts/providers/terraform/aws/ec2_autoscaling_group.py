# plancosts/providers/terraform/aws/ec2_autoscaling_group.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from plancosts.resource.filters import Filter  # type: ignore

from .base import BaseAwsPriceComponent, BaseAwsResource


class WrappedPriceComponent(BaseAwsPriceComponent):
    """
    Wraps a price component and scales its quantity/cost by the ASG desired_capacity.
    Delegates product/price filters to the wrapped component so query building works.
    """

    def __init__(self, scaled_resource: "Ec2AutoscalingGroup", wrapped_pc: BaseAwsPriceComponent):
        # Preserve name/resource/time_unit from wrapped component
        super().__init__(name=wrapped_pc.name(), resource=wrapped_pc.resource(), time_unit=wrapped_pc.time_unit_)
        self._scaled_resource = scaled_resource
        self._wrapped_pc = wrapped_pc
        # Keep display unit identical to the wrapped component
        self.unit_ = wrapped_pc.unit()

    # ---- Filter access passthroughs ----
    def filters(self) -> List[Filter]:
        # Use wrapped filters exactly
        return self._wrapped_pc.get_filters()

    def get_filters(self) -> List[Filter]:
        return self.filters()

    # ---- Product/price filters (IMPORTANT: must be callables returning dict|None) ----
    def product_filter(self):
        # Delegate to wrapped component; returns a dict
        return self._wrapped_pc.product_filter()

    def price_filter(self):
        # Delegate; may return dict or None
        return self._wrapped_pc.price_filter()

    # ---- Price & cost ----
    def set_price(self, price: Decimal) -> None:
        self._wrapped_pc.set_price(price)

    def hourly_cost(self) -> Decimal:
        # Scale cost by ASG count
        return self._wrapped_pc.hourly_cost() * Decimal(self._scaled_resource.count())

    # ---- Quantity/Unit for table rendering ----
    def unit(self) -> str:
        return self._wrapped_pc.unit() if hasattr(self._wrapped_pc, "unit") else ""

    def quantity(self) -> Decimal:
        base_q = Decimal(1)
        if hasattr(self._wrapped_pc, "quantity"):
            try:
                base_q = Decimal(str(self._wrapped_pc.quantity()))
            except Exception:
                base_q = Decimal(1)
        return base_q * Decimal(self._scaled_resource.count())

    # ---- Go-name shims ----
    def Unit(self) -> str:
        return self.unit()

    def Quantity(self) -> Decimal:
        return self.quantity()


class AutoscaledWrappedResource(BaseAwsResource):
    """
    Mirrors the referenced LC/LT resource but with every price component wrapped
    to multiply by the ASG desired_capacity. Sub-resources are mirrored too.
    """

    def __init__(self, address: str, scaled_resource: "Ec2AutoscalingGroup", wrapped: BaseAwsResource):
        super().__init__(address=address, region=wrapped.region(), raw_values=wrapped.raw_values())
        self._scaled_resource = scaled_resource
        self._wrapped = wrapped

        # Wrap all price components
        wrapped_pcs: List[BaseAwsPriceComponent] = []
        for pc in wrapped.price_components():
            wrapped_pcs.append(WrappedPriceComponent(scaled_resource, pc))
        self._set_price_components(wrapped_pcs)

        # Recursively mirror sub-resources
        subs: List[BaseAwsResource] = []
        for sub in wrapped.sub_resources():
            suffix = sub.address().replace(wrapped.address(), "", 1)
            subs.append(AutoscaledWrappedResource(f"{self.address()}{suffix}", scaled_resource, sub))
        self._set_sub_resources(subs)


class Ec2AutoscalingGroup(BaseAwsResource):
    """
    ASG that, once it gets a reference to a launch_configuration or launch_template,
    exposes a wrapped/scaled view of that resource so pricing scales with desired_capacity.
    """

    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        self._wrapped: Optional[AutoscaledWrappedResource] = None
        self._set_price_components([])

    # Wire LC/LT reference → wrap and scale it
    def add_reference(self, name: str, resource: BaseAwsResource) -> None:
        super().add_reference(name, resource)
        if name in ("launch_configuration", "launch_template", "launch_configuration_id", "launch_template_id") and resource is not None:
            self._wrapped = AutoscaledWrappedResource(self.address(), self, resource)

    def count(self) -> int:
        val = self.raw_values().get("desired_capacity")
        try:
            return int(Decimal(str(val)))
        except Exception:
            return 1

    # Expose wrapped components/subresources (scaled)
    def price_components(self) -> List[BaseAwsPriceComponent]:
        if self._wrapped:
            return self._wrapped.price_components()
        return []

    def sub_resources(self) -> List[BaseAwsResource]:
        if self._wrapped:
            return self._wrapped.sub_resources()
        return []
