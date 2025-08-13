from typing import List, Tuple, Any
from datetime import datetime, timedelta
import calendar

def calculate_aging_bucket(report_date, due_date, periods: int, period_of: int, period_type: str, show_current: bool = True) -> str:
    """
    Calculate aging bucket based on configurable periods.
    
    Args:
        report_date: The report date
        due_date: The invoice due date
        periods: Number of aging periods
        period_of: Duration of each period
        period_type: Type of period (Day, Week, Month)
    """
    days = (report_date - due_date).days
    
    if days < 0:
        return "Current"  # Always return Current for JSON response
    
    # For month-based periods, use actual calendar months
    if period_type.lower() == "month":
        # Calculate months difference
        months_diff = (report_date.year - due_date.year) * 12 + (report_date.month - due_date.month)
        if report_date.day < due_date.day:
            months_diff -= 1
        
        # Calculate which period this falls into using the periods parameter
        if months_diff <= 0:
            return f"< 1 {period_type}"  # Current invoices go to < 1 Month
        elif months_diff == 1:
            return f"1 {period_type}"
        else:
            # For periods > 1, check each period dynamically
            # The bucket names are: < 1 Month, 1 Month, 2 Months, 3 Months, etc.
            # But the generate_bucket_names function creates buckets up to periods-1
            # So for periods=4, we have: Current, < 1 Month, 1 Month, 2 Months, 3 Months, Older
            # For periods=3, we have: Current, < 1 Month, 1 Month, 2 Months, Older
            for i in range(2, periods):  # Changed from periods+1 to periods
                if months_diff == i:
                    return f"{i} {period_type}{'s' if i > 1 else ''}"
            
            return "Older"
    else:
        # Calculate days per period based on type
        if period_type.lower() == "day":
            days_per_period = period_of
        elif period_type.lower() == "week":
            days_per_period = period_of * 7
        else:
            days_per_period = period_of * 30  # Default to month
        
        # Calculate which period this falls into
        for i in range(1, periods + 1):
            if days <= i * days_per_period:
                if i == 1:
                    return f"< 1 {period_type}"
                else:
                    return f"{i-1} {period_type}{'s' if i-1 > 1 else ''}"
        
        return "Older"


def generate_bucket_names(periods: int, period_type: str, show_current: bool = True) -> list:
    """
    Generate bucket names based on configurable periods.
    
    Args:
        periods: Number of aging periods
        period_type: Type of period (Day, Week, Month)
        show_current: Whether to show Current bucket (always True for JSON, used for Excel headings)
    
    Returns:
        List of bucket names including Current, period buckets, and Older
    """
    # Always generate separate Current and < 1 Month buckets for JSON response
    bucket_names = ["Current"]
    for i in range(1, periods + 1):
        if i == 1:
            bucket_names.append(f"< 1 {period_type}")
        else:
            bucket_names.append(f"{i-1} {period_type}{'s' if i-1 > 1 else ''}")
    bucket_names.append("Older")
    
    return bucket_names


