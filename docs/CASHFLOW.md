# CashFlow Report

The CashFlow report provides bank balance data across multiple time periods for ASB and ANZ bank accounts.

## API Endpoint

```
GET /api/v1/reports/cashflow
```

## Parameters

- `report_date` (optional): Report date in YYYY-MM-DD format (defaults to today)
- `period` (optional): Number of periods to go back (default: 2)
- `period_of` (optional): Type of period - "Week", "Month", or "Year" (default: "Week")
- `connection_id` (optional): Specific connection ID to filter by

## Example Request

```bash
curl -X GET "http://localhost:8000/api/v1/reports/cashflow?report_date=2025-07-21&period=4&period_of=Week" \
  -H "X-API-Key: your-api-key"
```

## Response Format

The API returns a JSON response with the following structure:

```json
{
  "connections": [
    {
      "connection_name": "Company Name",
      "banks": [
        {
          "bank_name": "ASB",
          "account_number": "12-3113-013054-200",
          "periods": [
            {
              "date_range": "2025-07-15 - 2025-07-21",
              "opening_balance": 10000.00,
              "closing_balance": 15000.00
            }
          ]
        }
      ]
    }
  ],
  "system_comments": "21'Jul 2025 - 15'Jul 2025 - Positive cash flow: $5,000.00",
  "excel_file": "tmp/cashflow_report_20250127_143022.xlsx",
  "generated_at": "2025-01-27T14:30:22.123456",
  "report_config": {
    "date_ranges": [
      {"start": "2025-07-15", "end": "2025-07-21"},
      {"start": "2025-07-08", "end": "2025-07-14"}
    ]
  }
}
```

## Excel Export

The report generates an Excel file with three sheets:

1. **Bank Balance Sheet** - Currently blank (reserved for future use)
2. **ASB** - Cash flow data for ASB bank accounts
3. **ANZ** - Cash flow data for ANZ bank accounts

### Excel Structure

Each bank sheet contains:
- **Account**: Formatted account number (e.g., "12-3113-013054-200")
- **Connection Name**: Company/tenant name
- **Date Range Columns**: For each period, shows Opening and Available (closing) balances
- **Totals**: Sum of all accounts for each period
- **System Summary**: Insights about cash flow patterns

## Bank Account Filtering

The report automatically filters bank accounts based on account numbers:
- **ASB**: Account numbers starting with "12"
- **ANZ**: Account numbers starting with "01" or "06"

Only active bank accounts are included in the report.

## Date Range Calculation

### Week Periods
- Each period covers 7 days
- Example: If report_date is 2025-07-21 and period=4, periods are:
  - 2025-07-15 to 2025-07-21
  - 2025-07-08 to 2025-07-14
  - 2025-07-01 to 2025-07-07
  - 2025-06-24 to 2025-06-30

### Month Periods
- Each period covers a calendar month
- Example: If report_date is 2025-07-21 and period=2, periods are:
  - 2025-07-01 to 2025-07-21
  - 2025-06-01 to 2025-06-30

### Year Periods
- Each period covers a calendar year
- Example: If report_date is 2025-07-21 and period=2, periods are:
  - 2025-01-01 to 2025-07-21
  - 2024-01-01 to 2024-12-31

## Error Handling

- If a connection fails, the report continues with other connections
- If bank statement data is unavailable for a period, default values (0) are used
- API errors are logged but don't stop the report generation

## Dependencies

- Xero Python SDK for API calls
- OpenPyXL for Excel generation
- FastAPI for the web API 