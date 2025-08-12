import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import ReportQueue


class DatabaseQueueService:
    """Database-based queue service for report generation jobs"""
    
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
    
    def enqueue_job(self, job_type: str, job_data: Dict[str, Any]) -> str:
        """Add a job to the queue"""
        try:
            job_id = f"{job_type}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Create new queue entry
            queue_entry = ReportQueue(
                job_id=job_id,
                job_type=job_type,
                status="pending",
                job_data=json.dumps(job_data),
                created_at=datetime.now()
            )
            
            self.db.add(queue_entry)
            self.db.commit()
            
            print(f"[DB_QUEUE] Job {job_id} added to queue")
            return job_id
        except Exception as e:
            print(f"[DB_QUEUE] Error enqueueing job: {e}")
            import traceback
            print(f"[DB_QUEUE] Full traceback: {traceback.format_exc()}")
            raise
    
    def dequeue_job(self) -> Optional[Dict[str, Any]]:
        """Get the next pending job from the queue"""
        print(f"[DB_QUEUE] Checking for pending jobs...")
        
        # Get the oldest pending job
        queue_entry = (
            self.db.query(ReportQueue)
            .filter(ReportQueue.status == "pending")
            .order_by(ReportQueue.created_at.asc())
            .first()
        )
        
        if not queue_entry:
            # print("[DB_QUEUE] No pending jobs found")
            return None
        
        print(f"[DB_QUEUE] Found pending job: {queue_entry.job_id}")
        
        # Mark as processing
        queue_entry.status = "processing"
        queue_entry.started_at = datetime.now()
        self.db.commit()
        
        # Convert to job format
        job = {
            "id": queue_entry.job_id,
            "type": queue_entry.job_type,
            "data": json.loads(queue_entry.job_data),
            "created_at": queue_entry.created_at.isoformat(),
            "status": queue_entry.status
        }
        
        print(f"[DB_QUEUE] Processing job {queue_entry.job_id}")
        return job
    
    def mark_job_complete(self, job_id: str, result: Dict[str, Any] = None):
        """Mark a job as completed"""
        queue_entry = self.db.query(ReportQueue).filter(ReportQueue.job_id == job_id).first()
        
        if queue_entry:
            queue_entry.status = "completed"
            queue_entry.completed_at = datetime.now()
            if result:
                queue_entry.result_data = json.dumps(result)
            
            self.db.commit()
            print(f"[DB_QUEUE] Job {job_id} completed")
    
    def mark_job_failed(self, job_id: str, error: str):
        """Mark a job as failed"""
        queue_entry = self.db.query(ReportQueue).filter(ReportQueue.job_id == job_id).first()
        
        if queue_entry:
            queue_entry.status = "failed"
            queue_entry.failed_at = datetime.now()
            queue_entry.error_message = error
            
            self.db.commit()
            print(f"[DB_QUEUE] Job {job_id} failed: {error}")
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific job"""
        queue_entry = self.db.query(ReportQueue).filter(ReportQueue.job_id == job_id).first()
        
        if queue_entry:
            return {
                "id": queue_entry.job_id,
                "type": queue_entry.job_type,
                "status": queue_entry.status,
                "data": json.loads(queue_entry.job_data) if queue_entry.job_data else None,
                "result": json.loads(queue_entry.result_data) if queue_entry.result_data else None,
                "error": queue_entry.error_message,
                "created_at": queue_entry.created_at.isoformat() if queue_entry.created_at else None,
                "started_at": queue_entry.started_at.isoformat() if queue_entry.started_at else None,
                "completed_at": queue_entry.completed_at.isoformat() if queue_entry.completed_at else None,
                "failed_at": queue_entry.failed_at.isoformat() if queue_entry.failed_at else None
            }
        return None
    
    def get_pending_jobs_count(self) -> int:
        """Get the number of pending jobs"""
        return self.db.query(ReportQueue).filter(ReportQueue.status == "pending").count()
    
    def get_jobs_by_status(self, status: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get jobs by status"""
        queue_entries = (
            self.db.query(ReportQueue)
            .filter(ReportQueue.status == status)
            .order_by(ReportQueue.created_at.desc())
            .limit(limit)
            .all()
        )
        
        return [
            {
                "id": entry.job_id,
                "type": entry.job_type,
                "status": entry.status,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "started_at": entry.started_at.isoformat() if entry.started_at else None,
                "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
                "failed_at": entry.failed_at.isoformat() if entry.failed_at else None
            }
            for entry in queue_entries
        ]
    
    def cleanup_old_jobs(self, days: int = 7):
        """Clean up old completed/failed jobs"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        old_jobs = (
            self.db.query(ReportQueue)
            .filter(
                ReportQueue.status.in_(["completed", "failed"]),
                ReportQueue.created_at < cutoff_date
            )
            .all()
        )
        
        for job in old_jobs:
            self.db.delete(job)
        
        self.db.commit()
        print(f"[DB_QUEUE] Cleaned up {len(old_jobs)} old jobs") 