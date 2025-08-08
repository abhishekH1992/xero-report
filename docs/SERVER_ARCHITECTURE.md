# Finance Assistant API - Architecture Documentation

## Overview

The Finance Assistant API is a cloud-based system that generates financial reports from Xero data and integrates with n8n for automated email delivery. The system uses a single-machine architecture deployed on Fly.io with shared storage between app and worker processes.

## System Architecture

### 1. Single Machine Architecture

The system runs on a **single machine** with both app and worker processes sharing the same resources:

```
┌─────────────────────────────────────┐
│           Single Machine            │
│  ┌─────────────────────────────┐   │
│  │        App Process          │   │
│  │  - FastAPI Web Server      │   │
│  │  - HTTP Endpoints          │   │
│  │  - File Serving            │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │      Worker Process         │   │
│  │  - Background Job Queue     │   │
│  │  - Report Generation        │   │
│  │  - Xero API Integration    │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │      Shared Volume          │   │
│  │  - Excel File Storage       │   │
│  │  - /app/storage/reports/    │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

### 2. Process Configuration

**fly.toml Configuration:**
```toml
[processes]
app = 'bash -c "python -m app.workers.report_worker & gunicorn app.main:app --bind 0.0.0.0:8000 --workers 1 --worker-class uvicorn.workers.UvicornWorker"'

[[vm]]
memory = '1gb'
cpu_kind = 'shared'
cpus = 1
processes = ['app']

