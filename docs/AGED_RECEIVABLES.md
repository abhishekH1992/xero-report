# Aged Receivables Report

## Overview

The **Aged Receivables** report provides a detailed breakdown of outstanding invoices and credits for all connected Xero organizations, grouped by contact and aging bucket. This report helps you quickly identify overdue amounts, track customer payment behavior, and manage your cash flow more effectively.

---

## What is an Aged Receivables Report?

An aged receivables report categorizes outstanding customer invoices into time-based buckets (e.g., Current, <1 Month, 1 Month, 2 Months, Older) based on how long they have been overdue. It is a key tool for:
- Monitoring overdue payments
- Identifying high-risk customers
- Improving collections
- Reporting to management

---

## How It Works in This App

- **Multi-Tenant**: Fetches data from all active Xero connections in your database.
- **Dynamic Buckets**: Buckets are configurable (number, size, and type: days/weeks/months).
- **Contact Grouping**: Sums receivables by contact (customer) and bucket.
- **Credit Notes & Overpayments**: Credits and overpayments are applied as negative values in the correct bucket.
- **Early Payment Detection**: Handles invoices issued after report date but paid before report date.
- **Business Unit & Company Columns**: Each row is tagged with the Xero connection's business type and company name.
- **Excel Export**: Download a formatted Excel file for further analysis or sharing.
- **Combined Buckets**: Optional parameter to combine "Current" and "< 1 Month" in Excel export.
- **Failed Connections Tracking**: Provides detailed information about connections that failed during processing.

---

## Technical Implementation

### Xero API Integration

The report uses Xero's Accounting API to fetch financial data from connected organizations. The implementation follows these steps:

1. **Authentication**: Uses OAuth2 tokens stored in the database for each Xero connection
2. **Data Fetching**: Makes separate API calls for invoices, credit notes, and overpayments
3. **Processing**: Categorizes each item into aging buckets based on due dates
4. **Aggregation**: Groups data by contact and business unit
5. **Export**: Generates Excel report with detailed breakdowns

### API Endpoints Used

- **Invoices**: `GET /invoices` - Fetches unpaid and paid invoices with future due dates
- **Credit Notes**: `GET /creditnotes` - Fetches credit notes with remaining credit
- **Overpayments**: `GET /overpayments` - Fetches overpayments with remaining credit

### Data Fetching Logic

#### Invoices Query
```sql
Type == "ACCREC" && (
  (AmountDue > 0 && Status == "AUTHORISED" && Date <= DateTime(report_date)) || 
  (Status == "PAID" && DueDate > DateTime(report_date))
)
```

**What this fetches:**
- **Unpaid invoices**: `AmountDue > 0` and `Status == "AUTHORISED"` with issue date on or before report date
- **Paid invoices with future due dates**: `Status == "PAID"` and `DueDate > report_date` (these represent credits/overpayments)

#### Early Paid Invoices Query
```sql
Type == "ACCREC" && Date > DateTime(report_date)
```

**What this fetches:**
- Invoices issued after the report date but potentially paid before the report date
- These are processed separately to handle early payment scenarios

#### Credit Notes Query
```sql
Type == "ACCRECCREDIT" && 
Date <= DateTime(report_date) && 
RemainingCredit > 0 && 
(Status == "PAID" OR Status == "AUTHORISED")
```

**What this fetches:**
- Credit notes with remaining credit available
- Issued on or before the report date
- With valid status (PAID or AUTHORISED)

#### Overpayments Query
```sql
Type == "RECEIVE-OVERPAYMENT" && 
Date <= DateTime(report_date) && 
Status == "AUTHORISED"
```

**What this fetches:**
- Overpayment transactions with remaining credit
- Created on or before the report date
- With AUTHORISED status

### Payment Date Detection Logic

The system uses a multi-priority approach to determine payment dates:

1. **First Priority**: `fully_paid_on_date` field (if available)
2. **Second Priority**: Calculate total paid up to report date from `payments` array
3. **Third Priority**: `updated_date_utc` as proxy for payment date
4. **Fourth Priority**: Use issue date for old invoices that are clearly paid

