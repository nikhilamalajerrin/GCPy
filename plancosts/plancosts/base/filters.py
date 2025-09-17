"""
Filters for querying pricing information.
"""
from typing import List, Dict, Optional


class Filter:
    """Represents a filter for querying pricing data."""
    
    def __init__(self, key: str, value: str, operation: Optional[str] = None):
        self.key = key
        self.value = value
        self.operation = operation
    
    def to_dict(self) -> Dict[str, str]:
        """Convert filter to dictionary for JSON serialization."""
        result = {
            "key": self.key,
            "value": self.value
        }
        if self.operation:
            result["operation"] = self.operation
        return result
    
    def __repr__(self):
        return f"Filter(key={self.key}, value={self.value}, operation={self.operation})"
    
    def __eq__(self, other):
        if not isinstance(other, Filter):
            return False
        return (self.key == other.key and 
                self.value == other.value and 
                self.operation == other.operation)
    
    def __hash__(self):
        return hash((self.key, self.value, self.operation))


def merge_filters(*filtersets: List[Filter]) -> List[Filter]:
    """
    Merge multiple filter sets, keeping only unique filters by key.
    Later filters override earlier ones with the same key.
    """
    filter_dict = {}
    
    for filterset in filtersets:
        if filterset:  # Check if filterset is not None
            for filter in filterset:
                filter_dict[filter.key] = filter
    
    return list(filter_dict.values())