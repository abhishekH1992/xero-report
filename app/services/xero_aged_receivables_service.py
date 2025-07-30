from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_auth import XeroAuthService
from app.util.xero_connection import create_xero_api_client


class XeroAgedReceivablesService:
    """Service for handling Xero aged receivables report data fetching with multi-app support"""
    
    def __init__(self, xero_auth_service: XeroAuthService):
        self.xero_auth_service = xero_auth_service
    
    def get_aged_receivables_data(
        self, 
        tenant_id: str, 
        report_date,
        periods: int = 4,
        period_of: int = 1,
        period_type: str = "Month",
        app_id: Optional[int] = None,
        is_future_date: bool = False
    ) -> Dict[str, Any]:
        """
        Fetch all data needed for aged receivables report
        
        Args:
            tenant_id: Xero tenant/organization ID
            report_date: Report date for calculations
            periods: Number of aging periods
            period_of: Duration of each period
            period_type: Type of period (Day, Week, Month)
            app_id: Optional Xero app ID (1-2) for multi-app support
            
        Returns:
            Dict containing invoices, credit_notes, and overpayments
        """
        # Get connection from DB with app_id support
        connection = self.xero_auth_service.get_connection(tenant_id, app_id)
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")

        # Create Xero API client with automatic token refresh
        accounting_api = create_xero_api_client(connection, tenant_id, self.xero_auth_service)

        try:
            # Fetch all data needed for the report
            date_for_xero = f"{report_date.year},{report_date.month},{report_date.day}"
            
            # Get invoices
            invoices = self._get_unpaid_invoices(accounting_api, tenant_id, date_for_xero, is_future_date)
            
            # Get credit notes
            credit_notes = self._get_credit_notes(accounting_api, tenant_id, date_for_xero)
            
            # Get bank transactions
            # bank_transactions = self._get_bank_transactions(accounting_api, tenant_id, date_for_xero)

            # Get Overpayments
            overpayments = self._get_overpayments(accounting_api, tenant_id, date_for_xero)

            return {
                "invoices": invoices,
                "credit_notes": credit_notes,
                "overpayments": overpayments,
                "report_date": report_date,
                "periods": periods,
                "period_of": period_of,
                "period_type": period_type,
                "app_id": connection.app_id
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch report data: {str(e)}")
    
    def _get_unpaid_invoices(self, accounting_api, tenant_id: str, date_for_xero: str, is_future_date: bool) -> List:
        """Fetch unpaid and paid invoices with optimized separate calls"""
        
        # Convert date string to datetime for comparison
        from datetime import datetime
        try:
            year, month, day = map(int, date_for_xero.split(','))
            report_date = datetime(year, month, day).date()
        except Exception as e:
            report_date = datetime.now().date()
        
        all_invoices = []
        
        # Call 1: Get AUTHORISED invoices with AmountDue > 0
        unpaid_invoices = []
        page = 1
        page_size = 100

        # Write a logic to check if report date is future date or past date (today's date considered as past date)
        if is_future_date:
            # Future report date logic: Only include currently unpaid invoices
            where_clause_unpaid = f'Type == "ACCREC" && Status == "AUTHORISED" && AmountDue > 0 && Date <= DateTime({date_for_xero})'
        else:
            # Past report date logic: Include invoices that were outstanding as of the report date
            where_clause_unpaid = f'Type == "ACCREC" && Date <= DateTime({date_for_xero})'

        while True:
            try:
                invoices_response = accounting_api.get_invoices(
                    tenant_id,  # xero_tenant_id
                    empty,      # if_modified_since
                    where_clause_unpaid,  # where
                    empty,      # order
                    empty,      # ids
                    empty,      # invoice_numbers
                    empty,      # contact_ids
                    ["AUTHORISED", "PAID"] if not is_future_date else ["AUTHORISED"],  # statuses - more efficient than WHERE clause
                    page,       # page
                    empty,      # include_archived
                    empty,      # created_by_my_app
                    empty,      # unitdp
                    "False",    # summary_only - Changed from "True" to "False" to get full details
                    page_size,  # page_size
                    empty       # search_term
                )
                
                if not invoices_response.invoices:
                    break
                
                unpaid_invoices.extend(invoices_response.invoices)
                
                if len(invoices_response.invoices) < page_size:
                    break
                
                if page >= 100:  # Safety limit
                    break
                    
                page += 1
                
            except Exception as e:
                break
        
        # Call 2: Get PAID invoices with DueDate > report_date
        paid_invoices = []
        page = 1
        
        if not is_future_date:
            while True:
                try:
                    where_clause_paid = f'Type == "ACCREC" && Status == "PAID" && DueDate > DateTime({date_for_xero})'
                    invoices_response = accounting_api.get_invoices(
                        tenant_id,  # xero_tenant_id
                        empty,      # if_modified_since
                        where_clause_paid,  # where
                        empty,      # order
                        empty,      # ids
                        empty,      # invoice_numbers
                        empty,      # contact_ids
                        ["PAID"],   # statuses
                        page,       # page
                        empty,      # include_archived
                        empty,      # created_by_my_app
                        empty,      # unitdp
                        "False",    # summary_only - Changed from "True" to "False" to get full details
                        page_size,  # page_size
                        empty       # search_term
                    )
                    
                    if not invoices_response.invoices:
                        break
                    
                    paid_invoices.extend(invoices_response.invoices)
                    
                    if len(invoices_response.invoices) < page_size:
                        break
                    
                    if page >= 100:  # Safety limit
                        break
                        
                    page += 1
                    
                except Exception as e:
                    print(f"[DEBUG] Exception in paid invoices API call: {str(e)}")
                    break
        
        # Filter AUTHORISED invoices (AmountDue > 0 and Date <= report_date)
        for invoice in unpaid_invoices:
            contact_name = getattr(invoice.contact, 'name', 'Unknown') if hasattr(invoice, 'contact') and invoice.contact else 'Unknown'
            
            
            if (is_future_date and invoice.type == "ACCREC" and 
                invoice.amount_due > 0 and 
                invoice.status == "AUTHORISED" and
                invoice.date and invoice.date <= report_date):
                all_invoices.append(invoice)

            elif (not is_future_date and invoice.type == "ACCREC" and 
                invoice.date and invoice.date <= report_date):
                # Past report logic: Implement specific scenarios
                issue_date = getattr(invoice, 'date', None)
                due_date = getattr(invoice, 'due_date', None)
                payment_date = getattr(invoice, 'fully_paid_on_date', None)
                status = getattr(invoice, 'status', None)
                amount_due = getattr(invoice, 'amount_due', 0)
                total_amount = getattr(invoice, 'total', 0)
                
                # Get payment date from Payments array if available
                payments = getattr(invoice, 'payments', [])
                amount_paid = getattr(invoice, 'amount_paid', 0)
                
                # First priority: Check FullyPaidOnDate
                payment_date = getattr(invoice, 'fully_paid_on_date', None)
                
                # Parse FullyPaidOnDate if it's in Xero date format
                if payment_date and isinstance(payment_date, str) and payment_date.startswith('/Date('):
                    try:
                        # Extract timestamp from "/Date(1706572800000+0000)/"
                        timestamp_str = payment_date.split('(')[1].split('+')[0]
                        timestamp = int(timestamp_str) / 1000  # Convert to seconds
                        payment_date = datetime.fromtimestamp(timestamp).date()
                    except (ValueError, IndexError):
                        payment_date = None
                elif payment_date and isinstance(payment_date, str) and payment_date.startswith('\\/Date('):
                    try:
                        # Extract timestamp from "\/Date(1706572800000+0000)\/"
                        timestamp_str = payment_date.split('(')[1].split('+')[0]
                        timestamp = int(timestamp_str) / 1000  # Convert to seconds
                        payment_date = datetime.fromtimestamp(timestamp).date()
                    except (ValueError, IndexError):
                        payment_date = None
                
                # Second priority: Get payment date from Payments array if FullyPaidOnDate not available
                if not payment_date and payments:
                    # Get the latest payment date
                    latest_payment_date = None
                    for payment in payments:
                        if hasattr(payment, 'date'):
                            payment_dt = payment.date
                            # Handle Xero date format: "/Date(1592179200000+0000)/"
                            if isinstance(payment_dt, str) and payment_dt.startswith('/Date('):
                                try:
                                    # Extract timestamp from "/Date(1592179200000+0000)/"
                                    timestamp_str = payment_dt.split('(')[1].split('+')[0]
                                    timestamp = int(timestamp_str) / 1000  # Convert to seconds
                                    payment_dt = datetime.fromtimestamp(timestamp).date()
                                except (ValueError, IndexError):
                                    continue
                            elif isinstance(payment_dt, str) and payment_dt.startswith('\\/Date('):
                                try:
                                    # Extract timestamp from "\/Date(1592179200000+0000)\/"
                                    timestamp_str = payment_dt.split('(')[1].split('+')[0]
                                    timestamp = int(timestamp_str) / 1000  # Convert to seconds
                                    payment_dt = datetime.fromtimestamp(timestamp).date()
                                except (ValueError, IndexError):
                                    continue
                            elif hasattr(payment_dt, 'date'):
                                payment_dt = payment_dt.date()
                            else:
                                continue
                            
                            if latest_payment_date is None or payment_dt > latest_payment_date:
                                latest_payment_date = payment_dt
                    
                    if latest_payment_date:
                        payment_date = latest_payment_date
                
                # Third priority: If no payments found but amount_paid > 0, use updated_date_utc as proxy
                if amount_paid > 0 and not payment_date:
                    updated_date = getattr(invoice, 'updated_date_utc', None)
                    if updated_date and hasattr(updated_date, 'date'):
                        payment_date = updated_date.date()
                
                # Fourth priority: If still no payment date but invoice is clearly paid (amount_paid > 0 and amount_due = 0)
                # and issue_date is before report_date, assume it was paid before report_date
                if amount_paid > 0 and amount_due == 0 and not payment_date and issue_date and issue_date <= report_date:
                    # Create a dummy payment date that's before the report date
                    payment_date = issue_date  # Use issue date as payment date for old invoices
                
                # Convert dates to date objects if needed
                if issue_date and hasattr(issue_date, 'date'):
                    issue_date = issue_date.date()
                if due_date and hasattr(due_date, 'date'):
                    due_date = due_date.date()
                if payment_date and hasattr(payment_date, 'date'):
                    payment_date = payment_date.date()
                
                should_include = False
                is_negative = False
                report_amount = 0
                
                # Scenario 1: Issue date in June, Payment in June, Due date in July - SHOULD NOT SHOW IN AR
                if (issue_date and issue_date <= report_date and 
                    payment_date and payment_date <= report_date and 
                    due_date and due_date > report_date):
                    should_include = False
                
                # Scenario 2: Issue date in June, Not Paid in June, Due date in July - SHOULD SHOW IN CURRENT
                elif (issue_date and issue_date <= report_date and 
                      (not payment_date or payment_date > report_date) and 
                      due_date and due_date > report_date):
                    should_include = True
                    is_negative = False
                    report_amount = amount_due if amount_due > 0 else total_amount
                
                # Scenario 3: Issue date in July, Paid in June, Due date in July - SHOULD SHOW IN CURRENT AS NEGATIVE
                elif (issue_date and issue_date > report_date and 
                      payment_date and payment_date <= report_date and 
                      due_date and due_date > report_date):
                    should_include = True
                    is_negative = True
                    report_amount = total_amount
                
                # Scenario 4: Issue date before report date, paid before report date - SHOULD NOT SHOW IN AR
                elif (issue_date and issue_date <= report_date and 
                      payment_date and payment_date <= report_date):
                    should_include = False
                
                # Scenario 5: Issue date before report date, paid after report date - SHOULD SHOW IN CURRENT AS NEGATIVE
                elif (issue_date and issue_date <= report_date and 
                      payment_date and payment_date > report_date):
                    should_include = True
                    is_negative = True
                    report_amount = total_amount
                
                # Default: Include if it was outstanding as of report date (unpaid invoices)
                elif (issue_date and issue_date <= report_date and 
                      (not payment_date or payment_date > report_date)):
                    should_include = True
                    is_negative = False
                    report_amount = amount_due if amount_due > 0 else total_amount
                
                if should_include:
                    # Create a modified invoice object with the correct amount
                    modified_invoice = type("Item", (), {})()
                    for attr in dir(invoice):
                        if not attr.startswith('_'):
                            setattr(modified_invoice, attr, getattr(invoice, attr))
                    
                    # Override the amount_due with our calculated amount
                    setattr(modified_invoice, 'amount_due', report_amount)
                    setattr(modified_invoice, 'is_negative', is_negative)

                    with open("debug.log", "a") as debug_file:
                        debug_file.write(f"[DEBUG] Invoice: {invoice.invoice_number}\n")
                        debug_file.write(f"[DEBUG] Invoice ID: {invoice.invoice_id}\n")
                        debug_file.write(f"[DEBUG] Payment Date: {payment_date}\n")
                        debug_file.write(f"[DEBUG] Issue Date: {issue_date}\n")
                        debug_file.write(f"[DEBUG] Due Date: {due_date}\n")
                        debug_file.write(f"[DEBUG] Amount Due: {amount_due}\n")
                        debug_file.write(f"[DEBUG] Total Amount: {total_amount}\n")
                        debug_file.write(f"[DEBUG] Status: {status}\n")
                        debug_file.write(f"[DEBUG] Should Include: {should_include}\n")
                        debug_file.write(f"[DEBUG] Is Negative: {is_negative}\n")
                        debug_file.write(f"[DEBUG] Report Amount: {report_amount}\n")
                        debug_file.write(f"[DEBUG] --------------------------------\n")
                    
                    all_invoices.append(modified_invoice)
        
        # Filter PAID invoices with business logic:
        # - DueDate > report_date
        # - Issue date and Due date must be in the same month (to avoid showing invoices issued in one month but due in another)
        for invoice in paid_invoices:
            if (invoice.type == "ACCREC" and
                invoice.status == "PAID" and
                invoice.due_date and invoice.due_date > report_date and
                invoice.date and invoice.due_date):
                
                # Check if issue date and due date are in the same month
                issue_date = invoice.date
                due_date = invoice.due_date
                
                # Convert to date objects if they're datetime objects
                if hasattr(issue_date, 'date'):
                    issue_date = issue_date.date()
                if hasattr(due_date, 'date'):
                    due_date = due_date.date()
                
                # Check if both dates are in the same month and year
                if (issue_date.year == due_date.year and 
                    issue_date.month == due_date.month):
                    all_invoices.append(invoice)

        return all_invoices
    
    def _get_credit_notes(self, accounting_api, tenant_id: str, date_for_xero: str) -> List:
        """Fetch all credit notes for the period"""
        # Convert date string to datetime for comparison
        from datetime import datetime
        try:
            year, month, day = map(int, date_for_xero.split(','))
            report_date = datetime(year, month, day).date()
        except Exception as e:
            report_date = datetime.now().date()
        
        credit_where_clauses = []
        credit_where_clauses.append(f'Type == "ACCRECCREDIT"')
        credit_where_clauses.append(f"Date <= DateTime({date_for_xero})")
        credit_where_clauses.append(f'(Status == "PAID" OR Status == "AUTHORISED")')
        credit_where_clause = " && ".join(credit_where_clauses)
        
        credit_notes_response = accounting_api.get_credit_notes(
            tenant_id,
            empty,  # if_modified_since
            credit_where_clause,
            empty,  # order
            empty,  # ids
            empty,  # contact_ids
            empty,  # statuses
        )
        
        # Filter credit notes based on processing date logic
        filtered_credit_notes = []
        for credit_note in (credit_notes_response.credit_notes or []):
            should_include = False
            
            # Check if credit note was processed after report date
            if hasattr(credit_note, 'fully_paid_on_date') and credit_note.fully_paid_on_date:
                # Convert to date if it's datetime
                paid_date = credit_note.fully_paid_on_date
                if hasattr(paid_date, 'date'):
                    paid_date = paid_date.date()
                
                if paid_date > report_date:
                    should_include = True
            
            # Check payments if no FullyPaidOnDate
            elif hasattr(credit_note, 'payments') and credit_note.payments:
                latest_payment_date = None
                for payment in credit_note.payments:
                    if hasattr(payment, 'date'):
                        payment_date = payment.date
                        if hasattr(payment_date, 'date'):
                            payment_date = payment_date.date()
                        
                        if latest_payment_date is None or payment_date > latest_payment_date:
                            latest_payment_date = payment_date
                
                if latest_payment_date and latest_payment_date > report_date:
                    should_include = True
            
            # Check allocations if no payments
            elif hasattr(credit_note, 'allocations') and credit_note.allocations:
                latest_allocation_date = None
                for allocation in credit_note.allocations:
                    if hasattr(allocation, 'date'):
                        allocation_date = allocation.date
                        if hasattr(allocation_date, 'date'):
                            allocation_date = allocation_date.date()
                        
                        if latest_allocation_date is None or allocation_date > latest_allocation_date:
                            latest_allocation_date = allocation_date
                
                if latest_allocation_date and latest_allocation_date > report_date:
                    should_include = True
            
            # If no processing date found, include it (for AUTHORISED credit notes)
            else:
                should_include = True
            
            if should_include:
                filtered_credit_notes.append(credit_note)
        
        return filtered_credit_notes
    
    def _get_bank_transactions(self, accounting_api, tenant_id: str, date_for_xero: str) -> List:
        """Fetch bank transactions with type RECEIVE-OVERPAYMENT for the period"""
        bank_where_clauses = ['Type == "RECEIVE-OVERPAYMENT"']
        bank_where_clauses.append(f"Date <= DateTime({date_for_xero})")
        bank_where_clauses.append(f'Status == "AUTHORISED"')
        bank_where_clauses.append(f'IsReconciled == false')
        bank_where_clause = " && ".join(bank_where_clauses)
        
        bank_transactions_response = accounting_api.get_bank_transactions(
            tenant_id,
            empty,  # if_modified_since
            bank_where_clause,
            empty,  # order
            empty,  # ids
            empty,  # bank_account_ids
            empty,  # statuses
        )
        
        return bank_transactions_response.bank_transactions or []

    def _get_overpayments(self, accounting_api, tenant_id: str, date_for_xero: str) -> List:
        """Fetch overpayments with remaining credit for the period"""
        all_overpayments = []
        page = 1
        page_size = 100
        
        while True:
            overpayment_clause = []
            overpayment_clause = ['Type == "RECEIVE-OVERPAYMENT"']
            overpayment_clause.append(f"Date <= DateTime({date_for_xero})")
            overpayment_clause.append(f'Status == "AUTHORISED"')
            overpayment_clause = " && ".join(overpayment_clause)
            
            overpayment_response = accounting_api.get_overpayments(
                tenant_id,
                empty,  # if_modified_since
                overpayment_clause,
                empty,  # order
                empty,  # ids
                empty,  # contact_ids
                empty,  # statuses,
                page,   # page
                page_size  # page_size
            )
            
            if not overpayment_response.overpayments:
                break
                
            all_overpayments.extend(overpayment_response.overpayments)
            
            # If we got fewer results than page_size, we've reached the end
            if len(overpayment_response.overpayments) < page_size:
                break
                
            page += 1
        
        # Filter overpayments with remaining credit > 0
        filtered_overpayments = [
            op for op in all_overpayments 
            if hasattr(op, 'remaining_credit') and getattr(op, 'remaining_credit', 0) > 0
        ]
        
        return filtered_overpayments

    
    @classmethod
    def get_service_dependency(cls):
        """FastAPI dependency function for XeroAgedReceivablesService"""
        from fastapi import Depends
        from app.services.xero_auth import XeroAuthService
        
        def _get_service(xero_auth_service: XeroAuthService = Depends(XeroAuthService.get_service_dependency())) -> XeroAgedReceivablesService:
            return cls(xero_auth_service)
        
        return _get_service
