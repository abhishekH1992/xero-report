from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from xero_python.accounting import AccountingApi
from xero_python.accounting.api.accounting_api import empty
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token

from app.services.xero_auth import XeroAuthService
from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.config import settings
from app.util.xero_token import register_xero_token_handlers

router = APIRouter(prefix="/reports", tags=["Xero Reports"])

def get_xero_auth_service(db: Session = Depends(get_db)) -> XeroAuthService:
    repo = XeroAuthRepository(db)
    return XeroAuthService(repo)

def xero_bucket(report_date, due_date) -> str:
    days = (report_date - due_date).days
    if days < 0:
        return "Current"
    if days <= 30:
        return "< 1 Month"
    if days <= 60:
        return "1 Month"
    if days <= 90:
        return "2 Months"
    if days <= 120:
        return "3 Months"
    return "Older"

@router.get("/aged-receivables")
async def get_aged_receivables(
    tenant_id: str = Query(..., description="Xero tenant/organization ID"),
    report_date: str = Query(None, description="Report date in YYYY-MM-DD format"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Custom Aged Receivables report: fetch all unpaid invoices, group by contact and Xero-style aging bucket.
    """
    # Get connection from DB
    connection = xero_service.get_connection(tenant_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Parse report_date or use today
    if report_date:
        try:
            parsed_date = datetime.strptime(report_date, "%Y-%m-%d").date()
            report_date_obj = parsed_date
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid report_date format. Use YYYY-MM-DD.")
    else:
        report_date_obj = datetime.utcnow().date()

    # Build Xero SDK client
    api_client = ApiClient(
        Configuration(
            debug=False,
            oauth2_token=OAuth2Token(
                client_id=settings.xero_client_id,
                client_secret=settings.xero_client_secret
            ),
        ),
        pool_threads=1,
    )

    # Prepare token dictionary for the SDK
    token_dict = {
        "access_token": connection.access_token,
        "refresh_token": connection.refresh_token,
        "scope": connection.scope.split(),
        "expires_at": connection.expires_at.timestamp(),
        "expires_in": int((connection.expires_at - datetime.utcnow()).total_seconds()),
        "token_type": "Bearer"
    }

    # Register handlers for automatic refresh first, then set the token
    register_xero_token_handlers(api_client, token_dict, tenant_id, xero_service)
    api_client.set_oauth2_token(token_dict)

    # Create Accounting API instance
    accounting_api = AccountingApi(api_client)

    try:
        # Fetch all unpaid invoices using SDK (automatic token refresh happens here)
        date_for_xero = f"{report_date_obj.year},{report_date_obj.month},{report_date_obj.day}"
        where_clause = f"AmountDue>0 && DueDate <= DateTime({date_for_xero})"
        
        invoices_response = accounting_api.get_invoices(  # type: ignore
            tenant_id,  # xero_tenant_id
            empty,      # if_modified_since
            where_clause,  # where
            empty,      # order
            empty,      # ids
            empty,      # invoice_numbers
            empty,      # contact_ids
            ["AUTHORISED"],  # statuses
        )
        
        invoices = invoices_response.invoices or []  # type: ignore
        
    except Exception as e:
        print(f"[XERO REPORT] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch invoices: {str(e)}")

    # Build custom aged receivables report with Xero-style buckets
    bucket_names = ["Current", "< 1 Month", "1 Month", "2 Months", "3 Months", "Older"]
    report = {}
    
    for inv in invoices:
        contact_name = inv.contact.name if inv.contact else "Unknown"
        due_date = inv.due_date if inv.due_date else None
        
        if not due_date:
            continue
            
        bucket = xero_bucket(report_date_obj, due_date)
        amount_due = float(inv.amount_due) if inv.amount_due else 0
        
        if contact_name not in report:
            report[contact_name] = {name: 0 for name in bucket_names}
        report[contact_name][bucket] += amount_due

    return {
        "aged_receivables": report, 
        "generated_at": report_date_obj.isoformat(),
        "total_invoices": len(invoices)
    }