def process_financial_item(item, report_date, periods, period_of, period_type, bucket_names, report, 
                         amount_field, date_field, is_negative=False, date_fallback=None, 
                         connection_name=None, business_type=None, item_type="invoice", show_current=True):
    """
    Process a financial item (invoice, credit note, bank transaction) and categorize it into aging buckets.
    
    Args:
        item: The financial item object
        report_date: The report date for calculations
        periods: Number of aging periods
        period_of: Duration of each period
        period_type: Type of period (Day, Week, Month)
        bucket_names: List of bucket names
        report: The report dictionary to update
        amount_field: Field name for the amount (e.g., 'amount_due', 'remaining_credit', 'total')
        date_field: Field name for the date (e.g., 'due_date', 'date')
        is_negative: Whether to treat the amount as negative (for credits/overpayments)
        date_fallback: Fallback date if the primary date is not available
        item_type: Type of item ("invoice", "credit_note", "bank_transaction")
    
    Returns:
        Updated report dictionary
    """

    # Extract amount
    amount = float(getattr(item, amount_field, 0))

    # For bank transactions, we allow positive amounts since we treat them as negative in the report
    if amount <= 0 and item_type != "bank_transaction":
        return report
    
    # Extract contact name
    contact = getattr(item, "contact", None)
    contact_name = getattr(contact, "name", "Unknown") if contact else "Unknown"
    
    # Extract item details based on type
    if item_type == "invoice":
        item_number = getattr(item, "invoice_number", None)
        item_id = getattr(item, "invoice_id", None)
        status = getattr(item, "status", None)
    elif item_type == "credit_note":
        item_number = getattr(item, "credit_note_number", None)
        item_id = getattr(item, "credit_note_id", None)
        status = getattr(item, "status", None)
    elif item_type == "bank_transaction":
        item_number = f"{getattr(item, 'bank_transaction_id', 'Unknown')[:8]}"  # Short ID
        item_id = getattr(item, "bank_transaction_id", None)
        status = getattr(item, "status", None)
    else:
        item_number = "Unknown"
        item_id = None
        status = None
    
    # Extract and process date
    item_date = getattr(item, date_field, None)
    
    # Handle special cases for credit notes (check allocations first)
    if hasattr(item, "allocations") and getattr(item, "allocations", []):
        allocations = getattr(item, "allocations", [])
        if allocations and getattr(allocations[0], "date", None):
            item_date = getattr(allocations[0], "date")
    elif item_type == "credit_note":
        # Credit notes without allocations should use due_date for aging calculations
        if hasattr(item, "due_date") and getattr(item, "due_date", None):
            item_date = getattr(item, "due_date")
        elif hasattr(item, "DueDate") and getattr(item, "DueDate", None):
            # Handle Xero API response format
            item_date = getattr(item, "DueDate")

    # Convert datetime to date if needed
    if item_date and hasattr(item_date, "date"):
        item_date = item_date.date()
    
    # Use fallback date if no date available
    if not item_date:
        item_date = date_fallback or report_date
    
    # Calculate aging bucket
    bucket = calculate_aging_bucket(report_date, item_date, periods, period_of, period_type, show_current)
    # Create a unique key that includes business unit and company
    if connection_name and business_type:
        key = f"{business_type}|{connection_name}|{contact_name}"
    else:
        key = contact_name

    # Initialize report entry if needed
    if key not in report:
        report[key] = {
            "business_unit": business_type or "Unknown",
            "company": connection_name or "Unknown", 
            "contact": contact_name,
            **{name: 0 for name in bucket_names},
            "invoice_details": {name: [] for name in bucket_names}  # Store invoice details for each bucket
        }
    
    # Add or subtract amount to bucket
    if is_negative:
        report[key][bucket] -= amount  # Subtract amount (add negative value)
    else:
        report[key][bucket] += amount  # Add to existing value
    
    # Store item details for system comments
    if item_number:
        item_detail = {
            "item_number": item_number,
            "item_id": item_id,
            "amount": amount if not is_negative else -amount,
            "is_negative": is_negative,
            "status": status,
            "item_type": item_type
        }
        report[key]["invoice_details"][bucket].append(item_detail)
    
    return report