#### Early Payment Calculation
When `fully_paid_on_date` is not available, the system:
- Loops through all payments in the `payments` array
- Only includes payments where `payment_date <= report_date`
- Calculates `total_paid_up_to_report_date` for the specific amount paid before report date
- Uses this calculated amount instead of the full invoice amount

### Aging Calculation Logic

The aging calculation uses calendar months to determine which bucket each invoice belongs to:

```python
# Calculate months difference
months_diff = (report_date.year - due_date.year) * 12 + (report_date.month - due_date.month)
if report_date.day < due_date.day:
    months_diff -= 1

# Bucket assignment
if months_diff <= 0:
    return "Current"  # Future due dates
elif months_diff <= 1:
    return "< 1 Month"
elif months_diff <= periods:
    return f"{months_diff} Month{'s' if months_diff > 1 else ''}"
else:
    return "Older"
```

**Aging Buckets (for periods=4):**
- **Current**: Due dates in the future (0 months overdue)
- **< 1 Month**: 1 month overdue
- **1 Month**: 2 months overdue
- **2 Months**: 3 months overdue
- **3 Months**: 4 months overdue
- **Older**: More than 4 months overdue

### Invoice Processing Scenarios

The system handles various invoice scenarios based on issue date, payment date, and due date:

#### Scenario 1: Issue date in June, Payment in June, Due date in July
- **Should NOT SHOW IN AR**: Invoice was paid before it was due
- **Condition**: `issue_date <= report_date && payment_date <= report_date && due_date > report_date`

#### Scenario 2: Issue date in June, Not Paid in June, Due date in July
- **Should SHOW IN CURRENT**: Normal unpaid invoice
- **Condition**: `issue_date <= report_date && (not payment_date || payment_date > report_date) && due_date > report_date`

#### Scenario 3: Issue date in July, Paid in June, Due date in July
- **Should SHOW IN CURRENT AS NEGATIVE**: Early payment (credit)
- **Condition**: `issue_date > report_date && payment_date <= report_date && due_date >= report_date`
- **Amount**: Uses `total_paid_up_to_report_date` (only payments before report date)

#### Scenario 4: Issue date before report date, paid before report date
- **Should NOT SHOW IN AR**: Fully paid invoice
- **Condition**: `issue_date <= report_date && payment_date <= report_date`

#### Scenario 5: Issue date before report date, paid after report date
- **Should SHOW IN CURRENT AS POSITIVE**: Normal payment
- **Condition**: `issue_date <= report_date && payment_date > report_date`

#### Scenario 6: Issue date before report date, paid on report date
- **Should NOT SHOW IN AR**: Paid on report date
- **Condition**: `issue_date <= report_date && payment_date == report_date`

#### Scenario 7: Issue date before report date, paid on or before report date
- **Should NOT SHOW IN AR**: Fully paid invoice
- **Condition**: `issue_date <= report_date && payment_date <= report_date`

### Data Processing Flow

1. **Fetch Data**: Retrieve invoices, credit notes, and overpayments from Xero
2. **Process Early Payments**: Handle invoices issued after report date but paid before report date
3. **Deduplicate**: Remove duplicate invoices based on invoice_id
4. **Categorize**: Assign each item to appropriate aging bucket
5. **Group**: Aggregate amounts by contact and business unit
6. **Calculate**: Sum totals for each bucket and overall
7. **Export**: Generate Excel report with system comments

### System Comments Generation

The report includes detailed system comments showing:
- Invoice numbers and amounts for each bucket
- Credit note details with negative amounts
- Overpayment information
- Item types and statuses

Example system comments:
```
< 1 Month: INV-0039 = 15,392.57
1 Month: INV-0035 = 15,392.57
2 Months: INV-0031 = 15,392.57
3 Months: INV-0030 = 15,392.57
Older: INV-0007 = 15,392.57, 050419 = 15,392.57
```

---

## API Usage

### Endpoint
```
GET /api/v1/reports/aged-receivables
```

