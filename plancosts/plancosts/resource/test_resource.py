from __future__ import annotations

from decimal import Decimal

from plancosts.resource.resource import (
    BasePriceComponent,
    BaseResource,
    flatten_sub_resources,
)


def test_flatten_sub_resources():
    r1 = BaseResource("r1", {}, True)
    r2 = BaseResource("r2", {}, True)
    r3 = BaseResource("r3", {}, True)
    r4 = BaseResource("r4", {}, True)
    r5 = BaseResource("r5", {}, True)
    r6 = BaseResource("r6", {}, True)

    r1.AddSubResource(r2)
    r1.AddSubResource(r3)
    r2.AddSubResource(r4)
    r2.AddSubResource(r5)
    r4.AddSubResource(r6)

    result = flatten_sub_resources(r1)
    assert [r.Address() for r in result] == ["r2", "r4", "r6", "r5", "r3"]


def test_base_price_component_quantity():
    r1 = BaseResource("r1", {}, True)
    monthly = BasePriceComponent("monthlyPc", r1, "unit", "month")
    hourly = BasePriceComponent("hourlyPc", r1, "unit", "hour")

    # Monthly → 1
    assert monthly.Quantity() == Decimal("1.000000")

    # Hourly → 730
    assert hourly.Quantity() == Decimal("730.000000")

    # ResourceCount multiplies quantity
    r1.SetResourceCount(2)
    assert hourly.Quantity() == Decimal("1460.000000")
    r1.SetResourceCount(1)

    # quantity multiplier (×3) → 2190
    hourly.SetQuantityMultiplierFunc(lambda _r: Decimal(3))
    assert hourly.Quantity() == Decimal("2190.000000")


def test_base_price_component_hourly_cost():
    r1 = BaseResource("r1", {}, True)
    monthly = BasePriceComponent("monthlyPc", r1, "unit", "month")
    hourly = BasePriceComponent("hourlyPc", r1, "unit", "hour")

    # 0 price → 0 hourly cost
    assert hourly.HourlyCost() == Decimal("0")

    # Hourly price 0.2, multiplier 2 → 0.4
    hourly.SetPrice(Decimal("0.2"))
    hourly.SetQuantityMultiplierFunc(lambda _r: Decimal(2))
    assert hourly.HourlyCost().quantize(Decimal("0.00")) == Decimal("0.40")

    # Monthly price 7.3, multiplier 4:
    # Quantity = 4; hourly cost = 7.3 * 4 / 730 = 0.04
    monthly.SetPrice(Decimal("7.3"))
    monthly.SetQuantityMultiplierFunc(lambda _r: Decimal(4))
    assert monthly.HourlyCost().quantize(Decimal("0.00")) == Decimal("0.04")


def test_base_resource_sorting():
    r1 = BaseResource("r1", {}, True)
    r2 = BaseResource("charlie", {}, True)
    r3 = BaseResource("alpha", {}, True)
    r4 = BaseResource("bravo", {}, True)

    r1.AddSubResource(r2)
    r1.AddSubResource(r3)
    r1.AddSubResource(r4)

    subs = r1.SubResources()
    assert [r.Address() for r in subs] == ["alpha", "bravo", "charlie"]

    pc1 = BasePriceComponent("charlie", r1, "unit", "month")
    pc2 = BasePriceComponent("alpha", r1, "unit", "month")
    pc3 = BasePriceComponent("bravo", r1, "unit", "month")

    r1.AddPriceComponent(pc1)
    r1.AddPriceComponent(pc2)
    r1.AddPriceComponent(pc3)

    pcs = r1.PriceComponents()
    assert [pc.Name() for pc in pcs] == ["alpha", "bravo", "charlie"]
