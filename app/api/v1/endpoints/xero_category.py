# app/api/v1/endpoints/xero_categories.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import pandas as pd
import io
import re

from app.database.database import get_db
from app.database.models import XeroCategory, XeroAccount, XeroConnection
from app.util.auth import api_key_auth

router = APIRouter(
    prefix="/categories",
    tags=["Xero Category / Account"],
    dependencies=[Depends(api_key_auth)]
)

@router.post("/upload-categories-accounts")
async def upload_categories_accounts(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload CSV/Excel file to create/update categories and accounts.
    
    Expected CSV format:
    - Type: category/account
    - Name: Category name or account description
    - AccountType: Category type
    - BusinessType: Business classification
    """
    
    # Validate file type
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be CSV or Excel")
    
    try:
        # Read file content
        content = await file.read()
        
        # Parse based on file type
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        else:
            df = pd.read_excel(io.BytesIO(content))
        
        # Validate required columns
        required_columns = ['Type', 'Name']
        if not all(col in df.columns for col in required_columns):
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required columns. Expected: {required_columns}"
            )
        
        # Process the data
        result = process_categories_accounts(df, db)
        
        return {
            "message": "Categories and accounts processed successfully",
            "summary": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

def process_categories_accounts(df: pd.DataFrame, db: Session) -> dict:
    """Process the dataframe to create/update categories and accounts."""
    
    categories_created = 0
    categories_updated = 0
    accounts_created = 0
    accounts_updated = 0
    
    # Separate arrays for different types of failures
    failed_accounts = {
        "missing_companies": [],
        "no_account_code": [],
        "parsing_errors": []
    }
    
    current_category = None
    
    for index, row in df.iterrows():
        try:
            # Check if Type column has a valid value
            if pd.isna(row['Type']) or str(row['Type']).strip() == '':
                failed_accounts["parsing_errors"].append({
                    "row": index + 1,
                    "error": "Empty or missing 'Type' column value",
                    "account_description": row['Name'] if pd.isna(row['Name']) == False else "N/A"
                })
                continue
                
            row_type = str(row['Type']).strip().lower()
            
            if row_type == 'category':
                # Process category row
                if pd.isna(row['Name']) or str(row['Name']).strip() == '':
                    failed_accounts["parsing_errors"].append({
                        "row": index + 1,
                        "error": "Empty or missing 'Name' column value for category",
                        "account_description": "N/A"
                    })
                    continue
                    
                category_name = str(row['Name']).strip()
                category_type = str(row.get('AccountType', '')).strip() if 'AccountType' in row and pd.isna(row['AccountType']) == False else None
                business_type = str(row.get('BusinessType', '')).strip() if 'BusinessType' in row and pd.isna(row['BusinessType']) == False else None
                
                # Create or update category
                category = db.query(XeroCategory).filter(
                    XeroCategory.name == category_name
                ).first()
                
                if category:
                    # Update existing category
                    category.type = category_type
                    category.business_type = business_type
                    categories_updated += 1
                else:
                    # Create new category
                    category = XeroCategory(
                        name=category_name,
                        type=category_type,
                        business_type=business_type
                    )
                    db.add(category)
                    categories_created += 1
                
                db.flush()  # Get the ID
                current_category = category
                
            elif row_type == 'account':
                # Process account row
                if not current_category:
                    failed_accounts["parsing_errors"].append({
                        "row": index + 1,
                        "error": "No category defined for account",
                        "account_description": "N/A"
                    })
                    continue
                
                if pd.isna(row['Name']) or str(row['Name']).strip() == '':
                    failed_accounts["parsing_errors"].append({
                        "row": index + 1,
                        "error": "Empty or missing 'Name' column value for account",
                        "account_description": "N/A"
                    })
                    continue
                    
                account_description = str(row['Name']).strip()
                
                # Extract company name and account code
                company_name, account_code = extract_account_details(account_description)
                
                # Debug: Print what we're processing
                print(f"Row {index + 1}: Processing '{account_description}'")
                print(f"  -> Company: '{company_name}', Account Code: '{account_code}'")
                print(f"  -> Company (trimmed): '{company_name.strip()}'")
                
                if not company_name:
                    failed_accounts["parsing_errors"].append({
                        "row": index + 1,
                        "error": "Could not extract company name",
                        "account_description": account_description
                    })
                    continue
                
                # Check if account code exists
                if not account_code:
                    failed_accounts["no_account_code"].append({
                        "row": index + 1,
                        "company_name": company_name,
                        "account_description": account_description,
                        "category_name": current_category.name
                    })
                    continue
                
                # Find connection by company name (trim both sides for comparison)
                trimmed_company_name = company_name.strip()
                print(f"  -> Looking for company: '{trimmed_company_name}'")
                
                connection = db.query(XeroConnection).filter(
                    XeroConnection.tenant_name == trimmed_company_name
                ).first()
                
                # If not found, try a more flexible search with trimmed names
                if not connection:
                    print(f"  -> Direct match failed, trying flexible search...")
                    # Get all connections and compare trimmed names
                    all_connections = db.query(XeroConnection).all()
                    for conn in all_connections:
                        db_tenant_name = conn.tenant_name.strip()
                        if db_tenant_name == trimmed_company_name:
                            print(f"  -> Found match: '{db_tenant_name}' (ID: {conn.id})")
                            connection = conn
                            break
                        else:
                            print(f"  -> Checking: '{db_tenant_name}' vs '{trimmed_company_name}'")
                
                if not connection:
                    # Company not found - add to missing companies list
                    failed_accounts["missing_companies"].append({
                        "row": index + 1,
                        "company_name": company_name,
                        "account_description": account_description,
                        "account_code": account_code,
                        "category_name": current_category.name
                    })
                else:
                    # Company found - create or update account
                    # Check if account already exists
                    existing_account = db.query(XeroAccount).filter(
                        XeroAccount.connection_id == connection.id,
                        XeroAccount.category_id == current_category.id,
                        XeroAccount.account_code == account_code
                    ).first()
                    
                    if existing_account:
                        # Update existing account (if needed)
                        accounts_updated += 1
                    else:
                        # Create new account
                        account = XeroAccount(
                            connection_id=connection.id,
                            category_id=current_category.id,
                            account_code=account_code
                        )
                        db.add(account)
                        accounts_created += 1
            else:
                # Handle unknown row types (e.g., 'group', empty, or any other value)
                failed_accounts["parsing_errors"].append({
                    "row": index + 1,
                    "error": f"Unknown or unsupported row type: '{row_type}'",
                    "account_description": str(row['Name']) if not pd.isna(row['Name']) else "N/A"
                })
                continue
                
        except Exception as e:
            failed_accounts["parsing_errors"].append({
                "row": index + 1,
                "error": f"Unexpected error: {str(e)}",
                "account_description": row.get('Name', 'Unknown') if pd.isna(row.get('Name')) == False else "N/A"
            })
    
    # Commit all changes
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    return {
        "categories_created": categories_created,
        "categories_updated": categories_updated,
        "accounts_created": accounts_created,
        "accounts_updated": accounts_updated,
        "failed_accounts": failed_accounts,
        "total_rows_processed": len(df),
        "success_rate": f"{accounts_created + accounts_updated}/{len(df)}",
        "debug_info": {
            "total_companies_searched": len(set([acc["company_name"] for acc in failed_accounts["missing_companies"] + failed_accounts["no_account_code"]])),
            "companies_not_found": len(failed_accounts["missing_companies"]),
            "parsing_errors": len(failed_accounts["parsing_errors"])
        }
    }

def extract_account_details(account_description: str) -> tuple:
    """
    Extract company name and account code from account description.
    
    Expected format: "Company Name : ACCOUNT_CODE Category - Subcategory"
    Returns: (company_name, account_code)
    """
    
    # Split by colon to separate company from account details
    if ':' not in account_description:
        return None, None
    
    company_part, account_part = account_description.split(':', 1)
    company_name = company_part.strip()
    
    # Extract account code (first number after colon)
    account_code_match = re.search(r'(\d+)', account_part)
    if not account_code_match:
        return company_name, None  # Company found but no account code
    
    account_code = account_code_match.group(1)
    
    return company_name, account_code