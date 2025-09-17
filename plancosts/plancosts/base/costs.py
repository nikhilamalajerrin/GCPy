"""
Cost calculation and breakdown logic.
"""
from typing import List, Optional
from decimal import Decimal
from .resource import Resource
from .pricecomponent import PriceComponent
from .query import build_query, get_query_results, extract_price_from_result


HOURS_IN_MONTH = 730  # Standard cloud billing month


class PriceComponentCost:
    """Cost breakdown for a single price component."""
    
    def __init__(self, 
                 price_component: PriceComponent,
                 hourly_cost: Decimal,
                 monthly_cost: Decimal):
        self.price_component = price_component
        self.hourly_cost = hourly_cost
        self.monthly_cost = monthly_cost


class ResourceCostBreakdown:
    """Complete cost breakdown for a resource."""
    
    def __init__(self,
                 resource: Resource,
                 price_component_costs: List[PriceComponentCost]):
        self.resource = resource
        self.price_component_costs = price_component_costs


def get_cost_breakdown(resource: Resource) -> ResourceCostBreakdown:
    """
    Calculate cost breakdown for a single resource.
    
    Args:
        resource: The resource to calculate costs for
    
    Returns:
        ResourceCostBreakdown with all component costs
    
    Raises:
        Exception: If pricing API calls fail
    """
    # Build queries for non-skipped price components
    queries = []
    queried_components = []
    
    for component in resource.price_components():
        if not component.should_skip():
            queries.append(build_query(component.get_filters()))
            queried_components.append(component)
    
    # Get pricing data from API
    if queries:
        query_results = get_query_results(queries)
    else:
        query_results = []
    
    # Calculate costs for each component
    price_component_costs = []
    
    for i, result in enumerate(query_results):
        component = queried_components[i]
        
        # Extract price from result
        price_str = extract_price_from_result(result)
        if price_str:
            price = Decimal(price_str)
        else:
            price = Decimal('0')
        
        # Calculate hourly cost
        hourly_cost = component.calculate_hourly_cost(price)
        
        # Calculate monthly cost
        monthly_cost = hourly_cost * Decimal(HOURS_IN_MONTH)
        
        price_component_costs.append(
            PriceComponentCost(component, hourly_cost, monthly_cost)
        )
    
    return ResourceCostBreakdown(resource, price_component_costs)


def get_cost_breakdowns(resources: List[Resource]) -> List[ResourceCostBreakdown]:
    """
    Calculate cost breakdowns for multiple resources.
    
    Args:
        resources: List of resources to calculate costs for
    
    Returns:
        List of ResourceCostBreakdown objects
    
    Raises:
        Exception: If any pricing API call fails
    """
    cost_breakdowns = []
    for resource in resources:
        cost_breakdowns.append(get_cost_breakdown(resource))
    return cost_breakdowns