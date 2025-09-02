from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
from xero_python.accounting import AccountingApi

from app.services.xero_auth import XeroAuthService
from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.database.models import XeroAccount, XeroCategory
from app.util.auth import api_key_auth
from app.util.xero_connection import create_xero_api_client
from app.services.redis_service import RedisService
from sqlalchemy.orm import Session

router = APIRouter()

class ItemResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None

@router.get("/invoice/{tenant_id}/{invoice_id}", 
           response_model=ItemResponse,
           tags=["Xero General"],
           summary="Get Invoice by ID",
           description="Retrieve a specific invoice from Xero using tenant ID and invoice ID",
           dependencies=[Depends(api_key_auth)])
async def get_invoice_by_id(
    tenant_id: str,
    invoice_id: str,
    db: Session = Depends(get_db)
):
    """
    Get invoice details by ID from Xero.
    
    Args:
        tenant_id: Xero tenant ID
        invoice_id: Xero invoice ID
        
    Returns:
        Invoice details or error message
    """
    try:
        # Initialize Redis service
        redis_service = RedisService()
        
        # Create cache key
        cache_key = f"invoice:{tenant_id}:{invoice_id}"
        
        # Try to get from cache first
        cached_data = redis_service.get_cache(cache_key)
        if cached_data:
            return ItemResponse(
                success=True,
                data=cached_data
            )
        
        # Get Xero connection for the tenant
        repo = XeroAuthRepository(db)
        xero_auth_service = XeroAuthService(repo)
        connection = xero_auth_service.get_connection(tenant_id)
        
        if not connection:
            raise HTTPException(status_code=404, detail=f"No active connection found for tenant {tenant_id}")
        
        # Create Xero API client using existing utility
        api_instance = create_xero_api_client(connection, tenant_id, xero_auth_service)
        
        # Get invoice
        api_response = api_instance.get_invoice(tenant_id, invoice_id)
        
        # Process and filter response data
        if api_response:
            # Convert to dict to handle the response structure
            raw_data = api_response.to_dict()
            
            # The response contains an 'invoices' array, get the first invoice
            invoices = raw_data.get('invoices', [])
            if not invoices:
                return ItemResponse(
                    success=True,
                    data=None
                )
            
            # Get the first invoice from the array
            invoice = invoices[0]

            # Get account information for each line item
            line_items_with_accounts = []
            for item in invoice.get('line_items', []):
                account_code = item.get('account_code')
                account_info = None
                
                if account_code:
                    # Get account information from database
                    account_info = await get_account_by_code(tenant_id, account_code, db)
                
                line_items_with_accounts.append({
                    "qty": item.get('quantity'),
                    "unit_amount": item.get('unit_amount'),
                    "line_amount": item.get('line_amount'),
                    "account_code": account_code,
                    "account_code_name": account_info.get('name') if account_info else None,
                    "account_code_type": account_info.get('type') if account_info else None
                })
            
            # Extract only the required fields from the invoice
            filtered_data = {
                "id": invoice.get('invoice_id'),
                "type": invoice.get('type'),
                "contact": {
                    "name": invoice.get('contact', {}).get('name'),
                    "first_name": invoice.get('contact', {}).get('first_name'),
                    "last_name": invoice.get('contact', {}).get('last_name'),
                    "contact_number": invoice.get('contact', {}).get('contact_number')
                },
                "line_items": line_items_with_accounts,
                "due_date": invoice.get('due_date'),
                "issue_date": invoice.get('date'),
                "status": invoice.get('status'),
                "invoice_number": invoice.get('invoice_number'),
                "payments": [
                    {
                        "payment_id": payment.get('payment_id'),
                        "amount": payment.get('amount')
                    }
                    for payment in invoice.get('payments', [])
                ],
                "amount_due": invoice.get('amount_due'),
                "amount_paid": invoice.get('amount_paid')
            }
            
            # Cache the filtered response for 1 hour (3600 seconds)
            redis_service.set_cache(cache_key, filtered_data, ttl=604800)
            
            return ItemResponse(
                success=True,
                data=filtered_data
            )
        
        return ItemResponse(
            success=True,
            data=None
        )
        
    except Exception as e:
        return ItemResponse(
            success=False,
            error=f"Error retrieving invoice: {str(e)}"
        )
    finally:
        # Ensure database session is closed
        db.close()

@router.get("/credit-note/{tenant_id}/{credit_note_id}", 
           response_model=ItemResponse,
           tags=["Xero General"],
           summary="Get Credit Note by ID",
           description="Retrieve a specific credit note from Xero using tenant ID and credit note ID",
           dependencies=[Depends(api_key_auth)])
