"""
Mappings between Terraform resources and pricing components.
"""
from typing import Dict, List, Optional, Callable, Any
from decimal import Decimal
from .filters import Filter, merge_filters


class ValueMapping:
    """Maps values from Terraform to pricing API format."""
    
    def __init__(self, 
                 from_key: str, 
                 to_key: str, 
                 to_value_fn: Optional[Callable[[Any], str]] = None):
        self.from_key = from_key
        self.to_key = to_key
        self.to_value_fn = to_value_fn
    
    def mapped_value(self, from_val: Any) -> str:
        """Convert a value using the mapping function or default string conversion."""
        if self.to_value_fn:
            return self.to_value_fn(from_val)
        return str(from_val) if from_val is not None else ""


class PriceMapping:
    """Maps resource attributes to pricing queries."""
    
    def __init__(self,
                 time_unit: str = "hour",
                 default_filters: Optional[List[Filter]] = None,
                 value_mappings: Optional[List[ValueMapping]] = None,
                 should_skip: Optional[Callable[[Dict[str, Any]], bool]] = None,
                 calculate_cost: Optional[Callable[[Decimal], Decimal]] = None):
        self.time_unit = time_unit
        self.default_filters = default_filters or []
        self.value_mappings = value_mappings or []
        self.should_skip = should_skip
        self.calculate_cost = calculate_cost
    
    def get_filters(self, values: Dict[str, Any]) -> List[Filter]:
        """Get all filters for this price mapping."""
        return merge_filters(self.default_filters, self._value_filters(values))
    
    def _value_filters(self, values: Dict[str, Any]) -> List[Filter]:
        """Convert resource values to filters based on value mappings."""
        mapped_filters = []
        
        for value_mapping in self.value_mappings:
            from_key = value_mapping.from_key
            
            if from_key in values:
                from_val = values[from_key]
                to_val = value_mapping.mapped_value(from_val)
                
                if to_val:
                    mapped_filters.append(Filter(
                        key=value_mapping.to_key,
                        value=to_val
                    ))
        
        return mapped_filters


class ResourceMapping:
    """Maps Terraform resources to their price components."""
    
    def __init__(self,
                 price_mappings: Optional[Dict[str, PriceMapping]] = None,
                 sub_resource_mappings: Optional[Dict[str, 'ResourceMapping']] = None):
        self.price_mappings = price_mappings or {}
        self.sub_resource_mappings = sub_resource_mappings or {}