[[mounts]]
source = 'shared_reports_volume'
destination = '/app/storage/reports'
processes = ['app']
```

**Key Benefits:**
- ✅ **Shared Storage**: Both processes access the same volume
- ✅ **No Network Overhead**: Direct file system access
- ✅ **Simplified Deployment**: Single machine management
- ✅ **Cost Effective**: Reduced resource usage

## Core Components

### 1. API Layer (FastAPI)

**Endpoints:**
- `POST /api/v1/reports/aged-receivables` - Generate aged receivables report
- `POST /api/v1/reports/cashflow` - Generate cashflow report
- `GET /api/v1/reports/excel/{filename}` - Serve Excel files
- `GET /health` - Health check

**File Serving:**
```python
@router.get("/excel/{filename}")
async def serve_excel_file(filename: str):
    file_path = os.path.join("/app/storage/reports", filename)
    return FileResponse(path=file_path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

### 2. Worker Process

**Background Job Processing:**
- Polls database for pending jobs every 5 seconds
- Processes one job at a time
- Updates job status (pending → processing → completed/failed)

**Report Generation:**
- Connects to Xero API using OAuth2
- Fetches financial data
- Generates Excel reports using openpyxl
- Saves files to shared volume

### 3. Database Layer

**PostgreSQL Database:**
- Job queue management
- Xero connection storage
- Report metadata storage

**Key Tables:**
- `report_queue` - Job queue management
- `xero_connections` - OAuth2 connection storage

## File Handling Architecture

### 1. File Generation

**Process Flow:**
```
1. API receives report request
2. Job added to database queue
3. Worker picks up job
4. Xero API data fetched
5. Excel file generated
6. File saved to /app/storage/reports/
7. Webhook sent to n8n
```

### 2. File Storage

**Volume Configuration:**
- **Volume Name**: `shared_reports_volume`
- **Mount Point**: `/app/storage/reports/`
- **File Format**: Excel (.xlsx)
- **Naming Convention**: `{report_type}_{timestamp}.xlsx`

**File Access:**
- **Worker**: Writes files directly to volume
- **API**: Serves files via HTTP endpoint
- **n8n**: Downloads files via HTTP GET

## Webhook Integration

### 1. Webhook Service

**Configuration:**
```python
class WebhookService:
    def __init__(self):
        self.webhook_url = os.getenv("N8N_WEBHOOK_URL")
        self.jwt_token = os.getenv("N8N_JWT_TOKEN")
```

**Webhook Payload:**
```json
{
  "job_id": "aged_receivables_report_20250808_024546_123456",
  "report_type": "aged_receivables",
  "report_date": "2025-07-31",
  "file_path": "/app/storage/reports/aged_receivables_report_20250808_024546.xlsx",
  "file_url": "https://finance-assistant-api.fly.dev/api/v1/reports/excel/aged_receivables_report_20250808_024546.xlsx",
  "file_size": 6292,
  "status": "completed",
  "message": "Aged Receivables report generated successfully"
}
```

### 2. n8n Integration

**Workflow Components:**
1. **Webhook Node** - Receives completion notification
2. **HTTP Request Node** - Downloads Excel file
3. **Email Node** - Sends email with attachment

**n8n Node Configuration:**

**HTTP Request Node:**
- **Method**: GET
- **URL**: `{{ $json.file_url }}`
- **Response Format**: File
- **Output**: Binary data

**Email Node (Microsoft Outlook):**
- **To**: Recipient email address
- **Subject**: `{{ $json.report_type.replace('_', ' ').title() }} Report - {{ $json.report_date }}`
- **Message**: `{{ $json.message }}`
- **Attachments**: 
  - **Input Data Field Name**: `data`

## Deployment Architecture

### 1. Fly.io Configuration

**Machine Specifications:**
- **Memory**: 1GB
- **CPU**: 1 shared CPU
- **Storage**: 10GB shared volume
- **Region**: Sydney (syd)

**Scaling:**
- **Current**: 2 machines for redundancy
- **Scaling**: `fly scale count 2`

### 2. Environment Variables

**Required Environment Variables:**
```bash
# Database
DATABASE_URL=postgresql://...

# Xero OAuth2
XERO_CLIENT_ID=your_client_id
XERO_CLIENT_SECRET=your_client_secret
XERO_REDIRECT_URI=your_redirect_uri

# n8n Integration
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/...
N8N_JWT_TOKEN=your_jwt_token

# App Configuration
ENVIRONMENT=production
```

## Security Considerations

### 1. Authentication

**Xero OAuth2:**
- Secure token storage in database
- Automatic token refresh
- Connection validation

**n8n Integration:**
- JWT token authentication
- Webhook URL validation
- HTTPS communication

### 2. File Security

**File Access:**
- Files served via authenticated endpoints
- No direct file system access
- Temporary file cleanup

## Performance Characteristics

### 1. Resource Usage

**Single Machine Benefits:**
- **CPU**: Shared between app and worker
- **Memory**: 1GB shared
- **Storage**: Direct access, no network overhead
- **Network**: Reduced inter-process communication

**Performance Metrics:**
- **Report Generation**: 30-60 seconds
- **File Serving**: < 100ms
- **Webhook Response**: < 1 second

### 2. Scalability

**Current Limitations:**
- Single machine architecture
- Sequential job processing
- Limited CPU resources

**Scaling Options:**
- **Vertical**: Increase machine resources
- **Horizontal**: Multiple machines (requires volume sharing solution)

## Monitoring & Logging

### 1. Log Structure

**Log Format:**
```
[TIMESTAMP] app[MACHINE_ID] region [level][COMPONENT] Message
```

**Key Log Components:**
- `[WORKER]` - Background job processing
- `[WEBHOOK]` - n8n integration
- `[AGED_RECEIVABLES]` - Report generation
- `[DB_QUEUE]` - Database operations

### 2. Health Monitoring

**Health Check Endpoint:**
- `GET /health` - Basic system health
- Database connectivity check
- Volume access verification

## Troubleshooting Guide

### 1. Common Issues

**Webhook Failures:**
- Check `N8N_WEBHOOK_URL` configuration
- Verify JWT token validity
- Ensure n8n webhook is active

**File Access Issues:**
- Verify volume mounting
- Check file permissions
- Validate file path configuration

**OAuth Authentication:**
- Refresh Xero tokens
- Verify client credentials
- Check redirect URI configuration

### 2. Debug Commands

**Check System Status:**
```bash
fly status
fly machines list
fly logs
```

**Volume Management:**
```bash
fly volumes list
fly ssh console -C "ls -la /app/storage/reports/"
```

## Future Enhancements

### 1. Planned Improvements

**Architecture Enhancements:**
- Multi-machine deployment with shared storage
- Redis for job queue management
- Cloud storage integration (S3)

**Feature Additions:**
- Additional report types
- Email templates
- Report scheduling
- Dashboard interface

### 2. Scalability Roadmap

**Phase 1**: Optimize single machine performance
**Phase 2**: Implement distributed job queue
**Phase 3**: Add cloud storage integration
**Phase 4**: Multi-region deployment

## Conclusion

The current architecture provides a robust, cost-effective solution for automated financial report generation and delivery. The single-machine design simplifies deployment while maintaining reliability through shared storage and redundant machines.

The integration with n8n enables flexible automation workflows, while the webhook-based architecture ensures reliable communication between systems.

---

**Last Updated**: August 8, 2025
**Version**: 1.0
**Architecture Type**: Single Machine with Shared Storage
