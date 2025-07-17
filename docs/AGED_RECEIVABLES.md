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
    "Commercial Properties|Demo Company (NZ)|Bayside Club": {
      "business_unit": "Commercial Properties",
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
- **Business Unit**: Set per Xero connection in the database (default: "Commercial Properties").
- **Company**: Pulled from the Xero tenant name.
- **API Key**: All requests require a valid API key in the `X-API-Key` header.