from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
import os

from xero_python.accounting.api.accounting_api import empty

from app.database.database import get_db
from app.services.xero_aged_receivables_service import XeroAgedReceivablesService
from app.services.xero_auth import XeroAuthService
from app.services.xero_cashflow_service import XeroCashFlowService
from app.services.db_queue_service import DatabaseQueueService
from app.util.report_export import export_report_to_excel, generate_system_comments
from app.util.report_helper import calculate_aging_bucket, generate_bucket_names, process_financial_item
from app.util.export.report_cashflow_export import export_cashflow_to_excel, generate_cashflow_json_response
from app.util.auth import api_key_auth

router = APIRouter(
    prefix="/reports",
    tags=["Xero Reports"],
    dependencies=[Depends(api_key_auth)]
)

get_aged_receivables_service = XeroAgedReceivablesService.get_service_dependency()
get_xero_auth_service = XeroAuthService.get_service_dependency()
get_cashflow_service = XeroCashFlowService.get_service_dependency()

@router.get("/aged-receivables")
async def get_aged_receivables(
    report_date: str = Query(None, description="Report date in YYYY-MM-DD format"),
    periods: int = Query(4, description="Number of aging periods"),
    period_of: int = Query(1, description="Duration of each period"),
    period_type: str = Query("Month", description="Type of period (Day, Week, Month)"),
    app_id: Optional[int] = Query(None, ge=1, le=2, description="Filter by Xero app ID (1-2)"),
    show_current: bool = Query(True, description="Show Current bucket separately (if false, combines Current and < 1 Month)"),
    aged_receivables_service: XeroAgedReceivablesService = Depends(get_aged_receivables_service),
    xero_auth_service: XeroAuthService = Depends(get_xero_auth_service),
    connection_id: str = Query(None, description="Connection ID(s) - comma-separated for multiple connections"),
    is_response_only: int = Query(1, description="If 1, return response only without Excel generation"),
    format: int = Query(1, description="If 1, return table format; if 0, return JSON format"),
    is_local: bool = Query(False, description="Generate report immediately (true) or queue (false)"),
    db: Session = Depends(get_db)
):
    """
    Custom Aged Receivables report: fetch all unpaid invoices from all connections, 
    group by contact and Xero-style aging bucket, with business unit and company columns.
    Supports multi-app functionality with app_id filtering.
    """
    
    if is_local:
        # Generate report immediately using the service
        return await aged_receivables_service.generate_aged_receivables_report(
            report_date=report_date,
            periods=periods,
            period_of=period_of,
            period_type=period_type,
            app_id=app_id,
            show_current=show_current,
            connection_id=connection_id,
            is_response_only=is_response_only,
            format=format
        )
    else:
        # Queue the job for background processing using database
        queue_service = DatabaseQueueService(db)
        
        job_data = {
            "report_date": report_date,
            "periods": periods,
            "period_of": period_of,
            "period_type": period_type,
            "app_id": app_id,
            "show_current": show_current,
            "connection_id": connection_id
        }
        
        job_id = queue_service.enqueue_job("aged_receivables_report", job_data)
        
        return {
            "status": "queued",
            "job_id": job_id,
            "message": "Report generation started. You will be notified when ready.",
            "queue_info": {
                "job_type": "aged_receivables_report",
                "parameters": job_data
            }
        }

@router.get("/cashflow")
async def get_cashflow_report(
    report_date: str = Query(None, description="Report date in YYYY-MM-DD format"),
    period: int = Query(2, description="Number of periods to go back"),
    period_of: str = Query("Week", description="Type of period (Week, Month, Year)"),
    cashflow_service: XeroCashFlowService = Depends(get_cashflow_service),
    connection_ids: str = Query(None, description="Connection ID(s) - comma-separated for multiple connections")
):
    """
    CashFlow report: fetch bank statement data from all connections or a specific connection,
    filter for ASB and ANZ banks, and export to Excel with multiple sheets.
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
    
    report_date_str = report_date_obj.strftime("%Y-%m-%d")
    
    try:
        # Get cashflow data
        result = await cashflow_service.get_cashflow_data(
            report_date=report_date_str,
            period=period,
            period_of=period_of,
            connection_ids=connection_ids
        )
        
        # Extract data and errors from result
        cashflow_data = result.get("data", {})
        errors = result.get("errors", [])
        
        # Calculate date ranges for export
        from app.util.report_helper import calculate_date_ranges
        date_ranges = calculate_date_ranges(report_date_str, period, period_of)
        
        # Export to Excel
        excel_file_path = export_cashflow_to_excel(
            cashflow_data=cashflow_data,
            date_ranges=date_ranges,
            filename="cashflow_report",
            output_dir="tmp",
            report_date=report_date_str
        )

        # Generate JSON response
        json_response = generate_cashflow_json_response(
            cashflow_data=cashflow_data,
            date_ranges=date_ranges,
            excel_file_path=excel_file_path,
            errors=errors
        )
        
        return json_response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating CashFlow report: {str(e)}")

@router.get("/excel/{filename}")
async def serve_excel_file(filename: str):
    """
    Serve Excel files from the storage/reports directory.
    """
    file_path = os.path.join("storage/reports", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    
    return FileResponse(path=file_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.get("/job/{job_id}")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Get the status of a queued job.
    """
    queue_service = DatabaseQueueService(db)
    job_status = queue_service.get_job_status(job_id)
    
    if not job_status:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    
    return {
        "job_id": job_id,
        "status": job_status.get("status", "unknown"),
        "created_at": job_status.get("created_at"),
        "started_at": job_status.get("started_at"),
        "completed_at": job_status.get("completed_at"),
        "failed_at": job_status.get("failed_at"),
        "error": job_status.get("error"),
        "result": job_status.get("result")
    } 