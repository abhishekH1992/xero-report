from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
import os

from app.database.database import get_db
from app.services.xero_aged_receivables_service import XeroAgedReceivablesService
from app.services.xero_auth import XeroAuthService
from app.services.xero_cashflow_service import XeroCashFlowService
from app.services.db_queue_service import DatabaseQueueService
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
    is_cache: bool = Query(True, description="Use cache (true) or not (false)"),
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
            format=format,
            is_cache=is_cache
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
            "connection_id": connection_id,
            "is_cache": is_cache
        }
        
        job_id = queue_service.enqueue_job("aged_receivables_report", job_data)
        
        return {
            "format": "table",
            "data": [
                {
                    "status": "queued",
                    "job_id": job_id,
                }
            ],
            "columns": ["status", "job_id"],
            "shape": [1, 2],
        }

@router.get("/cashflow")
async def get_cashflow_report(
    report_date: str = Query(None, description="Report date in YYYY-MM-DD format"),
    period: int = Query(2, description="Number of periods to go back"),
    period_of: str = Query("Week", description="Type of period (Week, Month, Year)"),
    cashflow_service: XeroCashFlowService = Depends(get_cashflow_service),
    connection_ids: str = Query(None, description="Connection ID(s) - comma-separated for multiple connections"),
    is_local: bool = Query(False, description="Generate report immediately (true) or queue (false)"),
    is_cache: bool = Query(True, description="Use cache (true) or not (false)"),
    db: Session = Depends(get_db)
):
    """
    Generate cashflow report with option to queue for background processing
    """
    
    if is_local:
        # Generate report immediately using the service
        # Make sure to await the async method
        result = await cashflow_service.generate_cashflow_report(
            report_date=report_date,
            period=period,
            period_of=period_of,
            connection_ids=connection_ids,
            is_cache=is_cache
        )
        return result
    else:
        # Queue the job for background processing using database
        queue_service = DatabaseQueueService(db)
        
        job_data = {
            "report_date": report_date,
            "period": period,
            "period_of": period_of,
            "connection_ids": connection_ids,
            "is_cache": is_cache
        }
        
        job_id = queue_service.enqueue_job("cashflow_report", job_data)
        
        return {
            "format": "table",
            "data": [
                {
                    "status": "queued",
                    "job_id": job_id,
                }
            ],
            "columns": ["status", "job_id"],
            "shape": [1, 2],
        }

@router.get("/excel/{filename}")
async def serve_excel_file(filename: str, download: bool = Query(False, description="Force download instead of inline display")):
    """
    Serve Excel files from the storage/reports directory.
    """
    # Use absolute path to ensure we find the files in the Docker container
    file_path = os.path.join("/app/storage/reports", filename)

    print(f"[SERVE_EXCEL_FILE] File path: {file_path}")
    print(f"[SERVE_EXCEL_FILE] File exists: {os.path.exists(file_path)}")
    print(f"[SERVE_EXCEL_FILE] Current working directory: {os.getcwd()}")
    print(f"[SERVE_EXCEL_FILE] Directory contents: {os.listdir('/app/storage/reports') if os.path.exists('/app/storage/reports') else 'Directory not found'}")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    
    # Set headers for download if requested
    headers = {}
    if download:
        headers["Content-Disposition"] = f"attachment; filename={filename}"
    
    return FileResponse(
        path=file_path, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers
    )

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
        "format": "table",
        "data": [
            {
                "job_id": job_id,
                "status": job_status.get("status", "unknown"),
                "created_at": job_status.get("created_at"),
                "started_at": job_status.get("started_at"),
                "completed_at": job_status.get("completed_at"),
                "failed_at": job_status.get("failed_at"),
                "error": job_status.get("error"),
                "result": job_status.get("result")
            }
        ],
        "columns": ["job_id", "status", "created_at", "started_at", "completed_at", "failed_at", "error", "result"],
        "shape": [1, 8],
        "generated_at": datetime.utcnow().isoformat()
    } 