### Query Parameters
| Name         | Type   | Default | Description                                  |
|--------------|--------|---------|----------------------------------------------|
| report_date  | str    | today   | Report date in YYYY-MM-DD format             |
| periods      | int    | 4       | Number of aging periods                      |
| period_of    | int    | 1       | Duration of each period                      |
| period_type  | str    | Month   | Type of period: Day, Week, or Month          |
| show_current | bool   | true    | Show Current bucket separately (if false, combines Current and < 1 Month in Excel) |

### Example Request
```bash
curl -H "X-API-Key: your-api-key" \
  "http://localhost:8000/api/v1/reports/aged-receivables?report_date=2024-06-30&periods=4&period_of=1&period_type=Month&show_current=false"
```

### Example Response (JSON)
```json
{
  "aged_receivables": {
    "Commercial Property|Demo Company (NZ)|Bayside Club": {
      "business_unit": "Commercial Property",
      "company": "Demo Company (NZ)",
      "contact": "Bayside Club",
      "Current": 0.0,
      "< 1 Month": 3411.06,
      "1 Month": 0.0,
      "2 Months": 0.0,
      "Older": 0.0,
      "Total": 3411.06
    },
    ...
  },
  "generated_at": "2024-06-30",
  "total_invoices": 17,
  "aging_config": {
    "periods": 4,
    "period_of": 1,
    "period_type": "Month",
    "bucket_names": ["Current", "< 1 Month", "1 Month", "2 Months", "Older"]
  },
  "excel_file": "tmp/aged_receivables_report.xlsx",
  "failed_connections": [
    {
      "connection_id": "invalid_connection_id",
      "tenant_id": null,
      "tenant_name": "Unknown",
      "app_id": null,
      "error": "Connection not found",
      "error_details": "Connection with ID invalid_connection_id was not found in the database"
    }
  ],
  "connection_summary": {
    "total_connections_attempted": 3,
    "successful_connections": 2,
    "failed_connections_count": 1,
    "success_rate": "66.7%"
  }
}
```

---

## Excel Export

- The API response includes a path to a downloadable Excel file.
- The Excel file contains:
  - **Business Unit** (from Xero connection)
  - **Company** (Xero tenant name)
  - **Contact** (customer name)
  - **Aging Buckets** (Current, <1 Month, etc.)
  - **Total**
  - **Comments** (blank column for notes)
  - **Summary Rows**: Total and Percentage rows at the bottom
- The file is formatted for easy reading and sharing.

### Excel Bucket Combination

When `show_current=false`:
- **JSON Response**: Still maintains separate "Current" and "< 1 Month" buckets
- **Excel Export**: Combines "Current" and "< 1 Month" into a single column "Current & < 1 Month"
- **Data Aggregation**: Sums the amounts from both buckets for the combined column

---

## Configuration & Customization

- **Aging Buckets**: Change `periods`, `period_of`, and `period_type` query params to adjust bucket size and count.
- **Business Unit**: Set per Xero connection in the database (default: "Commercial Property").
- **Company**: Pulled from the Xero tenant name.
- **API Key**: All requests require a valid API key in the `X-API-Key` header.
- **Early Payment Detection**: Automatically handles invoices with partial payments before report date.
- **Excel Bucket Combination**: Use `show_current=false` to combine Current and < 1 Month in Excel export.

---

## Failed Connections Tracking

The report now tracks and reports on connections that fail during processing. This feature helps you identify and troubleshoot connection issues.

### Failed Connection Types

1. **Connection Retrieval Failures**: When a connection ID is provided but cannot be found or retrieved from the database
2. **Data Processing Failures**: When a connection is found but fails during data fetching or processing

### Response Fields

#### `failed_connections` Array
Each failed connection includes:
- `connection_id`: The ID of the failed connection
- `tenant_id`: The Xero tenant ID (null if connection not found)
- `tenant_name`: The Xero tenant name (or "Unknown" if not found)
- `app_id`: The Xero app ID (null if connection not found)
- `error`: A brief error message
- `error_details`: Detailed error information including stack trace

#### `connection_summary` Object
Provides overall statistics:
- `total_connections_attempted`: Total number of connections processed
- `successful_connections`: Number of connections that processed successfully
- `failed_connections_count`: Number of connections that failed
- `success_rate`: Percentage of successful connections (e.g., "66.7%")

