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
- **Business Unit & Company Columns**: Each row is tagged with the Xero connection's business type and company name.
- **Excel Export**: Download a formatted Excel file for further analysis or sharing.

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

### Data Processing Flow

1. **Fetch Data**: Retrieve invoices, credit notes, and overpayments from Xero
2. **Deduplicate**: Remove duplicate invoices based on invoice_id
3. **Categorize**: Assign each item to appropriate aging bucket
4. **Group**: Aggregate amounts by contact and business unit
5. **Calculate**: Sum totals for each bucket and overall
6. **Export**: Generate Excel report with system comments

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

### Example Request
```bash
curl -H "X-API-Key: your-api-key" \
  "http://localhost:8000/api/v1/reports/aged-receivables?report_date=2024-06-30&periods=4&period_of=1&period_type=Month"
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
  "excel_file": "tmp/aged_receivables_report.xlsx"
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

---

## Configuration & Customization

- **Aging Buckets**: Change `periods`, `period_of`, and `period_type` query params to adjust bucket size and count.
- **Business Unit**: Set per Xero connection in the database (default: "Commercial Property").
- **Company**: Pulled from the Xero tenant name.
- **API Key**: All requests require a valid API key in the `X-API-Key` header.