# plancosts/plancosts/schema/resource.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Dict, Any, Optional, Callable

from .cost_component import CostComponent, HOURS_IN_MONTH
from .resource_data import ResourceData  # for the alias below

# Go's: type ResourceFunc func(*ResourceData, *ResourceData) *Resource
# In Python we usually pass just one RD; keep the alias for parity if needed.
ResourceFunc = Callable[[ResourceData], "Resource"]


@dataclass
class Resource:
    """
    Python mirror of pkg/schema/resource.go
    """
    name: str
    # In Go, Name is typically the Terraform address (e.g., "aws_instance.foo").
    # We keep an optional 'address' for convenience; Address() accessor returns
    # address if set, else falls back to name.
    address: Optional[str] = None

    sub_resources: List["Resource"] = field(default_factory=list)
    cost_components: List[CostComponent] = field(default_factory=list)

    # internal rollup fields
    _hourly_cost: Decimal = field(default=Decimal(0), init=False, repr=False)
    _monthly_cost: Decimal = field(default=Decimal(0), init=False, repr=False)

    # ---- mutations ----
    def add_subresource(self, r: "Resource") -> None:
        self.sub_resources.append(r)

    def add_cost_component(self, c: CostComponent) -> None:
        self.cost_components.append(c)

    # ---- Go-parity cost rollup ----
    def CalculateCosts(self) -> None:
        """
        Go version:
          - calls each costComponent.CalculateCosts()
          - sums HourlyCost across components and subresources
          - monthly = hourly * 730
        Our CostComponent computes costs on-demand, so we don't need an explicit
        component.CalculateCosts() call, but the rollup math is identical.
        """
        hourly = Decimal(0)

        # Top-level components
        for cc in self.cost_components:
            # If your CostComponent implements a CalculateCosts, calling it is safe:
            calc = getattr(cc, "CalculateCosts", None)
            if callable(calc):
                try:
                    calc()
                except Exception:
                    # Non-fatal; HourlyCost/MonthlyCost are derived anyway.
                    pass
            hourly += cc.HourlyCost()

        # Sub-resources (recursive)
        for sr in self.sub_resources:
            sr.CalculateCosts()
            hourly += sr.HourlyCost()

        self._hourly_cost = hourly
        self._monthly_cost = hourly * HOURS_IN_MONTH

    def HourlyCost(self) -> Decimal:
        return self._hourly_cost

    def MonthlyCost(self) -> Decimal:
        return self._monthly_cost

    # ---- helpers (Go's FlattenedSubResources) ----
    def FlattenedSubResources(self) -> List["Resource"]:
        subs: List[Resource] = []
        for s in self.sub_resources:
            subs.append(s)
            if s.sub_resources:
                subs.extend(s.FlattenedSubResources())
        return subs

    # ---- address accessor (avoid name clash with the 'address' field) ----
    def Address(self) -> str:
        return self.address if self.address else self.name

    # ---- debug/export ----
    def to_dict(self) -> Dict[str, Any]:
        return {
            "Name": self.name,
            "Address": self.address,
            "SubResources": [s.to_dict() for s in self.sub_resources],
            "CostComponents": [cc.to_dict() for cc in self.cost_components],
            "HourlyCost": str(self._hourly_cost),
            "MonthlyCost": str(self._monthly_cost),
        }


# ---------------- module-level helpers (parity with Go) ----------------

def CalculateCosts(resources: List[Resource]) -> None:
    """
    Go: func CalculateCosts(resources []*Resource)
    """
    for r in resources:
        r.CalculateCosts()


def SortResources(resources: List[Resource]) -> None:
    """
    Go: schema.SortResources(resources)
    Sorts in place:
      - resources by Name/Address (case-insensitive)
      - each resource's sub-resources likewise (recursively)
      - each resource's cost components by Name
    """
    def _rname(r: Resource) -> str:
        return (r.Address() or r.name or "").lower()

    def _ccname(c: CostComponent) -> str:
        # CostComponent.name is a public attribute in our schema
        try:
            return (c.name or "").lower()
        except Exception:
            return ""

    # sort resources in place
    resources.sort(key=_rname)

    # recurse + sort internals
    for r in resources:
        # sort cost components
        r.cost_components.sort(key=_ccname)
        # sort sub-resources then recurse
        r.sub_resources.sort(key=_rname)
        if r.sub_resources:
            SortResources(r.sub_resources)