### Example Failed Connection Entry
```json
{
  "connection_id": "12345",
  "tenant_id": "tenant-uuid",
  "tenant_name": "My Company",
  "app_id": 1,
  "error": "Token expired",
  "error_details": "Xero API returned 401 Unauthorized: Token has expired and cannot be refreshed"
}
```

### Benefits
- **Visibility**: See exactly which connections failed and why
- **Troubleshooting**: Detailed error information helps identify the root cause
- **Monitoring**: Track connection health over time
- **Partial Success**: Report continues processing even if some connections fail

---

## Edge Cases Handled

### Early Payment Scenarios
- **INV-0799 Example**: Invoice issued July 1, due July 1, but payment of $8.14 made on June 30
- **Result**: Shows as negative $8.14 in Current bucket (not full invoice amount)
- **Logic**: Only payments made before report date are included

### Payment Date Detection
- **Missing fully_paid_on_date**: Uses payments array to calculate total paid up to report date
- **Multiple Payments**: Sums only payments occurring on or before report date
- **Date Format Handling**: Supports Xero's date format `/Date(timestamp)/`

### Invoice Status Handling
- **AUTHORISED with payments**: Invoices marked as AUTHORISED but with payment records
- **PAID with future due dates**: Treated as credits/overpayments
- **Mixed payment scenarios**: Handles invoices with multiple payments across different periods

### Bucket Combination
- **JSON vs Excel**: Maintains separate buckets in JSON but can combine in Excel
- **Data Integrity**: Ensures totals remain accurate when combining buckets
- **Backward Compatibility**: Default behavior maintains separate buckets

---

## Queue-Based Report Generation Plan

### Overview

This plan implements a queue-based system for Aged Receivables report generation using Fly.io's native process management capabilities. The system will support both immediate (local) and queued (background) report generation.

### Architecture

```
Dify Agent → API → Queue → Worker → tmp/ folder → n8n Webhook → Email
```

### Implementation Plan

#### Phase 1: Infrastructure Setup (Day 1)

**1.1 Fly.io Configuration**
- Update `fly.toml` to add worker process
- Configure process management for app and worker separation

**1.2 Queue System Setup**
- Implement simple file-based queue system
- Create queue service for job management
- Add Redis as optional alternative

**1.3 Worker Process**
- Create background worker for report processing
- Implement job dequeuing and processing logic
- Add error handling and retry mechanisms

#### Phase 2: API Modifications (Day 2)

**2.1 Enhanced API Endpoint**
- Add `is_local` parameter to existing endpoint
- Maintain backward compatibility
- Implement queue job creation for `is_local=false`

**2.2 Service Layer Refactoring**
- Move AR logic from `xero_reports.py` to `xero_aged_receivables_service.py`
- Create unified service interface for both local and queued processing
- Add progress tracking and status updates

**2.3 File Management**
- Implement tmp folder storage for both local and queued reports
- Add file cleanup mechanisms
- Create file download endpoint

#### Phase 3: Integration & Testing (Day 3)

**3.1 Webhook Integration**
- Implement n8n webhook triggering
- Add email notification system
- Create notification templates

**3.2 Testing & Monitoring**
- Test both local and queued workflows
- Implement logging and monitoring
- Add performance metrics

### Technical Implementation Details

#### 1. Fly.io Process Configuration

```toml
# fly.toml
[processes]
  app = ""
  worker = "python -m app.workers.report_worker"

[http_service]
  processes = ["app"]
```

#### 2. Queue System

```python
# app/services/queue_service.py
class SimpleQueueService:
    def __init__(self, queue_dir="tmp/queue"):
        self.queue_dir = queue_dir
        os.makedirs(queue_dir, exist_ok=True)
    
    async def enqueue_report_job(self, report_params: dict):
        job_id = f"ar_report_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        job_file = os.path.join(self.queue_dir, f"{job_id}.json")
        
        job_data = {
            "job_id": job_id,
            "type": "aged_receivables",
            "params": report_params,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }
        
        with open(job_file, 'w') as f:
            json.dump(job_data, f)
        
        return job_id
```

