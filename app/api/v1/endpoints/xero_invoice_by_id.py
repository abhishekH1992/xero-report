from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_auth import XeroAuthService
from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.util.xero_connection import create_xero_api_client

router = APIRouter(prefix="/invoice", tags=["Xero Invoice By ID"])

def get_xero_auth_service(db: Session = Depends(get_db)) -> XeroAuthService:
    repo = XeroAuthRepository(db)
    return XeroAuthService(repo)

@router.get("")
async def get_invoice_by_id(
    tenant_id: str = Query(..., description="Xero tenant/organization ID"),
    invoice_id: str = Query(..., description="Xero Invoice ID"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Fetch invoice details by InvoiceID.
    """
    connection = xero_service.get_connection(tenant_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    accounting_api = create_xero_api_client(connection, tenant_id, xero_service)

    try:
        invoice_response = accounting_api.get_invoices(
            tenant_id,
            empty,  # if_modified_since
            empty,  # where
            empty,  # order
            [invoice_id],  # ids
            empty,  # invoice_numbers
            empty,  # contact_ids
            empty,  # statuses
        )
        invoices = invoice_response.invoices or []
        if not invoices:
            raise HTTPException(status_code=404, detail="Invoice not found")
        invoice = invoices[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch invoice: {str(e)}")

    # Prepare response
    return {
        "InvoiceID": getattr(invoice, "invoice_id", None),
        "InvoiceNumber": getattr(invoice, "invoice_number", None),
        "Type": getattr(invoice, "type", None),
        "Status": getattr(invoice, "status", None),
        "Date": getattr(invoice, "date", None),
        "DueDate": getattr(invoice, "due_date", None),
        "Total": float(getattr(invoice, "total", 0)),
        "AmountDue": float(getattr(invoice, "amount_due", 0)),
        "AmountPaid": float(getattr(invoice, "amount_paid", 0)),
        "AmountCredited": float(getattr(invoice, "amount_credited", 0)),
        "Contact": {
            "ContactID": getattr(invoice.contact, "contact_id", None) if invoice.contact else None,
            "Name": getattr(invoice.contact, "name", None) if invoice.contact else None,
        },
        "LineItems": [
            {
                "Description": getattr(li, "description", None),
                "UnitAmount": float(getattr(li, "unit_amount", 0)),
                "Quantity": float(getattr(li, "quantity", 0)),
                "LineAmount": float(getattr(li, "line_amount", 0)),
            }
            for li in getattr(invoice, "line_items", [])
        ]
    } 