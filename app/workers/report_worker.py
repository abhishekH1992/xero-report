import asyncio
import json
import os
import time
from datetime import datetime
from typing import Dict, Any

from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.services.queue_service import FileBasedQueueService
from app.services.db_queue_service import DatabaseQueueService
from app.services.xero_aged_receivables_service import XeroAgedReceivablesService
from app.services.webhook_service import WebhookService
from app.services.xero_auth import XeroAuthService

class ReportWorker:
    """Background worker for processing report generation jobs"""
    
    def __init__(self):
        # Initialize database and repository with explicit database URL
        # Use the same database configuration as the API
        from app.database.database import SessionLocal, SQLALCHEMY_DATABASE_URL
        
        print("[WORKER] Initializing worker...")
        print(f"[WORKER] DATABASE_URL: {os.getenv('DATABASE_URL', 'NOT SET')}")
        print(f"[WORKER] SQLALCHEMY_DATABASE_URL: {SQLALCHEMY_DATABASE_URL}")
        
        db = SessionLocal()
        print("[WORKER] Database session created")
        
        repo = XeroAuthRepository(db)
        self.xero_auth_service = XeroAuthService(repo)
        
        # Use database queue service instead of file-based
        self.queue_service = DatabaseQueueService(db)
        print("[WORKER] Queue service initialized")
        
        self.aged_receivables_service = XeroAgedReceivablesService(self.xero_auth_service)
        self.webhook_service = WebhookService()
        print("[WORKER] Worker initialization complete")
    
    async def process_job(self, job: Dict[str, Any]):
        """Process a single job"""
        job_id = job["id"]
        job_type = job["type"]
        job_data = job["data"]
        
        print(f"[WORKER] Processing job {job_id} of type {job_type}")
        
        try:
            if job_type == "aged_receivables_report":
                await self.process_aged_receivables_report(job_id, job_data)
            else:
                raise ValueError(f"Unknown job type: {job_type}")
                
        except Exception as e:
            print(f"[WORKER] Error processing job {job_id}: {e}")
            import traceback
            print(f"[WORKER] Full traceback: {traceback.format_exc()}")
            self.queue_service.mark_job_failed(job_id, str(e))
            
            # Remove failed job from queue to prevent infinite retries
            self.queue_service.remove_job(job_id)
            
            # Send failure webhook
            await self.webhook_service.send_report_failure_webhook(
                job_id, job_type, str(e)
            )
    
    async def process_aged_receivables_report(self, job_id: str, job_data: Dict[str, Any]):
        """Process aged receivables report generation"""
        try:
            # Extract parameters from job data
            report_date = job_data.get("report_date")
            periods = job_data.get("periods", 4)
            period_of = job_data.get("period_of", 1)
            period_type = job_data.get("period_type", "Month")
            app_id = job_data.get("app_id")
            show_current = job_data.get("show_current", True)
            connection_id = job_data.get("connection_id")
            
            print(f"[WORKER] Generating aged receivables report for {report_date}")
            
            # Generate the report
            result = await self.aged_receivables_service.generate_aged_receivables_report(
                report_date=report_date,
                periods=periods,
                period_of=period_of,
                period_type=period_type,
                app_id=app_id,
                show_current=show_current,
                connection_id=connection_id,
                is_response_only=0,  # Generate Excel file
                format=1  # Table format
            )
            
            # Get the Excel file path
            excel_file_path = result.get("excel_file")
            
            if excel_file_path and os.path.exists(excel_file_path):
                print(f"[WORKER] Report generated successfully: {excel_file_path}")
                
                # Send completion webhook
                await self.webhook_service.send_report_completion_webhook(
                    job_id, "aged_receivables", excel_file_path, report_date
                )
                
                # Mark job as complete
                self.queue_service.mark_job_complete(job_id, {
                    "excel_file_path": excel_file_path,
                    "file_size": os.path.getsize(excel_file_path),
                    "report_summary": result.get("summary", {})
                })
            else:
                raise Exception("Excel file was not generated")
                
        except Exception as e:
            print(f"[WORKER] Error generating report: {e}")
            import traceback
            print(f"[WORKER] Full traceback: {traceback.format_exc()}")
            raise
    
    async def run(self):
        """Main worker loop"""
        print("[WORKER] Starting report worker...")
        
        while True:
            try:
                # Get next job from queue
                print("[WORKER] Checking for jobs...")
                job = self.queue_service.dequeue_job()
                
                if job:
                    print(f"[WORKER] Found job: {job['id']}")
                    await self.process_job(job)
                else:
                    print("[WORKER] No jobs available, waiting...")
                    # No jobs available, wait a bit
                    await asyncio.sleep(5)
                    
            except KeyboardInterrupt:
                print("[WORKER] Shutting down...")
                break
            except Exception as e:
                print(f"[WORKER] Error in main loop: {e}")
                import traceback
                print(f"[WORKER] Full traceback: {traceback.format_exc()}")
                await asyncio.sleep(10)

async def main():
    """Main entry point for the worker"""
    worker = ReportWorker()
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main()) 