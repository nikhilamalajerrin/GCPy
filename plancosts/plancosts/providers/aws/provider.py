"""
AWS provider-specific configurations and mappings.
"""
from typing import List, Dict
from plancosts.base.filters import Filter


# AWS region to location name mapping
REGION_MAPPING: Dict[str, str] = {
    "us-gov-west-1": "AWS GovCloud (US)",
    "us-gov-east-1": "AWS GovCloud (US-East)",
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "ca-central-1": "Canada (Central)",
    "cn-north-1": "China (Beijing)",
    "cn-northwest-1": "China (Ningxia)",
    "eu-central-1": "EU (Frankfurt)",
    "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)",
    "eu-west-3": "EU (Paris)",
    "eu-north-1": "EU (Stockholm)",
    "ap-east-1": "Asia Pacific (Hong Kong)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka-Local)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "me-south-1": "Middle East (Bahrain)",
    "sa-east-1": "South America (Sao Paulo)",
    "af-south-1": "Africa (Cape Town)",
}


def get_default_filters(region: str) -> List[Filter]:
    """
    Get default filters for AWS pricing queries based on region.
    
    Args:
        region: AWS region code (e.g., 'us-east-1')
    
    Returns:
        List of filters for the pricing query
    """
    location = REGION_MAPPING.get(region, "")
    
    return [
        Filter(key="locationType", value="AWS Region"),
        Filter(key="location", value=location),
    ]