def calculate_date_ranges(report_date: str, period: int = 2, period_of: str = "Week") -> List[Tuple[str, str]]:
    """
    Calculate date ranges for CashFlow report.
    
    Args:
        report_date: Report date in YYYY-MM-DD format
        period: Number of periods to go back
        period_of: Type of period (Week, Month, Year)
    
    Returns:
        List of tuples containing (start_date, end_date) in YYYY-MM-DD format
    """
    try:
        end_date = datetime.strptime(report_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid report_date format. Use YYYY-MM-DD.")
    
    date_ranges = []
    
    for i in range(period):
        if period_of.lower() == "week":
            # Calculate week ranges (7 days each)
            start_date = end_date - timedelta(days=6)
            date_ranges.append((start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
            end_date = start_date - timedelta(days=1)
            
        elif period_of.lower() == "month":
            # Calculate month ranges
            if end_date.day == 1:
                # If end_date is first day of month, go to last day of previous month
                if end_date.month == 1:
                    start_date = datetime(end_date.year - 1, 12, 1).date()
                else:
                    start_date = datetime(end_date.year, end_date.month - 1, 1).date()
            else:
                # Start from first day of current month
                start_date = datetime(end_date.year, end_date.month, 1).date()
            
            date_ranges.append((start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
            
            # Set end_date to last day of previous month
            if start_date.month == 1:
                end_date = datetime(start_date.year - 1, 12, 31).date()
            else:
                last_day = calendar.monthrange(start_date.year, start_date.month - 1)[1]
                end_date = datetime(start_date.year, start_date.month - 1, last_day).date()
                
        elif period_of.lower() == "year":
            # Calculate year ranges
            start_date = datetime(end_date.year, 1, 1).date()
            date_ranges.append((start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
            end_date = datetime(end_date.year - 1, 12, 31).date()
    
    return date_ranges


def filter_bank_accounts(accounts: List[Any]) -> List[Any]:
    """
    Filter bank accounts to only include ASB and ANZ banks based on account number.
    
    Args:
        accounts: List of bank account objects from Xero API
    
    Returns:
        Filtered list containing only ASB and ANZ accounts
    """
    filtered_accounts = []
    
    for account in accounts:
        account_number = getattr(account, 'bank_account_number', '')
        account_type = getattr(account, 'bank_account_type', '')
        status = getattr(account, 'status', '')
        
        # Check if it's an active bank account
        if account_type == "BANK" and status == "ACTIVE":
            # ASB bank: account number starts with 12
            if account_number.startswith('12'):
                setattr(account, 'bank_name', 'ASB')
                filtered_accounts.append(account)
            # ANZ bank: account number starts with 01 or 06
            elif account_number.startswith('01') or account_number.startswith('06'):
                setattr(account, 'bank_name', 'ANZ')
                filtered_accounts.append(account)
    
    return filtered_accounts


def format_account_number(account_number: str) -> str:
    """
    Convert account number to New Zealand bank account format.
    
    Args:
        account_number: Raw account number (e.g., "123113013054200")
    
    Returns:
        Formatted account number (e.g., "12-3113-0130542-00")
        Format: BB-bbbb-AAAAAAA-SSS
        Where: BB = bank code (2 digits)
               bbbb = branch code (4 digits) 
               AAAAAAA = account number (7 digits)
               SSS = suffix (3 digits, sometimes 2 with leading zero)
    """
    if not account_number:
        return ""
    
    # Remove any non-digit characters
    clean_number = ''.join(filter(str.isdigit, account_number))
    
    if len(clean_number) >= 16:
        # Full format: BB-bbbb-AAAAAAA-SSS (16 digits)
        # Example: 123244001865700 -> 12-3244-0018657-00
        return f"{clean_number[:2]}-{clean_number[2:6]}-{clean_number[6:13]}-{clean_number[13:16]}"
    elif len(clean_number) >= 13:
        # Format: BB-bbbb-AAAAAAA (13 digits)
        # Example: 01019400710472000 -> 01-0194-00710472-000
        return f"{clean_number[:2]}-{clean_number[2:6]}-{clean_number[6:13]}-{clean_number[13:]}"
    elif len(clean_number) >= 10:
        # Format: BB-bbbb-AAAA (10 digits)
        return f"{clean_number[:2]}-{clean_number[2:6]}-{clean_number[6:]}"
    elif len(clean_number) >= 6:
        # Format: BB-bbbb (6 digits)
        return f"{clean_number[:2]}-{clean_number[2:]}"
    else:
        # Return as is if too short
        return account_number


def format_date_range_for_excel(start_date: str, end_date: str) -> str:
    """
    Format date range for Excel column headers.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    
    Returns:
        Formatted string (e.g., "21'Jul 2025 - 15'Jul 2025")
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        start_formatted = f"{start_dt.day}'{start_dt.strftime('%b')} {start_dt.year}"
        end_formatted = f"{end_dt.day}'{end_dt.strftime('%b')} {end_dt.year}"
        
        return f"{start_formatted} - {end_formatted}"
    except ValueError:
        return f"{start_date} - {end_date}"


def calculate_cash_balance_summary(cashflow_data: dict, date_ranges: List[Tuple[str, str]], 
                                 ownership_groups: dict, report_date: str) -> dict:
    """
    Calculate cash balance summary for the Bank Balance Report.
    
    Args:
        cashflow_data: Dictionary containing cashflow data
        date_ranges: List of date ranges used in the report
        ownership_groups: Dictionary containing connections grouped by ownership
        report_date: Report date string
    
    Returns:
        Dictionary containing calculated cash balance summary
    """
    summary = {
        "report_date": report_date,
        "periods": {},
        "term_deposit": 1300000.00,  # Static term deposit value
        "minimum_cash_holding": 5000000.00  # Static minimum cash holding
    }
    
    # Calculate for each period
    for start_date, end_date in date_ranges:
        period_key = f"{start_date}_{end_date}"
        summary["periods"][period_key] = {
            "fully_owned": 0.0,
            "partially_owned": 0.0,
            "total_available_cash": 0.0,
            "total_with_term_deposit": 0.0,
            "minimum_cash_holding_excess": 0.0
        }
        
        # Calculate fully owned cash
        for connection in ownership_groups.get("fully_owned", []):
            connection_name = connection.tenant_name
            if connection_name in cashflow_data:
                for account_data in cashflow_data[connection_name].get('accounts', []):
                    period_data = account_data.get('periods', {}).get(period_key, {})
                    closing_balance = period_data.get('closing_balance', 0)
                    summary["periods"][period_key]["fully_owned"] += float(closing_balance) if closing_balance else 0
        
        # Calculate partially owned cash
        for connection in ownership_groups.get("partially_owned", []):
            connection_name = connection.tenant_name
            if connection_name in cashflow_data:
                for account_data in cashflow_data[connection_name].get('accounts', []):
                    period_data = account_data.get('periods', {}).get(period_key, {})
                    closing_balance = period_data.get('closing_balance', 0)
                    summary["periods"][period_key]["partially_owned"] += float(closing_balance) if closing_balance else 0
        
        # Calculate totals
        period_summary = summary["periods"][period_key]
        period_summary["total_available_cash"] = period_summary["fully_owned"] + period_summary["partially_owned"]
        period_summary["total_with_term_deposit"] = period_summary["total_available_cash"] + summary["term_deposit"]
        period_summary["minimum_cash_holding_excess"] = period_summary["total_available_cash"] - summary["minimum_cash_holding"]
    
    return summary