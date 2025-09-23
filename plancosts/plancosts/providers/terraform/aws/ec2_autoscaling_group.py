from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from plancosts.resource.filters  import Filter  # type hints

from .base import BaseAwsPriceComponent, BaseAwsResource

class WrappedPriceComponent(BaseAwsPriceComponent):
    def __init__(self, scaled_resource: "Ec2AutoscalingGroup", wrapped_pc: BaseAwsPriceComponent):
        super().__init__(name=wrapped_pc.name(), resource=wrapped_pc.resource(), time_unit=wrapped_pc.time_unit_)
        self._scaled_resource = scaled_resource
        self._wrapped_pc = wrapped_pc
        self.unit_ = wrapped_pc.unit()

    def filters(self) -> List[Filter]:
        return self._wrapped_pc.get_filters()

    def get_filters(self) -> List[Filter]:
        return self.filters()

    def calculate_hourly_cost(self, price: Decimal) -> Decimal:
        base_hourly = self._wrapped_pc.calculate_hourly_cost(price)
        return base_hourly * Decimal(self._scaled_resource.count())

    def set_price(self, price: Decimal) -> None:
        self._wrapped_pc.set_price(price)

    def hourly_cost(self) -> Decimal:
        return self._wrapped_pc.hourly_cost() * Decimal(self._scaled_resource.count())

    # quantity/unit for table (quantity scales by ASG count)
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

    def Unit(self) -> str:
        return self.unit()

    def Quantity(self) -> Decimal:
        return self.quantity()

class AutoscaledWrappedResource(BaseAwsResource):
    def __init__(self, address: str, scaled_resource: "Ec2AutoscalingGroup", wrapped: BaseAwsResource):
        super().__init__(address=address, region=wrapped.region(), raw_values=wrapped.raw_values())
        self._scaled_resource = scaled_resource
        self._wrapped = wrapped

        wrapped_pcs: List[BaseAwsPriceComponent] = []
        for pc in wrapped.price_components():
            wrapped_pcs.append(WrappedPriceComponent(scaled_resource, pc))
        self._set_price_components(wrapped_pcs)

        subs: List[BaseAwsResource] = []
        for sub in wrapped.sub_resources():
            suffix = sub.address().replace(wrapped.address(), "", 1)
            subs.append(AutoscaledWrappedResource(f"{self.address()}{suffix}", scaled_resource, sub))
        self._set_sub_resources(subs)

class Ec2AutoscalingGroup(BaseAwsResource):
    def __init__(self, address: str, region: str, raw_values: Dict[str, Any]):
        super().__init__(address=address, region=region, raw_values=raw_values)
        self._wrapped: Optional[AutoscaledWrappedResource] = None
        self._set_price_components([])

    def add_reference(self, name: str, resource: BaseAwsResource) -> None:
        super().add_reference(name, resource)
        if name in ("launch_configuration", "launch_template") and resource is not None:
            self._wrapped = AutoscaledWrappedResource(self.address(), self, resource)

    def count(self) -> int:
        val = self.raw_values().get("desired_capacity")
        try:
            return int(Decimal(str(val)))
        except Exception:
            return 1

    def price_components(self) -> List[BaseAwsPriceComponent]:
        if self._wrapped:
            return self._wrapped.price_components()
        return []

    def sub_resources(self) -> List[BaseAwsResource]:
        if self._wrapped:
            return self._wrapped.sub_resources()
        return []
