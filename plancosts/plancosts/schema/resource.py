from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Dict, Any, Optional, Callable

from .cost_component import CostComponent, HOURS_IN_MONTH
from .resource_data import ResourceData  # for alias below

# ResourceFunc func(*ResourceData, *ResourceData) *Resource
ResourceFunc = Callable[[ResourceData], "Resource"]


@dataclass
class Resource:
    """
    Python mirror of pkg/schema/resource with skip-support (feat #122).
    """
    name: str
    address: Optional[str] = None

    sub_resources: List["Resource"] = field(default_factory=list)
    cost_components: List[CostComponent] = field(default_factory=list)

    # cost aggregation fields
    _hourly_cost: Decimal = field(default=Decimal(0), init=False, repr=False)
    _monthly_cost: Decimal = field(default=Decimal(0), init=False, repr=False)

    # new fields from feat #122
    is_skipped: bool = False
    skip_message: Optional[str] = None
    resource_type: Optional[str] = None

    # ---- composition helpers ----
    def add_subresource(self, r: "Resource") -> None:
        self.sub_resources.append(r)

    def add_cost_component(self, c: CostComponent) -> None:
        self.cost_components.append(c)

    # ---- cost rollup ----
    def CalculateCosts(self) -> None:
        """
        Calculate and roll up hourly/monthly costs.
        """
        hourly = Decimal(0)

        # skip if flagged
        if self.is_skipped:
            self._hourly_cost = Decimal(0)
            self._monthly_cost = Decimal(0)
            return

        for cc in self.cost_components:
            calc = getattr(cc, "CalculateCosts", None)
            if callable(calc):
                try:
                    calc()
                except Exception:
                    pass
            hourly += cc.HourlyCost()

        for sr in self.sub_resources:
            sr.CalculateCosts()
            hourly += sr.HourlyCost()

        self._hourly_cost = hourly
        self._monthly_cost = hourly * HOURS_IN_MONTH

    # ---- accessors ----
    def HourlyCost(self) -> Decimal:
        return self._hourly_cost

    def MonthlyCost(self) -> Decimal:
        return self._monthly_cost

    def IsSkipped(self) -> bool:
        return self.is_skipped

    def SkipMessage(self) -> Optional[str]:
        return self.skip_message

    def ResourceType(self) -> str:
        return self.resource_type or ""

    # ---- helpers ----
    def FlattenedSubResources(self) -> List["Resource"]:
        subs: List[Resource] = []
        for s in self.sub_resources:
            subs.append(s)
            if s.sub_resources:
                subs.extend(s.FlattenedSubResources())
        return subs

    def Address(self) -> str:
        return self.address if self.address else self.name

    # ---- export ----
    def to_dict(self) -> Dict[str, Any]:
        return {
            "Name": self.name,
            "Address": self.address,
            "SubResources": [s.to_dict() for s in self.sub_resources],
            "CostComponents": [cc.to_dict() for cc in self.cost_components],
            "HourlyCost": str(self._hourly_cost),
            "MonthlyCost": str(self._monthly_cost),
            "IsSkipped": self.is_skipped,
            "SkipMessage": self.skip_message,
            "ResourceType": self.resource_type,
        }


# ---------------- module-level helpers  ----------------

def CalculateCosts(resources: List[Resource]) -> None:
    for r in resources:
        r.CalculateCosts()


def SortResources(resources: List[Resource]) -> None:
    """
    Sorts resources, their subresources, and their cost components.
    """
    def _rname(r: Resource) -> str:
        return (r.Address() or r.name or "").lower()

    def _ccname(c: CostComponent) -> str:
        try:
            return (c.name or "").lower()
        except Exception:
            return ""

    resources.sort(key=_rname)
    for r in resources:
        r.cost_components.sort(key=_ccname)
        r.sub_resources.sort(key=_rname)
        if r.sub_resources:
            SortResources(r.sub_resources)
