"""
JSON output formatter for cost breakdowns.
"""
import json
from typing import List, Dict, Any
from decimal import Decimal
from plancosts.base.costs import ResourceCostBreakdown


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal types."""
    
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert to string to preserve precision
            return str(obj)
        return super().default(obj)


def to_json(resource_cost_breakdowns: List[ResourceCostBreakdown]) -> str:
    """
    Convert resource cost breakdowns to JSON format.
    
    Args:
        resource_cost_breakdowns: List of cost breakdowns
    
    Returns:
        JSON string representation of the cost breakdowns
    """
    json_output = []
    
    for breakdown in resource_cost_breakdowns:
        # Build breakdown array for this resource
        price_component_costs = []
        
        for component_cost in breakdown.price_component_costs:
            price_component_costs.append({
                "priceComponent": component_cost.price_component.name(),
                "hourlyCost": component_cost.hourly_cost,
                "monthlyCost": component_cost.monthly_cost
            })
        
        # Add resource breakdown to output
        json_output.append({
            "resource": breakdown.resource.address(),
            "breakdown": price_component_costs
        })
    
    return json.dumps(json_output, indent=2, cls=DecimalEncoder)