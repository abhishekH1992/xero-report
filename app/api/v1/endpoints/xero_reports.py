from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_auth import XeroAuthService
from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.util.xero_connection import create_xero_api_client
from app.util.report_export import export_report_to_excel

router = APIRouter(prefix="/reports", tags=["Xero Reports"])

def get_xero_auth_service(db: Session = Depends(get_db)) -> XeroAuthService:
    repo = XeroAuthRepository(db)
    return XeroAuthService(repo)

def calculate_aging_bucket(report_date, due_date, periods: int, period_of: int, period_type: str) -> str:
    """
    Calculate aging bucket based on configurable periods.
    
    Args:
        report_date: The report date
        due_date: The invoice due date
        periods: Number of aging periods
        period_of: Duration of each period
        period_type: Type of period (Day, Week, Month)
    """
    days = (report_date - due_date).days
    
    if days < 0:
        return "Current"
    
    # Calculate days per period based on type
    if period_type.lower() == "day":
        days_per_period = period_of
    elif period_type.lower() == "week":
        days_per_period = period_of * 7
    elif period_type.lower() == "month":
        days_per_period = period_of * 30  # Approximate
    else:
        days_per_period = period_of * 30  # Default to month
    
    # Calculate which period this falls into
    for i in range(1, periods + 1):
        if days <= i * days_per_period:
            if i == 1:
                return f"< 1 {period_type}"
            else:
                return f"{i-1} {period_type}{'s' if i-1 > 1 else ''}"
    
    return "Older"

@router.get("/aged-receivables")
async def get_aged_receivables(
    tenant_id: str = Query(..., description="Xero tenant/organization ID"),
    report_date: str = Query(None, description="Report date in YYYY-MM-DD format"),
    periods: int = Query(4, description="Number of aging periods"),
    period_of: int = Query(1, description="Duration of each period"),
    period_type: str = Query("Month", description="Type of period (Day, Week, Month)"),
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

    # Create Xero API client with automatic token refresh
    accounting_api = create_xero_api_client(connection, tenant_id, xero_service)

    try:
        # Fetch all unpaid invoices using SDK (automatic token refresh happens here)
        date_for_xero = f"{report_date_obj.year},{report_date_obj.month},{report_date_obj.day}"
        where_clause = f'AmountDue>0 && DueDate <= DateTime({date_for_xero}) && Type == "ACCREC"'
        
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

    # Generate bucket names based on configurable periods
    bucket_names = ["Current"]
    for i in range(1, periods + 1):
        if i == 1:
            bucket_names.append(f"< 1 {period_type}")
        else:
            bucket_names.append(f"{i-1} {period_type}{'s' if i-1 > 1 else ''}")
    bucket_names.append("Older")
    
    report = {}
    
    for inv in invoices:
        contact_name = inv.contact.name if inv.contact else "Unknown"
        due_date = inv.due_date if inv.due_date else None
        
        if not due_date:
            continue
            
        bucket = calculate_aging_bucket(report_date_obj, due_date, periods, period_of, period_type)
        amount_due = float(inv.amount_due) if inv.amount_due else 0
        
        if contact_name not in report:
            report[contact_name] = {name: 0 for name in bucket_names}
        report[contact_name][bucket] += amount_due

    # Prepare data for Excel export
    excel_data = []
    for contact_name, buckets in report.items():
        row = {"Contact": contact_name}
        total_amount = 0
        for bucket_name in bucket_names:
            amount = buckets.get(bucket_name, 0)
            row[bucket_name] = amount
            total_amount += amount
        row["Total"] = total_amount
        excel_data.append(row)
    
    # Define columns for Excel export
    columns = [
        {"header": "Contact", "key": "Contact", "width": 30, "format": "text"},
        *[{"header": bucket, "key": bucket, "width": 15, "format": "currency"} for bucket in bucket_names],
        {"header": "Total", "key": "Total", "width": 15, "format": "currency"}
    ]
    
    # Export to Excel
    excel_file_path = export_report_to_excel(
        data=excel_data,
        columns=columns,
        filename="aged_receivables_report",
        sheet_name="Aged Receivables",
        title="Aged Receivables Summary",
        organization_name=connection.tenant_name,  # This should come from Xero tenant info
        report_date=f"As at {report_date_obj.strftime('%d %B %Y')}",
        output_dir="tmp",
        include_totals=True,
        include_percentages=True
    )
    
    return {
        "aged_receivables": report, 
        "generated_at": report_date_obj.isoformat(),
        "total_invoices": len(invoices),
        "aging_config": {
            "periods": periods,
            "period_of": period_of,
            "period_type": period_type,
            "bucket_names": bucket_names
        },
        "excel_file": excel_file_path
    }