async def get_credit_note_by_id(
    tenant_id: str,
    credit_note_id: str,
    db: Session = Depends(get_db)
):
    """
    Get credit note details by ID from Xero.
    
    Args:
        tenant_id: Xero tenant ID
        credit_note_id: Xero credit note ID
        
    Returns:
        Credit note details or error message
    """
    try:
        # Initialize Redis service
        redis_service = RedisService()
        
        # Create cache key
        cache_key = f"credit_note:{tenant_id}:{credit_note_id}"
        
        # Try to get from cache first
        cached_data = redis_service.get_cache(cache_key)
        if cached_data:
            return ItemResponse(
                success=True,
                data=cached_data
            )
        
        # Get Xero connection for the tenant
        repo = XeroAuthRepository(db)
        xero_auth_service = XeroAuthService(repo)
        connection = xero_auth_service.get_connection(tenant_id)
        
        if not connection:
            raise HTTPException(status_code=404, detail=f"No active connection found for tenant {tenant_id}")
        
        # Create Xero API client using existing utility
        api_instance = create_xero_api_client(connection, tenant_id, xero_auth_service)
        
        # Get credit note
        api_response = api_instance.get_credit_note(tenant_id, credit_note_id)
        
        # Process and filter response data
        if api_response:
            # Convert to dict to handle the response structure
            raw_data = api_response.to_dict()
            
            # The response contains a 'credit_notes' array, get the first credit note
            credit_notes = raw_data.get('credit_notes', [])
            if not credit_notes:
                return ItemResponse(
                    success=True,
                    data=None
                )
            
            # Get the first credit note from the array
            credit_note = credit_notes[0]
            
            # Get account information for each line item
            line_items_with_accounts = []
            for item in credit_note.get('line_items', []):
                account_code = item.get('account_code')
                account_info = None
                
                if account_code:
                    # Get account information from database
                    account_info = await get_account_by_code(tenant_id, account_code, db)
                
                line_items_with_accounts.append({
                    "qty": item.get('quantity'),
                    "unit_amount": item.get('unit_amount'),
                    "line_amount": item.get('line_amount'),
                    "account_code": account_code,
                    "account_code_name": account_info.get('name') if account_info else None,
                    "account_code_type": account_info.get('type') if account_info else None
                })
            
            # Extract only the required fields from the credit note
            filtered_data = {
                "id": credit_note.get('credit_note_id'),
                "type": credit_note.get('type'),
                "contact": {
                    "name": credit_note.get('contact', {}).get('name'),
                    "first_name": credit_note.get('contact', {}).get('first_name'),
                    "last_name": credit_note.get('contact', {}).get('last_name'),
                    "contact_number": credit_note.get('contact', {}).get('contact_number')
                },
                "line_items": line_items_with_accounts,
                "due_date": credit_note.get('due_date'),
                "issue_date": credit_note.get('date'),
                "status": credit_note.get('status'),
                "credit_note_number": credit_note.get('credit_note_number'),
                "payments": [
                    {
                        "payment_id": payment.get('payment_id'),
                        "amount": payment.get('amount')
                    }
                    for payment in credit_note.get('payments', [])
                ],
                "allocations": [
                    {
                        "invoice_id": allocation.get('invoice', {}).get('invoice_id'),
                        "invoice_number": allocation.get('invoice', {}).get('invoice_number'),
                        "amount": allocation.get('amount'),
                        "date": allocation.get('date')
                    }
                    for allocation in credit_note.get('allocations', [])
                ],
                "remaining_credit": credit_note.get('remaining_credit'),
                "total": credit_note.get('total')
            }
            
            # Cache the filtered response for 1 hour (3600 seconds)
            redis_service.set_cache(cache_key, filtered_data, ttl=604800)
            
            return ItemResponse(
                success=True,
                data=filtered_data
            )
        
        return ItemResponse(
            success=True,
            data=None
        )
        
    except Exception as e:
        return ItemResponse(
            success=False,
            error=f"Error retrieving credit note: {str(e)}"
        )
    finally:
        # Ensure database session is closed
        db.close()

@router.get("/overpayment/{tenant_id}/{overpayment_id}", 
           response_model=ItemResponse,
           tags=["Xero General"],
           summary="Get Overpayment by ID",
           description="Retrieve a specific overpayment from Xero using tenant ID and overpayment ID",
           dependencies=[Depends(api_key_auth)])
