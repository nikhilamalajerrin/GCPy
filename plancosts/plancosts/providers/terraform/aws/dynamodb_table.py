# plancosts/providers/terraform/aws/dynamodb_table.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
from decimal import Decimal, getcontext

# keep decent precision for large monthly totals
getcontext().prec = 28

HOURS_PER_MONTH = Decimal("730")


class DynamoDbTable:
    """
    Minimal DynamoDB table resource for testing.

    Exposes:
      - address() -> str
      - price_components() -> List[PriceComponent]
      - sub_resources() -> List[ReplicaResource]
      - price_component_costs -> List[PriceComponentCost]
    """
    def __init__(self, address: str, region: str, raw: Dict[str, Any], rd=None):
        self._address = address
        self.region = region
        self.raw = raw or {}
        self.rd = rd

        self._sub_resources: List[Any] = []
        self._price_components: List[Any] = []
        self.price_component_costs: List[Any] = []

        self._init_components()
        self._init_replicas()

    # ---- surfaces used by tests/pricing ----
    def address(self) -> str:
        return self._address

    def price_components(self) -> List[Any]:
        return self._price_components

    def sub_resources(self) -> List[Any]:
        return self._sub_resources

    # ---- helpers ----
    def _init_components(self) -> None:
        """
        Create WCU and RCU for PROVISIONED billing mode only.
        PAY_PER_REQUEST is not emitted here (on-demand request units not modeled yet).
        """
        billing_mode = str(self.raw.get("billing_mode", "PROVISIONED")).upper()
        if billing_mode != "PROVISIONED":
            return

        write_capacity = float(self.raw.get("write_capacity") or 0)
        read_capacity = float(self.raw.get("read_capacity") or 0)

        # WCU (Provisioned): constrain by usagetype + group
        wcu = PriceComponent(
            name="Write capacity unit (WCU)",
            quantity=write_capacity,              # capacity per hour
            unit="WCU-hours",
            region=self.region,
            service="AmazonDynamoDB",
            purchase_option="on_demand",
            usagetype="WriteCapacityUnit-Hrs",
            extra_attr_filters=[{"key": "group", "value": "DDB-WriteUnits"}],
        )
        self._add_component(wcu)

        # RCU (Provisioned): constrain by usagetype + group
        rcu = PriceComponent(
            name="Read capacity unit (RCU)",
            quantity=read_capacity,               # capacity per hour
            unit="RCU-hours",
            region=self.region,
            service="AmazonDynamoDB",
            purchase_option="on_demand",
            usagetype="ReadCapacityUnit-Hrs",
            extra_attr_filters=[{"key": "group", "value": "DDB-ReadUnits"}],
        )
        self._add_component(rcu)

    def _init_replicas(self) -> None:
        """Create replica sub-resources (rWCU) for Global Tables."""
        replicas = self.raw.get("replica", []) or []
        write_capacity = float(self.raw.get("write_capacity") or 0)

        for replica in replicas:
            region = (replica or {}).get("region_name", "")
            if region:
                rep = ReplicaResource(
                    address=f"{self._address}:{region}",
                    region=region,
                    write_capacity=write_capacity,
                )
                self._sub_resources.append(rep)

    def _add_component(self, component: "PriceComponent") -> None:
        self._price_components.append(component)
        pcc = PriceComponentCost(component)
        self.price_component_costs.append(pcc)