#### 3. Worker Process

```python
# app/workers/report_worker.py
class AgedReceivablesWorker:
    def __init__(self):
        self.queue_service = SimpleQueueService()
        self.ar_service = XeroAgedReceivablesService()
        self.webhook_service = WebhookService()
    
    async def process_ar_report(self, job_data: dict):
        try:
            # Generate report
            excel_file_path = await self.ar_service.generate_report(job_data["params"])
            
            # Trigger webhook with file path
            await self.webhook_service.trigger_report_complete(
                file_path=excel_file_path,
                report_type="aged_receivables",
                job_id=job_data["job_id"]
            )
            
        except Exception as e:
            # Handle errors and retries
            await self.handle_job_error(job_data, str(e))
```

#### 4. Enhanced API Endpoint

```python
# app/api/v1/endpoints/xero_reports.py
@router.get("/aged-receivables")
async def get_aged_receivables(
    # ... existing parameters ...
    is_local: bool = Query(False, description="Generate report immediately (true) or queue (false)")
):
    if is_local:
        # Existing synchronous logic
        return await generate_report_sync(params)
    else:
        # Queue the job
        job_id = await queue_service.enqueue_report_job(params)
        return {
            "status": "queued",
            "job_id": job_id,
            "message": "Report generation started. You will be notified when ready."
        }
```

#### 5. Webhook Service

```python
# app/services/webhook_service.py
class WebhookService:
    async def trigger_report_complete(self, file_path: str, report_type: str, job_id: str):
        webhook_url = os.getenv("N8N_WEBHOOK_URL")
        
        payload = {
            "file_path": file_path,
            "report_type": report_type,
            "job_id": job_id,
            "generated_at": datetime.now().isoformat()
        }
        
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=payload)
```

### Environment Variables

```env
# Queue Configuration
QUEUE_DIR=tmp/queue

# n8n Webhook
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/report-complete

# Email Configuration (for n8n)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

### File Structure

```
app/
├── workers/
│   ├── __init__.py
│   └── report_worker.py
├── services/
│   ├── queue_service.py
│   └── webhook_service.py
└── api/v1/endpoints/
    └── xero_reports.py (modified)

tmp/
├── queue/          # Queue jobs
├── reports/        # Generated reports
└── .gitkeep
```

### API Response Examples

#### Queued Report Request
```bash
GET /api/v1/reports/aged-receivables?is_local=false&report_date=2024-06-30
```

#### Queued Response
```json
{
  "status": "queued",
  "job_id": "ar_report_20240806_143022_123456",
  "message": "Report generation started. You will be notified when ready.",
  "estimated_completion": "2-3 minutes"
}
```

#### Local Report Request
```bash
GET /api/v1/reports/aged-receivables?is_local=true&report_date=2024-06-30
```

#### Local Response (existing format)
```json
{
  "aged_receivables": { ... },
  "excel_file": "tmp/aged_receivables_report_20240806_143022.xlsx",
  "generated_at": "2024-06-30"
}
```

### Benefits

1. **Scalability**: Worker processes can be scaled independently
2. **Reliability**: Failed jobs can be retried automatically
3. **User Experience**: Immediate response for queued requests
4. **Resource Management**: Heavy processing moved to background
5. **Monitoring**: Separate logs for web and worker processes
6. **Flexibility**: Support for both immediate and queued processing

### Deployment Steps

1. **Update fly.toml** with worker process configuration
2. **Deploy application** with new process structure
3. **Scale workers** based on expected load: `fly scale count worker=2`
4. **Monitor logs**: `fly logs --process worker`
5. **Test both workflows** (local and queued)

### Monitoring & Maintenance

- **Queue Monitoring**: Check queue size and processing times
- **Worker Health**: Monitor worker process status and restarts
- **File Cleanup**: Implement automatic cleanup of old reports
- **Error Tracking**: Log and alert on failed jobs
- **Performance Metrics**: Track report generation times and success rates

This implementation provides a robust, scalable solution for handling Aged Receivables report generation while maintaining backward compatibility and providing a smooth user experience.