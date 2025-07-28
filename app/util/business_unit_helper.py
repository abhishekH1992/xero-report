"""
Utility module for determining business units for companies based on JSON data.
"""

import json
import os
from pathlib import Path
from typing import Optional


def load_company_business_units() -> dict:
    """
    Load company business units data from JSON file.
    
    Returns:
        dict: Dictionary mapping company names to business units
    """
    # Get the path to the data directory relative to the app directory
    app_dir = Path(__file__).parent.parent.parent
    json_file = app_dir / "data" / "company_business_units.json"
    
    if not json_file.exists():
        print(f"⚠️  Warning: {json_file} not found")
        return {}
    
    try:
        with open(json_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON file: {e}")
        return {}
    except Exception as e:
        print(f"❌ Error reading JSON file: {e}")
        return {}


def get_business_unit_for_company(company_name: str) -> str:
    """
    Get the business unit for a given company name.
    
    Args:
        company_name: Name of the company
        
    Returns:
        str: Business unit for the company, or "Commercial Property" as default
    """
    company_data = load_company_business_units()
    
    # Trim whitespace from company name for comparison
    trimmed_company_name = company_name.strip()
    
    if trimmed_company_name in company_data:
        return company_data[trimmed_company_name]
    
    # Default business unit if company not found
    return "Commercial Property"


def get_business_unit_for_tenant(tenant_name: str) -> str:
    """
    Get the business unit for a given tenant name.
    This is an alias for get_business_unit_for_company for clarity.
    
    Args:
        tenant_name: Name of the Xero tenant/company
        
    Returns:
        str: Business unit for the tenant, or "Commercial Property" as default
    """
    return get_business_unit_for_company(tenant_name) 