from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
import httpx
from datetime import datetime

from app.services.xero_auth import XeroAuthService
from app.database.database import get_db
from app.database.repository import XeroAuthRepository

router = APIRouter(prefix="/reports", tags=["Xero Reports"])

def get_xero_auth_service(db: Session = Depends(get_db)) -> XeroAuthService:
    repo = XeroAuthRepository(db)
    return XeroAuthService(repo)

def month_diff(d1, d2):
    return (d1.year - d2.year) * 12 + d1.month - d2.month

def xero_month_bucket(report_date, due_date):
    print(report_date, due_date)

    # If due date is after report date, it's Current
    if due_date > report_date:
        return "Current"
    # Calculate how many months ago the due date was, relative to the report date
    months_diff = (report_date.year - due_date.year) * 12 + (report_date.month - due_date.month)
    if months_diff == 0:
        return "< 1 Month"
    elif months_diff == 1:
        return "1 Month"
    elif months_diff == 2:
        return "2 Months"
    elif months_diff == 3:
        return "3 Months"
    else:
        return "Older"

@router.get("/aged-receivables")
async def get_aged_receivables(
    tenant_id: str = Query(..., description="Xero tenant/organization ID"),
    xero_service: XeroAuthService = Depends(get_xero_auth_service)
):
    """
    Custom Aged Receivables report: fetch all unpaid invoices, group by contact and Xero-style aging bucket.
    """
    # Get connection from DB
    connection = xero_service.get_connection(tenant_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Refresh token if needed
    expires_at = connection.expires_at
    if not isinstance(expires_at, datetime):
        raise HTTPException(status_code=500, detail="Invalid expires_at type in connection")
    if expires_at <= datetime.utcnow():
        token_response = await xero_service.refresh_access_token(str(connection.refresh_token), tenant_id=tenant_id)
        xero_service.update_connection_tokens(tenant_id, token_response)
        access_token = token_response.access_token
    else:
        access_token = str(connection.access_token)

    # Fetch all unpaid invoices
    url = "https://api.xero.com/api.xro/2.0/Invoices"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "xero-tenant-id": tenant_id,
        "Accept": "application/json"
    }
    params = {
        "status": "AUTHORISED",
        "where": "AmountDue>0"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            invoices = response.json().get("Invoices", [])
    except httpx.HTTPStatusError as e:
        print(f"[XERO REPORT] Error status: {e.response.status_code}")
        print(f"[XERO REPORT] Error response: {e.response.text}")
        detail = e.response.json() if e.response.content else str(e)
        raise HTTPException(status_code=e.response.status_code, detail=detail)

    # Build custom aged receivables report with Xero-style buckets
    today = datetime.utcnow().date()
    bucket_names = ["Current", "< 1 Month", "1 Month", "2 Months", "3 Months", "Older"]
    report = {}
    for inv in invoices:
        contact = inv["Contact"]["Name"]
        due_date_str = inv.get("DueDateString") or inv.get("DueDate")
        if not due_date_str:
            continue
        try:
            due_date = datetime.strptime(due_date_str[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        bucket = xero_month_bucket(today, due_date)
        amount_due = inv.get("AmountDue", 0)
        if contact not in report:
            report[contact] = {name: 0 for name in bucket_names}
        report[contact][bucket] += amount_due

    return {"aged_receivables": report, "generated_at": today.isoformat()}
