"""
GraphQL query builder and executor for pricing API.
"""
import json
import requests
from typing import List, Dict, Any, Optional
from .filters import Filter


class GraphQLQuery:
    """Represents a GraphQL query with variables."""
    
    def __init__(self, query: str, variables: Dict[str, Any]):
        self.query = query
        self.variables = variables
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "query": self.query,
            "variables": self.variables
        }


def build_query(filters: List[Filter]) -> GraphQLQuery:
    """Build a GraphQL query for pricing data."""
    variables = {
        "filter": {
            "attributes": [f.to_dict() for f in filters]
        }
    }
    
    query = """
        query($filter: ProductFilter!) {
            products(
                filter: $filter,
            ) {
                onDemandPricing {
                    priceDimensions {
                        unit
                        pricePerUnit {
                            USD
                        }
                    }
                }
            }
        }
    """
    
    return GraphQLQuery(query.strip(), variables)


def get_query_results(queries: List[GraphQLQuery]) -> List[Dict[str, Any]]:
    """
    Execute GraphQL queries and return results.
    
    Args:
        queries: List of GraphQL queries to execute
    
    Returns:
        List of query results as dictionaries
    
    Raises:
        requests.RequestException: If API call fails
        ValueError: If response is not valid JSON
    """
    if not queries:
        return []
    
    # Convert queries to list of dictionaries
    queries_data = [q.to_dict() for q in queries]
    
    # Make API request
    try:
        response = requests.post(
            "http://localhost:4000",
            json=queries_data,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise requests.RequestException(f"API request failed: {e}")
    
    # Parse response
    try:
        results = response.json()
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response: {e}")
    
    # Ensure results is a list
    if not isinstance(results, list):
        results = [results]
    
    return results


def extract_price_from_result(result: Dict[str, Any]) -> Optional[str]:
    """
    Extract price string from query result using dictionary navigation.
    
    Returns:
        Price string or None if not found
    """
    try:
        products = result.get("data", {}).get("products", [])
        if products:
            pricing = products[0].get("onDemandPricing", [])
            if pricing:
                dimensions = pricing[0].get("priceDimensions", [])
                if dimensions:
                    price_per_unit = dimensions[0].get("pricePerUnit", {})
                    return price_per_unit.get("USD")
    except (KeyError, IndexError, TypeError):
        pass
    
    return None