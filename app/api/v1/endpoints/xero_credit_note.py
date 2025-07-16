from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_auth import XeroAuthService
from app.util.xero_connection import create_xero_api_client

router = APIRouter(prefix="/credit-notes", tags=["Xero Credit Notes"])

get_xero_auth_service = XeroAuthService.get_service_dependency()

@router.get("")
async def get_credit_notes(
    tenant_id: str = Query(..., description="Xero tenant/organization ID"),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Fetch credit notes for a given period, including RemainingCredit, Allocations, and Contact info.
    """
    connection = xero_service.get_connection(tenant_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    accounting_api = create_xero_api_client(connection, tenant_id, xero_service)

    # Build where clause for date filtering
    where_clauses = ["Type == \"ACCRECCREDIT\""]
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
        credit_notes_response = accounting_api.get_credit_notes(
            tenant_id,
            empty,  # if_modified_since
            where_clause,
            empty,  # order
            empty,  # ids
            empty,  # contact_ids
            empty,  # statuses
        )
        credit_notes = credit_notes_response.credit_notes or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch credit notes: {str(e)}")

    # Prepare response
    result = []
    for cn in credit_notes:
        result.append({
            "CreditNoteID": getattr(cn, "credit_note_id", None),
            "CreditNoteNumber": getattr(cn, "credit_note_number", None),
            "Type": getattr(cn, "type", None),
            "Status": getattr(cn, "status", None),
            "Date": getattr(cn, "date", None),
            "Total": float(getattr(cn, "total", 0)),
            "RemainingCredit": float(getattr(cn, "remaining_credit", 0)),
            "Contact": {
                "ContactID": getattr(cn.contact, "contact_id", None) if cn.contact else None,
                "Name": getattr(cn.contact, "name", None) if cn.contact else None,
            },
            "Allocations": [
                {
                    "AllocationID": getattr(a, "allocation_id", None),
                    "Amount": float(getattr(a, "amount", 0)),
                    "Date": getattr(a, "date", None),
                    "InvoiceID": getattr(a.invoice, "invoice_id", None) if getattr(a, "invoice", None) else None,
                    "InvoiceNumber": getattr(a.invoice, "invoice_number", None) if getattr(a, "invoice", None) else None,
                }
                for a in getattr(cn, "allocations", [])
            ]
        })

    return {"credit_notes": result} 