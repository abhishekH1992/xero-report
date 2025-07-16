from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_auth import XeroAuthService
from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.util.xero_connection import create_xero_api_client

router = APIRouter(prefix="/bank-transactions", tags=["Xero Bank Transactions"])

def get_xero_auth_service(db: Session = Depends(get_db)) -> XeroAuthService:
    repo = XeroAuthRepository(db)
    return XeroAuthService(repo)

@router.get("")
async def get_bank_transactions(
    tenant_id: str = Query(..., description="Xero tenant/organization ID"),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    transaction_type: Optional[str] = Query("RECEIVE-OVERPAYMENT", description="Type of bank transaction to filter"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Fetch bank transactions for a given period, filtering by type RECEIVE-OVERPAYMENT.
    """
    connection = xero_service.get_connection(tenant_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    accounting_api = create_xero_api_client(connection, tenant_id, xero_service)

    # Build where clause for date filtering
    where_clauses = [f'Type == "{transaction_type}"']
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            where_clauses.append(f"Date >= DateTime({start_dt.year},{start_dt.month},{start_dt.day})")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            where_clauses.append(f"Date <= DateTime({end_dt.year},{end_dt.month},{end_dt.day})")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")
    where_clause = " && ".join(where_clauses)

    try:
        bank_transactions_response = accounting_api.get_bank_transactions(
            tenant_id,
            empty,  # if_modified_since
            where_clause,
            empty,  # order
            empty,  # ids
            empty,  # bank_account_ids
            empty,  # statuses
        )
        bank_transactions = bank_transactions_response.bank_transactions or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch bank transactions: {str(e)}")

    # Prepare response
    result = []
    for bt in bank_transactions:
        result.append({
            "BankTransactionID": getattr(bt, "bank_transaction_id", None),
            "Type": getattr(bt, "type", None),
            "Status": getattr(bt, "status", None),
            "Date": getattr(bt, "date", None),
            "Amount": float(getattr(bt, "amount", 0)),
            "Contact": {
                "ContactID": getattr(bt.contact, "contact_id", None) if bt.contact else None,
                "Name": getattr(bt.contact, "name", None) if bt.contact else None,
            },
            "LineItems": [
                {
                    "Description": getattr(li, "description", None),
                    "Amount": float(getattr(li, "amount", 0)),
                    "AccountCode": getattr(li, "account_code", None),
                }
                for li in getattr(bt, "line_items", [])
            ]
        })

    return {"bank_transactions": result} 