"""
Price component abstraction for cost calculations.
"""
from typing import List, Optional
from decimal import Decimal
from abc import ABC, abstractmethod
from .filters import Filter, merge_filters
from .mappings import PriceMapping


class PriceComponent(ABC):
    """Abstract base class for price components."""
    
    @abstractmethod
    def name(self) -> str:
        """Get the name of this price component."""
        pass
    
    @abstractmethod
    def should_skip(self) -> bool:
        """Check if this component should be skipped."""
        pass
    
    @abstractmethod
    def get_filters(self) -> List[Filter]:
        """Get filters for pricing query."""
        pass
    
    @abstractmethod
    def calculate_hourly_cost(self, price: Decimal) -> Decimal:
        """Calculate hourly cost from the price."""
        pass


class BasePriceComponent(PriceComponent):
    """Base implementation of a price component."""
    
    def __init__(self, name: str, resource, price_mapping: PriceMapping):
        """
        Initialize a price component.
        Note: resource is not typed here to avoid circular import.
        """
        self._name = name
        self._resource = resource
        self._price_mapping = price_mapping
    
    def name(self) -> str:
        return self._name
    
    def should_skip(self) -> bool:
        """Check if this component should be skipped based on resource values."""
        if self._price_mapping.should_skip:
            return self._price_mapping.should_skip(self._resource.raw_values())
        return False
    
    def get_filters(self) -> List[Filter]:
        """Merge resource and price mapping filters."""
        return merge_filters(
            self._resource.get_filters(),
            self._price_mapping.get_filters(self._resource.raw_values())
        )
    
    def calculate_hourly_cost(self, price: Decimal) -> Decimal:
        """Calculate hourly cost, converting from the price's time unit if needed."""
        # Apply custom calculation if provided
        if self._price_mapping.calculate_cost:
            cost = self._price_mapping.calculate_cost(price)
        else:
            cost = price
        
        # Convert to hourly rate based on time unit
        time_unit_seconds = {
            "hour": 60 * 60,
            "month": 60 * 60 * 730  # 730 hours per month
        }
        
        time_unit_multiplier = Decimal(
            time_unit_seconds["hour"] / time_unit_seconds[self._price_mapping.time_unit]
        )
        
        hourly_cost = cost * time_unit_multiplier
        return hourly_cost