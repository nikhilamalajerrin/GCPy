"""
Resource abstraction for cloud resources.
"""
from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
from .filters import Filter
from .mappings import ResourceMapping, PriceMapping


class Resource(ABC):
    """Abstract base class for cloud resources."""
    
    @abstractmethod
    def address(self) -> str:
        """Get the resource address."""
        pass
    
    @abstractmethod
    def raw_values(self) -> Dict[str, Any]:
        """Get raw resource values from Terraform."""
        pass
    
    @abstractmethod
    def references(self) -> Dict[str, 'Resource']:
        """Get referenced resources."""
        pass
    
    @abstractmethod
    def get_filters(self) -> List[Filter]:
        """Get filters for pricing queries."""
        pass
    
    @abstractmethod
    def add_reference(self, address: str, reference: 'Resource'):
        """Add a reference to another resource."""
        pass
    
    @abstractmethod
    def price_components(self) -> List:  # Will be List[PriceComponent]
        """Get price components for this resource."""
        pass


class BaseResource(Resource):
    """Base implementation of a cloud resource."""
    
    def __init__(self, 
                 address: str,
                 raw_values: Dict[str, Any],
                 resource_mapping: ResourceMapping,
                 provider_filters: List[Filter]):
        self._address = address
        self._raw_values = raw_values
        self._resource_mapping = resource_mapping
        self._references = {}
        self._provider_filters = provider_filters
        self._price_components = []
        
        # Initialize price components from resource mapping
        self._initialize_price_components()
    
    def _initialize_price_components(self):
        """Initialize price components from the resource mapping."""
        # Import here to avoid circular dependency
        from .pricecomponent import BasePriceComponent
        
        for name, price_mapping in self._resource_mapping.price_mappings.items():
            component = BasePriceComponent(name, self, price_mapping)
            self._price_components.append(component)
    
    def address(self) -> str:
        return self._address
    
    def raw_values(self) -> Dict[str, Any]:
        return self._raw_values
    
    def references(self) -> Dict[str, Resource]:
        return self._references
    
    def get_filters(self) -> List[Filter]:
        return self._provider_filters
    
    def add_reference(self, address: str, reference: Resource):
        self._references[address] = reference
    
    def price_components(self) -> List:
        return self._price_components