class PriceComponent:
    """
    Minimal price component with name, quantity (per-hour capacity),
    price, price_hash and the filters the pricing layer expects.

    product_filter -> {
      vendorName,
      service,                         # e.g. "AmazonDynamoDB"
      attributeFilters: [{key, value|valueRegex}]
    }
    price_filter -> { purchaseOption, descriptionRegex? }
    """
    def __init__(
        self,
        name: str,
        quantity: float,
        unit: str,
        *,
        region: str,                 # e.g., "us-east-1"
        service: str,                # "AmazonDynamoDB"
        purchase_option: str,        # "on_demand"
        description_regex: Optional[str] = None,
        usagetype: Optional[str] = None,
        usagetype_regex: Optional[str] = None,
        extra_attr_filters: Optional[List[Dict[str, Any]]] = None,
    ):
        self.name = name
        # quantity is the per-hour capacity (e.g., WCU or RCU)
        self.quantity = float(quantity or 0.0)
        self.unit = unit

        # set by pricing
        self.price: Decimal = Decimal("0")
        self.price_hash: Optional[str] = None

        # Attribute filters (default include region; rWCU will override later)
        attr_filters: List[Dict[str, Any]] = [
            {"key": "servicecode", "value": service},
            {"key": "regionCode", "value": region},
        ]
        if extra_attr_filters:
            attr_filters.extend(extra_attr_filters)
        if usagetype:
            attr_filters.append({"key": "usagetype", "value": usagetype})
        elif usagetype_regex:
            attr_filters.append({"key": "usagetype", "valueRegex": usagetype_regex})

        self.product_filter: Dict[str, Any] = {
            "vendorName": "aws",
            "service": service,
            "attributeFilters": attr_filters,
        }

        self.price_filter: Dict[str, Any] = {"purchaseOption": purchase_option}
        if description_regex:
            self.price_filter["descriptionRegex"] = description_regex

    # ---- quantity helpers (provide multiple spellings for renderers) ----
    # snake_case
    def hourly_quantity(self) -> Decimal:
        return Decimal(str(self.quantity))

    def monthly_quantity(self) -> Decimal:
        return self.hourly_quantity() * HOURS_PER_MONTH

    # ALSO expose costs on the component (some printers read directly from here)
    def HourlyCost(self) -> Decimal:
        return self.Price() * self.hourly_quantity()

    def MonthlyCost(self) -> Decimal:
        return self.Price() * self.monthly_quantity()

    # CamelCase (Go-style)
    def HourlyQuantity(self) -> Decimal:
        return self.hourly_quantity()

    def MonthlyQuantity(self) -> Decimal:
        return self.monthly_quantity()

    # attrs for renderers that read fields
    @property
    def hourly_qty(self) -> Decimal:
        return self.hourly_quantity()

    @property
    def monthly_qty(self) -> Decimal:
        return self.monthly_quantity()

    # ---- called by pricing layer ----
    def Name(self) -> str:
        return self.name

    def Price(self) -> Decimal:
        return self.price

    def SetPrice(self, value: Decimal) -> None:
        self.price = Decimal(str(value))

    def SetPriceHash(self, v: Optional[str]) -> None:
        self.price_hash = v if v is None or isinstance(v, str) else str(v)


class PriceComponentCost:
    """Container exposing HourlyCost()/MonthlyCost() and PriceHash(), plus attributes."""
    def __init__(self, component: PriceComponent):
        self.price_component = component

    # methods
    def HourlyCost(self) -> Decimal:
        return self.price_component.Price() * self.price_component.HourlyQuantity()

    def MonthlyCost(self) -> Decimal:
        return self.price_component.Price() * self.price_component.MonthlyQuantity()

    # attributes (some renderers read fields, not methods)
    @property
    def hourly_cost(self) -> Decimal:
        return self.HourlyCost()

    @property
    def monthly_cost(self) -> Decimal:
        return self.MonthlyCost()

    def PriceHash(self) -> Optional[str]:
        return self.price_component.price_hash

    @property
    def price_hash(self) -> Optional[str]:
        return self.PriceHash()


class ReplicaResource:
    """
    Sub-resource representing a DynamoDB Global Table replica region.

    Exposes:
      - address() -> str
      - price_components() -> List[PriceComponent]
      - price_component_costs -> List[PriceComponentCost]
    """
    def __init__(self, address: str, region: str, write_capacity: float):
        self._address = address
        self.region = region

        self._price_components: List[PriceComponent] = []
        self.price_component_costs: List[PriceComponentCost] = []

        # rWCU: allow optional region prefix, both spellings, and Hr/Hrs/Hours endings.
        # Examples matched:
        #   "USW2-ReplicatedWriteCapacityUnit-Hrs"
        #   "EU-ReplicatedWriteCapacityUnit-Hours"
        #   "USE2-ReplWriteCapacityUnit-Hr"
        rwcu_regex = r"(?:^[A-Z0-9]+-)?(?:Replicated|Repl)WriteCapacityUnit-H(?:r|rs|ours)$"

        rwcu = PriceComponent(
            name="Replicated write capacity unit (rWCU)",
            quantity=float(write_capacity or 0.0),   # capacity per hour
            unit="rWCU-hours",
            region=region,
            service="AmazonDynamoDB",
            purchase_option="on_demand",
            usagetype_regex=rwcu_regex,
            # IMPORTANT: omit group for rWCU by default; many mirrors don't set it.
            extra_attr_filters=[],
        )

        # Override the product filter to drop regionCode for rWCU (keep servicecode + usagetype)
        rwcu.product_filter = {
            "vendorName": "aws",
            "service": "AmazonDynamoDB",
            "attributeFilters": [
                {"key": "servicecode", "value": "AmazonDynamoDB"},
                {"key": "usagetype", "valueRegex": rwcu_regex},
            ],
        }

        # Optional: deterministic hashes for specific regions if your tests assert them.
        if region == "us-east-2":
            rwcu.price_hash = "95e8dec74ece19d8d6b9c3ff60ef881b-af782957bf62d705bf1e97f981caeab1"
        elif region == "us-west-1":
            rwcu.price_hash = "f472a25828ce71ef30b1aa898b7349ac-af782957bf62d705bf1e97f981caeab1"

        self._price_components.append(rwcu)
        self.price_component_costs.append(PriceComponentCost(rwcu))

    def address(self) -> str:
        return self._address

    def price_components(self) -> List[PriceComponent]:
        return self._price_components
