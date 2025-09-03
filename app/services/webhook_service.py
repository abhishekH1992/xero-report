import httpx
import os
from typing import Dict, Any

class WebhookService:
    """Service for sending webhooks to external systems (like n8n)"""
    
    def __init__(self):
        self.webhook_url = os.getenv("N8N_WEBHOOK_URL")
        self.jwt_token = os.getenv("N8N_JWT_TOKEN")
    
    async def send_webhook(self, data: Dict[str, Any]):
        """Send webhook to n8n with JWT authentication"""
        if not self.webhook_url:
            print("[WEBHOOK] No webhook URL configured, skipping webhook")
            return
        
        # Prepare headers with JWT token if available
        headers = {
            "Content-Type": "application/json"
        }
        if self.jwt_token and self.jwt_token != "test_jwt_token_for_local_dev":
            headers["Authorization"] = f"Bearer {self.jwt_token}"
            print("[WEBHOOK] Using JWT authentication")
        else:
            print("[WEBHOOK] No JWT token configured or using test token, sending without authentication")
        
        try:
            async with httpx.AsyncClient() as client:
                # Send POST request with data in body
                response = await client.post(
                    self.webhook_url,
                    headers=headers,
                    json=data,  # Send data as JSON in request body
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    print(f"[WEBHOOK] Webhook sent successfully: {response.status_code}")
                else:
                    print(f"[WEBHOOK] Webhook failed: {response.status_code} - {response.text}")
                    
        except Exception as e:
            print(f"[WEBHOOK] Error sending webhook: {e}")
    
    async def send_report_completion_webhook(self, job_id: str, report_type: str, file_path: str, report_date: str, email: str = None):
        """Send webhook when report generation is complete"""
        webhook_data = {
            "job_id": job_id,
            "report_type": report_type,
            "report_date": report_date,
            "file_path": file_path,
            "file_url": f"https://finance-assistant-api.fly.dev/api/v1/reports/excel/{os.path.basename(file_path)}",
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            "status": "completed",
            "message": f"{report_type.replace('_', ' ').title()} report generated successfully"
        }
        
        # Add email to webhook data if provided
        if email:
            webhook_data["email"] = email
        
        await self.send_webhook(webhook_data)
    
    async def send_report_failure_webhook(self, job_id: str, report_type: str, error: str):
        """Send webhook when report generation fails"""
        webhook_data = {
            "job_id": job_id,
            "report_type": report_type,
            "status": "failed",
            "error": error,
            "message": f"{report_type.replace('_', ' ').title()} report generation failed"
        }
        
        await self.send_webhook(webhook_data) 