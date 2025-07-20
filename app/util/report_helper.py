def calculate_aging_bucket(report_date, due_date, periods: int, period_of: int, period_type: str) -> str:
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
    
    if days <= 0:
        return "Current"
    
    # Calculate days per period based on type
    if period_type.lower() == "day":
        days_per_period = period_of
    elif period_type.lower() == "week":
        days_per_period = period_of * 7
    elif period_type.lower() == "month":
        days_per_period = period_of * 30  # Approximate
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


def generate_bucket_names(periods: int, period_type: str) -> list:
    """
    Generate bucket names based on configurable periods.
    
    Args:
        periods: Number of aging periods
        period_type: Type of period (Day, Week, Month)
    
    Returns:
        List of bucket names including Current, period buckets, and Older
    """
    # Generate bucket names based on configurable periods
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
                         connection_name=None, business_type=None):
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
    
    Returns:
        Updated report dictionary
    """

    # Extract amount
    amount = float(getattr(item, amount_field, 0))

    if amount <= 0:
        return report
    
    # Extract contact name
    contact = getattr(item, "contact", None)
    contact_name = getattr(contact, "name", "Unknown") if contact else "Unknown"
    
    # Extract invoice details
    invoice_number = getattr(item, "invoice_number", None)
    invoice_id = getattr(item, "invoice_id", None)
    status = getattr(item, "status", None)
    
    # Extract and process date
    item_date = getattr(item, date_field, None)
    
    # Handle special cases for credit notes (check allocations first)
    if hasattr(item, "allocations") and getattr(item, "allocations", []):
        allocations = getattr(item, "allocations", [])
        if allocations and getattr(allocations[0], "date", None):
            item_date = getattr(allocations[0], "date")
    
    # Convert datetime to date if needed
    if item_date and hasattr(item_date, "date"):
        item_date = item_date.date()
    
    # Use fallback date if no date available
    if not item_date:
        item_date = date_fallback or report_date
    
    # Calculate aging bucket
    bucket = calculate_aging_bucket(report_date, item_date, periods, period_of, period_type)
    
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
        report[key][bucket] = -amount  # Set as negative value (do not add)
    else:
        report[key][bucket] += amount  # Add to existing value
    
    # Store invoice details for system comments
    if invoice_number:
        invoice_detail = {
            "invoice_number": invoice_number,
            "invoice_id": invoice_id,
            "amount": amount if not is_negative else -amount,
            "is_negative": is_negative,
            "status": status
        }
        report[key]["invoice_details"][bucket].append(invoice_detail)
    
    return report