async def get_overpayment_by_id(
    tenant_id: str,
    overpayment_id: str,
    db: Session = Depends(get_db)
):
    """
    Get overpayment details by ID from Xero.
    
    Args:
        tenant_id: Xero tenant ID
        overpayment_id: Xero overpayment ID
        
    Returns:
        Overpayment details or error message
    """
    try:
        # Initialize Redis service
        redis_service = RedisService()
        
        # Create cache key
        cache_key = f"overpayment:{tenant_id}:{overpayment_id}"
        
        # Try to get from cache first
        cached_data = redis_service.get_cache(cache_key)
        if cached_data:
            return ItemResponse(
                success=True,
                data=cached_data
            )
        
        # Get Xero connection for the tenant
        repo = XeroAuthRepository(db)
        xero_auth_service = XeroAuthService(repo)
        connection = xero_auth_service.get_connection(tenant_id)
        
        if not connection:
            raise HTTPException(status_code=404, detail=f"No active connection found for tenant {tenant_id}")
        
        # Create Xero API client using existing utility
        api_instance = create_xero_api_client(connection, tenant_id, xero_auth_service)
        
        # Get overpayment
        api_response = api_instance.get_overpayment(tenant_id, overpayment_id)
        
        # Process and filter response data
        if api_response:
            # Convert to dict to handle the response structure
            raw_data = api_response.to_dict()
            
            # The response contains an 'overpayments' array, get the first overpayment
            overpayments = raw_data.get('overpayments', [])
            if not overpayments:
                return ItemResponse(
                    success=True,
                    data=None
                )
            
            # Get the first overpayment from the array
            overpayment = overpayments[0]
            
            # Get account information for each line item
            line_items_with_accounts = []
            for item in overpayment.get('line_items', []):
                account_code = item.get('account_code')
                account_info = None
                
                if account_code:
                    # Get account information from database
                    account_info = await get_account_by_code(tenant_id, account_code, db)
                
                line_items_with_accounts.append({
                    "qty": item.get('quantity'),
                    "unit_amount": item.get('unit_amount'),
                    "line_amount": item.get('line_amount'),
                    "account_code": account_code,
                    "account_code_name": account_info.get('name') if account_info else None,
                    "account_code_type": account_info.get('type') if account_info else None
                })
            
            # Extract only the required fields from the overpayment
            filtered_data = {
                "id": overpayment.get('overpayment_id'),
                "type": overpayment.get('type'),
                "contact": {
                    "name": overpayment.get('contact', {}).get('name'),
                    "first_name": overpayment.get('contact', {}).get('first_name'),
                    "last_name": overpayment.get('contact', {}).get('last_name'),
                    "contact_number": overpayment.get('contact', {}).get('contact_number')
                },
                "line_items": line_items_with_accounts,
                "issue_date": overpayment.get('date'),
                "status": overpayment.get('status'),
                "payments": [
                    {
                        "payment_id": payment.get('payment_id'),
                        "amount": payment.get('amount')
                    }
                    for payment in overpayment.get('payments', [])
                ],
                "allocations": [
                    {
                        "invoice_id": allocation.get('invoice', {}).get('invoice_id'),
                        "invoice_number": allocation.get('invoice', {}).get('invoice_number'),
                        "amount": allocation.get('amount'),
                        "date": allocation.get('date')
                    }
                    for allocation in overpayment.get('allocations', [])
                ],
                "remaining_credit": overpayment.get('remaining_credit'),
                "total": overpayment.get('total')
            }
            
            # Cache the filtered response for 1 hour (3600 seconds)
            redis_service.set_cache(cache_key, filtered_data, ttl=604800)
            
            return ItemResponse(
                success=True,
                data=filtered_data
            )
        
        return ItemResponse(
            success=True,
            data=None
        )
        
    except Exception as e:
        return ItemResponse(
            success=False,
            error=f"Error retrieving overpayment: {str(e)}"
        )
    finally:
        # Ensure database session is closed
        db.close()

async def get_account_by_code(
    tenant_id: str,
    account_code: str,
    db: Session
):
    """
    Get account details by account code from database.
    
    Args:
        tenant_id: Xero tenant ID
        account_code: Xero account code
        
    Returns:
        Account details or error message
    """
    try:
        # Initialize Redis service
        redis_service = RedisService()
        
        # Create cache key
        cache_key = f"account_code:{tenant_id}:{account_code}"
        
        # Try to get from cache first
        cached_data = redis_service.get_cache(cache_key)
        if cached_data:
            return cached_data
        
        # Get Xero connection for the tenant to get connection_id
        repo = XeroAuthRepository(db)
        xero_auth_service = XeroAuthService(repo)
        connection = xero_auth_service.get_connection(tenant_id)
        
        if not connection:
            raise HTTPException(status_code=404, detail=f"No active connection found for tenant {tenant_id}")
        
        # Query database for account information
        account_info = db.query(
            XeroAccount.account_code,
            XeroCategory.name,
            XeroCategory.type
        ).join(
            XeroCategory, XeroAccount.category_id == XeroCategory.id
        ).filter(
            XeroAccount.connection_id == connection.id,
            XeroAccount.account_code == account_code
        ).first()
        
        if account_info:
            # Extract account information
            filtered_data = {
                "account_code": account_info.account_code,
                "name": account_info.name,
                "type": account_info.type
            }
            
            # Cache the response for 1 hour (3600 seconds)
            redis_service.set_cache(cache_key, filtered_data, ttl=604800)
            
            return filtered_data
        
        return None
        
    except Exception as e:
        print(f"Error retrieving account: {str(e)}")
        return None
