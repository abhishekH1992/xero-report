from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_aged_receivables_service import XeroAgedReceivablesService
from app.util.report_export import export_report_to_excel
from app.util.report_helper import calculate_aging_bucket, generate_bucket_names, process_financial_item

router = APIRouter(prefix="/reports", tags=["Xero Reports"])

get_aged_receivables_service = XeroAgedReceivablesService.get_service_dependency()

@router.get("/aged-receivables")
async def get_aged_receivables(
    tenant_id: str = Query(..., description="Xero tenant/organization ID"),
    report_date: str = Query(None, description="Report date in YYYY-MM-DD format"),
    periods: int = Query(4, description="Number of aging periods"),
    period_of: int = Query(1, description="Duration of each period"),
    period_type: str = Query("Month", description="Type of period (Day, Week, Month)"),
    aged_receivables_service: XeroAgedReceivablesService = Depends(get_aged_receivables_service)
):
    """
    Custom Aged Receivables report: fetch all unpaid invoices, group by contact and Xero-style aging bucket.
    """
    # Parse report_date or use today
    if report_date:
        try:
            parsed_date = datetime.strptime(report_date, "%Y-%m-%d").date()
            report_date_obj = parsed_date
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid report_date format. Use YYYY-MM-DD.")
    else:
        report_date_obj = datetime.utcnow().date()

    try:
        # Fetch all data using the service
        data = aged_receivables_service.get_aged_receivables_data(
            tenant_id=tenant_id,
            report_date=report_date_obj,
            periods=periods,
            period_of=period_of,
            period_type=period_type
        )
        
        invoices = data["invoices"]
        credit_notes = data["credit_notes"]
        bank_transactions = data["bank_transactions"]
        
    except Exception as e:
        print(f"[XERO REPORT] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch report data: {str(e)}")

    # Generate bucket names based on configurable periods
    bucket_names = generate_bucket_names(periods, period_type)
    
    report = {}
    
    # Process invoices
    for inv in invoices:
        if inv.due_date:  # Only process invoices with due dates
            process_financial_item(
                item=inv,
                report_date=report_date_obj,
                periods=periods,
                period_of=period_of,
                period_type=period_type,
                bucket_names=bucket_names,
                report=report,
                amount_field="amount_due",
                date_field="due_date",
                is_negative=False
            )

    # Process credit notes (apply as negative values)
    for cn in credit_notes:
        process_financial_item(
            item=cn,
            report_date=report_date_obj,
            periods=periods,
            period_of=period_of,
            period_type=period_type,
            bucket_names=bucket_names,
            report=report,
            amount_field="remaining_credit",
            date_field="date",
            is_negative=True,
            date_fallback=report_date_obj
        )

    # Process bank transactions (apply as negative values for overpayments)
    for bt in bank_transactions:
        process_financial_item(
            item=bt,
            report_date=report_date_obj,
            periods=periods,
            period_of=period_of,
            period_type=period_type,
            bucket_names=bucket_names,
            report=report,
            amount_field="total",
            date_field="date",
            is_negative=True,
            date_fallback=report_date_obj
        )

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
        row["Comments"] = ""  # Add blank comments column
        excel_data.append(row)
    
    # Define columns for Excel export
    columns = [
        {"header": "Contact", "key": "Contact", "width": 30, "format": "text"},
        *[{"header": bucket, "key": bucket, "width": 15, "format": "currency"} for bucket in bucket_names],
        {"header": "Total", "key": "Total", "width": 15, "format": "currency"},
        {"header": "Comments", "key": "Comments", "width": 25, "format": "text"}
    ]
    
    # Export to Excel
    excel_file_path = export_report_to_excel(
        data=excel_data,
        columns=columns,
        filename="aged_receivables_report",
        sheet_name="Aged Receivables",
        title="Aged Receivables Summary",
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
