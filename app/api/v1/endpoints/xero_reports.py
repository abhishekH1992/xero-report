from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_aged_receivables_service import XeroAgedReceivablesService
from app.services.xero_auth import XeroAuthService
from app.util.report_export import export_report_to_excel, generate_system_comments
from app.util.report_helper import calculate_aging_bucket, generate_bucket_names, process_financial_item
from app.util.auth import api_key_auth

router = APIRouter(
    prefix="/reports",
    tags=["Xero Reports"],
    dependencies=[Depends(api_key_auth)]
)

get_aged_receivables_service = XeroAgedReceivablesService.get_service_dependency()
get_xero_auth_service = XeroAuthService.get_service_dependency()

@router.get("/aged-receivables")
async def get_aged_receivables(
    report_date: str = Query(None, description="Report date in YYYY-MM-DD format"),
    periods: int = Query(4, description="Number of aging periods"),
    period_of: int = Query(1, description="Duration of each period"),
    period_type: str = Query("Month", description="Type of period (Day, Week, Month)"),
    aged_receivables_service: XeroAgedReceivablesService = Depends(get_aged_receivables_service),
    xero_auth_service: XeroAuthService = Depends(get_xero_auth_service),
    connection_id: str = Query(None, description="Connection ID")
):
    """
    Custom Aged Receivables report: fetch all unpaid invoices from all connections, 
    group by contact and Xero-style aging bucket, with business unit and company columns.
    """
    # Parse report_date or use today
    if report_date:
        try:
            parsed_date = datetime.strptime(report_date, "%Y-%m-%d").date()
            report_date_obj = parsed_date
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid report_date format. Use YYYY-MM-DD.")
    else:
        report_date_obj = datetime.utcnow().date()

    # Get all active connections
    if connection_id:
        connections = [xero_auth_service.get_connection(connection_id)]
    else:
        connections = xero_auth_service.get_all_connections()
    if not connections:
        raise HTTPException(status_code=404, detail="No active Xero connections found")

    # Generate bucket names based on configurable periods
    bucket_names = generate_bucket_names(periods, period_type)
    
    all_report_data = {}
    total_invoices = 0
    
    # Process each connection
    for connection in connections:
        try:
            # Fetch data for this connection
            data = aged_receivables_service.get_aged_receivables_data(
                tenant_id=str(connection.tenant_id),
                report_date=report_date_obj,
                periods=periods,
                period_of=period_of,
                period_type=period_type
            )
            
            invoices = data["invoices"]
            credit_notes = data["credit_notes"]
            overpayments = data["overpayments"]  # Now properly contains overpayments from the service
            
            total_invoices += len(invoices)
            
            # Process invoices
            # First, group invoices by contact to handle multiple paid invoices per contact
            contact_invoices = {}
            
            for invoice in invoices:
                amount_due = getattr(invoice, 'amount_due', 0.0)
                due_date = getattr(invoice, 'due_date', None)
                status = getattr(invoice, 'status', None)
                total_amount = getattr(invoice, 'total', 0.0)
                contact_name = getattr(invoice.contact, 'name', 'Unknown') if hasattr(invoice, 'contact') and invoice.contact else 'Unknown'
                
                # Convert due_date to date if it's a string
                if due_date and isinstance(due_date, str):
                    due_date = datetime.strptime(due_date[:10], "%Y-%m-%d").date()
                
                # Determine if we should include this invoice
                include_in_report = False
                report_amount = amount_due
                report_date_field = due_date
                is_negative = False
                
                if amount_due != 0.0:
                    # Normal unpaid invoice - use due date and amount due
                    include_in_report = True
                    report_amount = amount_due
                    report_date_field = due_date
                    is_negative = amount_due < 0
                elif status == "PAID" and due_date and due_date > report_date_obj and amount_due == 0.0:
                    # Paid invoice with future due date and zero amount due = credit
                    include_in_report = True
                    report_amount = total_amount  # Use total amount (will be made negative)
                    report_date_field = due_date  # Use actual due date for proper aging
                    is_negative = True  # Mark as negative to show as credit
                
                if include_in_report and report_date_field:
                    # Group by contact for paid invoices with future due dates
                    if is_negative:
                        if contact_name not in contact_invoices:
                            contact_invoices[contact_name] = {
                                'contact': invoice.contact,
                                'total_amount': 0,
                                'report_date_field': report_date_field,
                                'is_negative': is_negative,
                                'status': status
                            }
                        contact_invoices[contact_name]['total_amount'] += report_amount
                    else:
                        # Process unpaid invoices immediately
                        item = type("Item", (), {})()
                        setattr(item, "contact", invoice.contact)
                        setattr(item, "due_date", report_date_field)
                        setattr(item, "amount_due", report_amount)
                        setattr(item, "status", status)
                        setattr(item, "total", total_amount)
                        setattr(item, "invoice_number", getattr(invoice, 'invoice_number', None))
                        setattr(item, "invoice_id", getattr(invoice, 'invoice_id', None))
                        
                        process_financial_item(
                            item,
                            report_date_obj,
                            periods,
                            period_of,
                            period_type,
                            bucket_names,
                            all_report_data,
                            amount_field="amount_due",
                            date_field="due_date",
                            is_negative=is_negative,
                            connection_name=connection.tenant_name,
                            business_type=getattr(connection, 'business_type', 'Commercial Properties'),
                            item_type="invoice"
                        )
            
            # Process grouped paid invoices
            for contact_name, invoice_data in contact_invoices.items():
                # For grouped invoices, we need to get the actual invoice numbers
                # This represents paid invoices with future due dates (credits)
                # We'll create separate items for each invoice to preserve invoice numbers
                
                # Get the original invoices for this contact that were grouped
                contact_invoices_list = [inv for inv in invoices if getattr(inv.contact, 'name', '') == contact_name and inv.status == "PAID" and getattr(inv, 'due_date', None) and inv.due_date > report_date_obj and inv.amount_due == 0.0]
                
                if contact_invoices_list:
                    # Process each invoice individually to preserve invoice numbers
                    for invoice in contact_invoices_list:
                        item = type("Item", (), {})()
                        setattr(item, "contact", invoice.contact)
                        setattr(item, "due_date", getattr(invoice, 'due_date', report_date_obj))  # Use actual due date for proper aging
                        setattr(item, "amount_due", getattr(invoice, 'total', 0))  # Use total amount
                        setattr(item, "status", invoice.status)
                        setattr(item, "total", getattr(invoice, 'total', 0))
                        setattr(item, "invoice_number", getattr(invoice, 'invoice_number', 'Unknown'))
                        setattr(item, "invoice_id", getattr(invoice, 'invoice_id', None))
                        
                        process_financial_item(
                            item,
                            report_date_obj,
                            periods,
                            period_of,
                            period_type,
                            bucket_names,
                            all_report_data,
                            amount_field="amount_due",
                            date_field="due_date",
                            is_negative=True,  # Mark as negative to show as credit
                            connection_name=connection.tenant_name,
                            business_type=getattr(connection, 'business_type', 'Commercial Properties'),
                            item_type="invoice"
                        )
                else:
                    # Fallback to grouped approach if we can't find individual invoices
                    item = type("Item", (), {})()
                    setattr(item, "contact", invoice_data['contact'])
                    setattr(item, "due_date", invoice_data['report_date_field'])
                    setattr(item, "amount_due", invoice_data['total_amount'])
                    setattr(item, "status", invoice_data['status'])
                    setattr(item, "total", invoice_data['total_amount'])
                    setattr(item, "invoice_number", "Invoice Overpayments")
                    setattr(item, "invoice_id", None)
                    
                    process_financial_item(
                        item,
                        report_date_obj,
                        periods,
                        period_of,
                        period_type,
                        bucket_names,
                        all_report_data,
                        amount_field="amount_due",
                        date_field="due_date",
                        is_negative=invoice_data['is_negative'],
                        connection_name=connection.tenant_name,
                        business_type=getattr(connection, 'business_type', 'Commercial Properties'),
                        item_type="invoice"
                    )

            # Process credit notes (apply as negative values)
            for cn in credit_notes:
                process_financial_item(
                    item=cn,
                    report_date=report_date_obj,
                    periods=periods,
                    period_of=period_of,
                    period_type=period_type,
                    bucket_names=bucket_names,
                    report=all_report_data,
                    amount_field="remaining_credit",
                    date_field="date",
                    is_negative=True,
                    date_fallback=report_date_obj,
                    connection_name=connection.tenant_name,
                    business_type=getattr(connection, 'business_type', 'Commercial Properties'),
                    item_type="credit_note"
                )

            # Process overpayments (apply as negative values for credits)
            for overpayment in overpayments:
                process_financial_item(
                    item=overpayment,
                    report_date=report_date_obj,
                    periods=periods,
                    period_of=period_of,
                    period_type=period_type,
                    bucket_names=bucket_names,
                    report=all_report_data,
                    amount_field="remaining_credit",
                    date_field="date",
                    is_negative=True,
                    date_fallback=report_date_obj,
                    connection_name=connection.tenant_name,
                    business_type=getattr(connection, 'business_type', 'Commercial Properties'),
                    item_type="overpayment"
                )
                
        except Exception as e:
            print(f"[XERO REPORT] Error processing connection {connection.tenant_name}: {str(e)}")
            # Continue with other connections even if one fails
            continue

    # Prepare data for Excel export
    excel_data = []
    for key, data in all_report_data.items():
        # Calculate total amount first
        total_amount = 0
        for bucket_name in bucket_names:
            amount = data.get(bucket_name, 0)
            total_amount += amount
        contact_name = data.get("contact", "Unknown")
        row = {
            "Business Unit": data.get("business_unit", "Unknown"),
            "Company": data.get("company", "Unknown"),
            "Contact": contact_name
        }
        for bucket_name in bucket_names:
            amount = data.get(bucket_name, 0)
            row[bucket_name] = amount
        row["Total"] = total_amount
        row["Comments"] = ""  # Add blank comments column
        # Generate system comments
        invoice_details = data.get("invoice_details", {})
        system_comments = generate_system_comments(invoice_details, bucket_names)
        row["System Comments"] = system_comments
        # Only include rows that have non-zero amounts
        if total_amount != 0:
            excel_data.append(row)

    # Define columns for Excel export
    columns = [
        {"header": "Business Unit", "key": "Business Unit", "width": 20, "format": "text"},
        {"header": "Company", "key": "Company", "width": 25, "format": "text"},
        {"header": "Contact", "key": "Contact", "width": 30, "format": "text"},
        *[{"header": bucket, "key": bucket, "width": 15, "format": "currency"} for bucket in bucket_names],
        {"header": "Total", "key": "Total", "width": 15, "format": "currency"},
        {"header": "Comments", "key": "Comments", "width": 25, "format": "text"},
        {"header": "System Comments", "key": "System Comments", "width": 60, "format": "text"}
    ]
    
    # Export to Excel
    excel_file_path = export_report_to_excel(
        data=excel_data,
        columns=columns,
        filename="aged_receivables_report",
        sheet_name="Aged Receivables",
        title="Aged Receivables Summary",
        report_date=f"As at {report_date_obj.strftime('%d %B %Y')}",
        output_dir="tmp",
        include_totals=True,
        include_percentages=True
    )
    
    return {
        "aged_receivables": all_report_data, 
        "generated_at": report_date_obj.isoformat(),
        "total_invoices": total_invoices,
        "aging_config": {
            "periods": periods,
            "period_of": period_of,
            "period_type": period_type,
            "bucket_names": bucket_names
        },
        "excel_file": excel_file_path
    }
