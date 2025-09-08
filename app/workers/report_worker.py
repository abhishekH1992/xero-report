import asyncio
import json
import os
import time
from datetime import datetime
from typing import Dict, Any

from app.database.database import get_db
from app.database.repository import XeroAuthRepository
from app.services.db_queue_service import DatabaseQueueService
from app.services.xero_aged_receivables_service import XeroAgedReceivablesService
from app.services.xero_cashflow_service import XeroCashFlowService
from app.services.webhook_service import WebhookService
from app.services.xero_auth import XeroAuthService
from app.util.db_session_manager import DatabaseSessionManager

class ReportWorker:
    """Background worker for processing report generation jobs"""
    
    def __init__(self):
        print("[WORKER] Initializing worker...")
        print(f"[WORKER] DATABASE_URL: {os.getenv('DATABASE_URL', 'NOT SET')}")
        
        # Initialize session manager for proper database session handling
        self.session_manager = DatabaseSessionManager()
        print("[WORKER] Database session manager initialized")
        
        # Initialize services that don't need persistent database sessions
        self.webhook_service = WebhookService()
        print("[WORKER] Webhook service initialized")
        
        print("[WORKER] Worker initialization complete")
    
    def _get_fresh_services(self):
        """Get fresh database session and services for each job"""
        session = self.session_manager.get_fresh_session()
        try:
            repo = XeroAuthRepository(session)
            xero_auth_service = XeroAuthService(repo)
            queue_service = DatabaseQueueService(session)
            aged_receivables_service = XeroAgedReceivablesService(xero_auth_service)
            cashflow_service = XeroCashFlowService(xero_auth_service)
            
            return session, queue_service, aged_receivables_service, cashflow_service
        except Exception as e:
            # If we can't create services, close the session and re-raise
            self.session_manager.close_session(session)
            raise e
    
    async def process_job(self, job: Dict[str, Any]):
        """Process a single job with fresh database session"""
        job_id = job["id"]
        job_type = job["type"]
        job_data = job["data"]
        
        print(f"[WORKER] Processing job {job_id} of type {job_type}")
        
        # Get fresh services for this job
        session, queue_service, aged_receivables_service, cashflow_service = self._get_fresh_services()
        
        try:
            if job_type == "aged_receivables_report":
                await self.process_aged_receivables_report(
                    job_id, job_data, session, queue_service, aged_receivables_service
                )
            elif job_type == "cashflow_report":
                await self.process_cashflow_report(
                    job_id, job_data, session, queue_service, cashflow_service
                )
            else:
                raise ValueError(f"Unknown job type: {job_type}")
                
        except Exception as e:
            print(f"[WORKER] Error processing job {job_id}: {e}")
            import traceback
            print(f"[WORKER] Full traceback: {traceback.format_exc()}")
            
            try:
                # Mark job as failed
                queue_service.mark_job_failed(job_id, str(e))
                # Remove failed job from queue to prevent infinite retries
                queue_service.remove_job(job_id)
                # Send failure webhook
                await self.webhook_service.send_report_failure_webhook(
                    job_id, job_type, str(e)
                )
            except Exception as webhook_error:
                print(f"[WORKER] Error handling job failure: {webhook_error}")
            finally:
                # Always clean up the session
                self.session_manager.rollback_and_close(session)
        else:
            # Job completed successfully, commit and close session
            try:
                session.commit()
            except Exception as commit_error:
                print(f"[WORKER] Error committing job {job_id}: {commit_error}")
                session.rollback()
            finally:
                self.session_manager.close_session(session)
    
    async def process_aged_receivables_report(self, job_id: str, job_data: Dict[str, Any], 
                                           session, queue_service, aged_receivables_service):
        """Process aged receivables report generation with fresh session"""
        try:
            # Extract parameters from job data
            report_date = job_data.get("report_date")
            periods = job_data.get("periods", 4)
            period_of = job_data.get("period_of", 1)
            period_type = job_data.get("period_type", "Month")
            app_id = job_data.get("app_id")
            show_current = job_data.get("show_current", True)
            connection_id = job_data.get("connection_id")
            email = job_data.get("email")
            
            print(f"[WORKER] Generating aged receivables report for {report_date}")
            
            # Generate the report
            result = await aged_receivables_service.generate_aged_receivables_report(
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
                    job_id, "aged_receivables", excel_file_path, report_date, email
                )
                
                # Mark job as complete
                queue_service.mark_job_complete(job_id, {
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

    async def process_cashflow_report(self, job_id: str, job_data: Dict[str, Any], 
                                   session, queue_service, cashflow_service):
        """Process cashflow report generation with fresh session"""
        try:
            # Extract parameters from job data
            report_date = job_data.get("report_date")
            period = job_data.get("period", 2)
            period_of = job_data.get("period_of", "Week")
            connection_ids = job_data.get("connection_ids")
            email = job_data.get("email")
            
            print(f"[WORKER] Generating cashflow report for {report_date}")
            
            # Generate the report
            result = await cashflow_service.generate_cashflow_report(
                report_date=report_date,
                period=period,
                period_of=period_of,
                connection_ids=connection_ids,
                email=email
            )
            
            # Get the Excel file path
            excel_file_path = result.get("excel_file")
            
            if excel_file_path and os.path.exists(excel_file_path):
                print(f"[WORKER] Cashflow report generated successfully: {excel_file_path}")
                
                # Send completion webhook
                await self.webhook_service.send_report_completion_webhook(
                    job_id, "cashflow", excel_file_path, report_date, email
                )
                
                # Mark job as complete
                queue_service.mark_job_complete(job_id, {
                    "excel_file_path": excel_file_path,
                    "file_size": os.path.getsize(excel_file_path),
                    "report_summary": result.get("summary", {})
                })
            else:
                raise Exception("Excel file was not generated")
                
        except Exception as e:
            print(f"[WORKER] Error generating cashflow report: {e}")
            import traceback
            print(f"[WORKER] Full traceback: {traceback.format_exc()}")
            raise
    
    async def run(self):
        """Main worker loop with proper error recovery"""
        print("[WORKER] Starting report worker...")
        
        while True:
            try:
                # Get fresh services for checking the queue
                session, queue_service, _, _ = self._get_fresh_services()
                
                try:
                    # Get next job from queue
                    print("[WORKER] Checking for jobs...")
                    job = queue_service.dequeue_job()
                    
                    if job:
                        print(f"[WORKER] Found job: {job['id']}")
                        # Close the queue session and process job with fresh session
                        self.session_manager.close_session(session)
                        await self.process_job(job)
                    else:
                        # print("[WORKER] No jobs available, waiting...")
                        # No jobs available, wait a bit
                        self.session_manager.close_session(session)
                        await asyncio.sleep(5)
                        
                except Exception as e:
                    print(f"[WORKER] Error checking queue: {e}")
                    self.session_manager.rollback_and_close(session)
                    await asyncio.sleep(10)
                    
            except KeyboardInterrupt:
                print("[WORKER] Shutting down...")
                break
            except Exception as e:
                print(f"[WORKER] Critical error in main loop: {e}")
                import traceback
                print(f"[WORKER] Full traceback: {traceback.format_exc()}")
                await asyncio.sleep(10)

async def main():
    """Main entry point for the worker"""
    worker = ReportWorker()
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main()) 