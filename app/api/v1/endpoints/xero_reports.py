from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd

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
    app_id: Optional[int] = Query(None, ge=1, le=2, description="Filter by Xero app ID (1-2)"),
    show_current: bool = Query(True, description="Show Current bucket separately (if false, combines Current and < 1 Month)"),
    aged_receivables_service: XeroAgedReceivablesService = Depends(get_aged_receivables_service),
    xero_auth_service: XeroAuthService = Depends(get_xero_auth_service),
    connection_id: str = Query(None, description="Connection ID(s) - comma-separated for multiple connections"),
    is_response_only: int = Query(1, description="If 1, return response only without Excel generation"),
    format: int = Query(1, description="If 1, return table format; if 0, return JSON format")
):
    """
    Custom Aged Receivables report: fetch all unpaid invoices from all connections, 
    group by contact and Xero-style aging bucket, with business unit and company columns.
    Supports multi-app functionality with app_id filtering.
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

    is_future_date = report_date_obj > datetime.now().date()

    # Get all active connections with app_id filtering
    failed_connections = []  # Track failed connections from initial retrieval
    connections = []
    
    if connection_id:
        # Handle comma-separated connection IDs
        connection_ids = [cid.strip() for cid in connection_id.split(',')]
        for cid in connection_ids:
            try:
                # Try to parse as integer for connection ID
                connection_id = int(cid)
                connection = xero_auth_service.get_connection_by_id(connection_id)
                if connection:
                    connections.append(connection)
                else:
                    # Connection not found
                    failed_connections.append({
                        "connection_id": cid,
                        "tenant_id": None,
                        "tenant_name": "Unknown",
                        "app_id": None,
                        "error": "Connection not found",
                        "error_details": f"Connection with ID {cid} was not found in the database"
                    })
            except ValueError:
                # If not an integer, try as tenant_id
                try:
                    connection = xero_auth_service.get_connection(cid)
                    if connection:
                        connections.append(connection)
                    else:
                        failed_connections.append({
                            "connection_id": cid,
                            "tenant_id": None,
                            "tenant_name": "Unknown",
                            "app_id": None,
                            "error": "Connection not found",
                            "error_details": f"Connection with ID {cid} was not found in the database"
                        })
                except Exception as e:
                    failed_connections.append({
                        "connection_id": cid,
                        "tenant_id": None,
                        "tenant_name": "Unknown",
                        "app_id": None,
                        "error": str(e),
                        "error_details": f"Failed to retrieve connection {cid}: {str(e)}"
                    })
            except Exception as e:
                # Log error but continue with other connections
                print(f"Error getting connection {cid}: {str(e)}")
                failed_connections.append({
                    "connection_id": cid,
                    "tenant_id": None,
                    "tenant_name": "Unknown",
                    "app_id": None,
                    "error": str(e),
                    "error_details": f"Failed to retrieve connection {cid}: {str(e)}"
                })
    elif app_id:
        connections = xero_auth_service.get_connections_by_app(app_id)
    else:
        connections = xero_auth_service.get_all_connections()
    
    if not connections and not failed_connections:
        raise HTTPException(status_code=404, detail="No active Xero connections found")

    # Generate bucket names based on configurable periods
    bucket_names = generate_bucket_names(periods, period_type, show_current)
    
    all_report_data = {}
    total_invoices = 0
    # failed_connections is already initialized above for initial connection retrieval
    
    # Process each connection
    for connection in connections:
        try:
            # Fetch data for this connection with app_id support
            data = await aged_receivables_service.get_aged_receivables_data(
                tenant_id=str(connection.tenant_id),
                report_date=report_date_obj,
                periods=periods,
                period_of=period_of,
                period_type=period_type,
                app_id=connection.app_id,
                is_future_date=is_future_date
            )
            
            invoices = data["invoices"]
            credit_notes = data["credit_notes"]
            overpayments = data["overpayments"] 
            
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
                
                # Check if this invoice was marked as negative by our early_paid_invoices logic
                is_negative_flag = getattr(invoice, 'is_negative', False)
                
                # Convert due_date to date if it's a string
                if due_date and isinstance(due_date, str):
                    due_date = datetime.strptime(due_date[:10], "%Y-%m-%d").date()
                
                # Determine if we should include this invoice
                include_in_report = False
                report_amount = amount_due
                report_date_field = due_date
                is_negative = False
                
                # First check if this invoice was marked as negative by our early_paid_invoices logic
                if is_negative_flag:
                    include_in_report = True
                    report_amount = amount_due  # This should be the total_amount from our logic
                    report_date_field = due_date
                    is_negative = True
                    
                elif amount_due != 0.0:
                    # Normal unpaid invoice - use due date and amount due
                    include_in_report = True
                    report_amount = amount_due
                    report_date_field = due_date
                    is_negative = amount_due < 0
                    
                elif status == "PAID" and due_date and due_date > report_date_obj and amount_due == 0.0:
                    # For past reports, only include paid invoices that were issued before the report date
                    # For future reports, include all paid invoices with future due dates
                    invoice_date = getattr(invoice, 'date', None)
                    if invoice_date and hasattr(invoice_date, 'date'):
                        invoice_date = invoice_date.date()
                    
                    if report_date_obj <= datetime.now().date():
                        # Past report logic: Only include if invoice was issued before report date
                        if invoice_date and invoice_date <= report_date_obj:
                            include_in_report = True
                            report_amount = total_amount  # Use total amount (will be made negative)
                            report_date_field = due_date  # Use actual due date for proper aging
                            is_negative = True  # Mark as negative to show as credit
                    else:
                        # Future report logic: Include all paid invoices with future due dates
                        include_in_report = True
                        report_amount = total_amount  # Use total amount (will be made negative)
                        report_date_field = due_date  # Use actual due date for proper aging
                        is_negative = True  # Mark as negative to show as credit
                
                if include_in_report and report_date_field:
                    # Handle early_paid_invoices (marked with is_negative_flag) individually
                    if is_negative_flag:
                        # Process early_paid_invoices individually to preserve invoice numbers
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
                            is_negative=True,  # Mark as negative to show as credit
                            connection_name=connection.tenant_name,
                            business_type=getattr(connection, 'business_type', 'Commercial Property'),
                            item_type="invoice",
                            show_current=show_current
                        )
                    # Group by contact for other paid invoices with future due dates
                    elif is_negative:
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
                            business_type=getattr(connection, 'business_type', 'Commercial Property'),
                            item_type="invoice",
                            show_current=show_current
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
                            business_type=getattr(connection, 'business_type', 'Commercial Property'),
                            item_type="invoice",
                            show_current=show_current
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
                        business_type=getattr(connection, 'business_type', 'Commercial Property'),
                        item_type="invoice",
                        show_current=show_current
                    )

            # Process credit notes (apply as negative values)
            for cn in credit_notes:
                # For credit notes that were processed after the report date, use total amount
                # For credit notes with remaining credit, use remaining_credit
                if getattr(cn, 'remaining_credit', 0) > 0:
                    amount_field = "remaining_credit"
                else:
                    amount_field = "total"
                
                process_financial_item(
                    item=cn,
                    report_date=report_date_obj,
                    periods=periods,
                    period_of=period_of,
                    period_type=period_type,
                    bucket_names=bucket_names,
                    report=all_report_data,
                    amount_field=amount_field,
                    date_field="date",
                    is_negative=True,
                    date_fallback=report_date_obj,
                    connection_name=connection.tenant_name,
                    business_type=getattr(connection, 'business_type', 'Commercial Property'),
                    item_type="credit_note",
                    show_current=show_current
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
                    business_type=getattr(connection, 'business_type', 'Commercial Property'),
                    item_type="overpayment",
                    show_current=show_current
                )
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[XERO REPORT] Error processing connection {connection.tenant_name} (App {connection.app_id}): {str(e)}")
            print(f"[XERO REPORT] Full error details: {error_details}")
            
            # Track failed connection
            failed_connections.append({
                "connection_id": connection.id,
                "tenant_id": connection.tenant_id,
                "tenant_name": connection.tenant_name,
                "app_id": connection.app_id,
                "error": str(e),
                "error_details": error_details
            })
            
            # Continue with other connections even if one fails
            continue

    # Prepare data for Excel export (only if is_response_only is 0)
    excel_data = []
    if is_response_only == 0:
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
            
            # Add bucket amounts to row
            for bucket_name in bucket_names:
                amount = data.get(bucket_name, 0)
                if bucket_name == "Current" and not show_current:
                    # When show_current=False, combine Current and < 1 Month amounts
                    current_amount = data.get("Current", 0)
                    less_than_one_amount = data.get("< 1 Month", 0)
                    row["Current"] = current_amount + less_than_one_amount
                elif bucket_name == "< 1 Month" and not show_current:
                    # Skip the < 1 Month column when show_current=False since it's combined with Current
                    continue
                else:
                    row[bucket_name] = amount
            
            row["Total"] = total_amount
            row["Comments"] = ""  # Add blank comments column
            # Generate system comments
            invoice_details = data.get("invoice_details", {})
            # When show_current=False, we need to combine Current and < 1 Month comments
            if not show_current:
                # Create a copy of invoice_details to avoid modifying the original
                combined_invoice_details = invoice_details.copy()
                if "Current" in combined_invoice_details and "< 1 Month" in combined_invoice_details:
                    # Combine the invoice details from both buckets
                    combined_invoice_details["Current"] = combined_invoice_details.get("Current", []) + combined_invoice_details.get("< 1 Month", [])
                    # Remove the < 1 Month entry since it's now combined
                    if "< 1 Month" in combined_invoice_details:
                        del combined_invoice_details["< 1 Month"]
                # Create a modified bucket_names list for system comments
                system_bucket_names = []
                for bucket in bucket_names:
                    if bucket == "Current":
                        system_bucket_names.append("Current & < 1 Month")
                    elif bucket == "< 1 Month":
                        continue  # Skip this bucket in system comments
                    else:
                        system_bucket_names.append(bucket)
                system_comments = generate_system_comments(combined_invoice_details, system_bucket_names)
            else:
                system_comments = generate_system_comments(invoice_details, bucket_names)
            row["System Comments"] = system_comments
            # Only include rows that have non-zero amounts
            if total_amount != 0:
                excel_data.append(row)

    # Handle table format conversion if requested
    if format == 1:
        # Convert to pandas DataFrame for table format
        table_data = []
        for key, data in all_report_data.items():
            # Calculate total amount first
            total_amount = 0
            for bucket_name in bucket_names:
                amount = data.get(bucket_name, 0)
                total_amount += amount
            
            # Only include rows that have non-zero amounts
            if total_amount != 0:
                row = {
                    "Business Unit": data.get("business_unit", "Unknown"),
                    "Company": data.get("company", "Unknown"),
                    "Contact": data.get("contact", "Unknown")
                }
                # Add aging buckets
                for bucket_name in bucket_names:
                    amount = data.get(bucket_name, 0)
                    row[bucket_name] = amount
                row["Total"] = total_amount
                
                # Generate system comments
                invoice_details = data.get("invoice_details", {})
                system_comments = generate_system_comments(invoice_details, bucket_names)
                row["System Comments"] = system_comments
                
                table_data.append(row)
        
        # Create pandas DataFrame
        df = pd.DataFrame(table_data)
        
        # Prepare response with table data
        response_data = {
            "format": "table",
            "data": df.to_dict(orient="records"),
            "columns": df.columns.tolist(),
            "shape": df.shape,
            "generated_at": report_date_obj.isoformat(),
            "total_invoices": total_invoices,
            "aging_config": {
                "periods": periods,
                "period_of": period_of,
                "period_type": period_type,
                "bucket_names": bucket_names
            },
            "app_filter": app_id,
            "failed_connections": failed_connections,
            "connection_summary": {
                "total_connections_attempted": len(connections) + len(failed_connections),
                "successful_connections": len(connections),
                "failed_connections_count": len(failed_connections),
                "success_rate": f"{(len(connections) / (len(connections) + len(failed_connections)) * 100):.1f}%" if (len(connections) + len(failed_connections)) > 0 else "0%"
            }
        }
    else:
        # Return original JSON format
        response_data = {
            "aged_receivables": all_report_data, 
            "generated_at": report_date_obj.isoformat(),
            "total_invoices": total_invoices,
            "aging_config": {
                "periods": periods,
                "period_of": period_of,
                "period_type": period_type,
                "bucket_names": bucket_names
            },
            "app_filter": app_id,
            "failed_connections": failed_connections,
            "connection_summary": {
                "total_connections_attempted": len(connections) + len(failed_connections),
                "successful_connections": len(connections),
                "failed_connections_count": len(failed_connections),
                "success_rate": f"{(len(connections) / (len(connections) + len(failed_connections)) * 100):.1f}%" if (len(connections) + len(failed_connections)) > 0 else "0%"
            }
        }
    
    # Generate Excel file only if is_response_only is 0
    if is_response_only == 0:
        # Define columns for Excel export
        excel_columns = []
        for bucket in bucket_names:
            if bucket == "Current" and not show_current:
                # Combine Current and < 1 Month in Excel header
                excel_columns.append({"header": "Current & < 1 Month", "key": bucket, "width": 15, "format": "currency"})
            elif bucket == "< 1 Month" and not show_current:
                # Skip the < 1 Month column when show_current=False since it's combined with Current
                continue
            else:
                excel_columns.append({"header": bucket, "key": bucket, "width": 15, "format": "currency"})
        
        columns = [
            {"header": "Business Unit", "key": "Business Unit", "width": 20, "format": "text"},
            {"header": "Company", "key": "Company", "width": 25, "format": "text"},
            {"header": "Contact", "key": "Contact", "width": 30, "format": "text"},
            *excel_columns,
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
        
        response_data["excel_file"] = excel_file_path
    
    return response_data
