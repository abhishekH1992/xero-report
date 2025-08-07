import json
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

class FileBasedQueueService:
    """Simple file-based queue for local development and production"""
    
    def __init__(self, queue_dir: str = "storage/queue"):
        self.queue_dir = Path(queue_dir)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
    
    def enqueue_job(self, job_type: str, job_data: Dict[str, Any]) -> str:
        """Add a job to the queue"""
        job_id = f"{job_type}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        job_file = self.queue_dir / f"{job_id}.json"
        
        job = {
            "id": job_id,
            "type": job_type,
            "data": job_data,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        with open(job_file, 'w') as f:
            json.dump(job, f, indent=2)
        
        print(f"[QUEUE] Job {job_id} added to queue")
        return job_id
    
    def dequeue_job(self) -> Optional[Dict[str, Any]]:
        """Get the next job from the queue"""
        job_files = list(self.queue_dir.glob("*.json"))
        if not job_files:
            return None
        
        # Get the oldest pending job
        for job_file in sorted(job_files, key=lambda f: f.stat().st_mtime):
            try:
                with open(job_file, 'r') as f:
                    job = json.load(f)
                
                # Only process pending jobs
                if job.get("status") == "pending":
                    # Mark as processing
                    job["status"] = "processing"
                    job["started_at"] = datetime.now().isoformat()
                    
                    with open(job_file, 'w') as f:
                        json.dump(job, f, indent=2)
                    
                    print(f"[QUEUE] Processing job {job['id']}")
                    return job
            except Exception as e:
                print(f"[QUEUE] Error reading job file {job_file}: {e}")
                continue
        
        return None
    
    def mark_job_complete(self, job_id: str, result: Dict[str, Any] = None):
        """Mark a job as completed"""
        job_file = self.queue_dir / f"{job_id}.json"
        if job_file.exists():
            with open(job_file, 'r') as f:
                job = json.load(f)
            
            job["status"] = "completed"
            job["completed_at"] = datetime.now().isoformat()
            if result:
                job["result"] = result
            
            with open(job_file, 'w') as f:
                json.dump(job, f, indent=2)
            
            print(f"[QUEUE] Job {job_id} completed")
    
    def mark_job_failed(self, job_id: str, error: str):
        """Mark a job as failed"""
        job_file = self.queue_dir / f"{job_id}.json"
        if job_file.exists():
            with open(job_file, 'r') as f:
                job = json.load(f)
            
            job["status"] = "failed"
            job["failed_at"] = datetime.now().isoformat()
            job["error"] = error
            
            with open(job_file, 'w') as f:
                json.dump(job, f, indent=2)
            
            print(f"[QUEUE] Job {job_id} failed: {error}")
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a specific job"""
        job_file = self.queue_dir / f"{job_id}.json"
        if job_file.exists():
            with open(job_file, 'r') as f:
                return json.load(f)
        return None
    
    def remove_job(self, job_id: str):
        """Remove a job file from the queue"""
        job_file = self.queue_dir / f"{job_id}.json"
        if job_file.exists():
            job_file.unlink()
            print(f"[QUEUE] Job {job_id} removed from queue")
        else:
            print(f"[QUEUE] Job {job_id} not found in queue") 