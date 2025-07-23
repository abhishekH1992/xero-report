from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import HTTPException

from xero_python.accounting.api.accounting_api import empty

from app.services.xero_auth import XeroAuthService
from app.util.xero_connection import create_xero_api_client


class XeroAgedReceivablesService:
    """Service for handling Xero aged receivables report data fetching"""
    
    def __init__(self, xero_auth_service: XeroAuthService):
        self.xero_auth_service = xero_auth_service
    
    def get_aged_receivables_data(
        self, 
        tenant_id: str, 
        report_date,
        periods: int = 4,
        period_of: int = 1,
        period_type: str = "Month"
    ) -> Dict[str, Any]:
        """
        Fetch all data needed for aged receivables report
        
        Args:
            tenant_id: Xero tenant/organization ID
            report_date: Report date for calculations
            periods: Number of aging periods
            period_of: Duration of each period
            period_type: Type of period (Day, Week, Month)
            
        Returns:
            Dict containing invoices, credit_notes, and overpayments
        """
        # Get connection from DB
        connection = self.xero_auth_service.get_connection(tenant_id)
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")

        # Create Xero API client with automatic token refresh
        accounting_api = create_xero_api_client(connection, tenant_id, self.xero_auth_service)

        try:
            # Fetch all data needed for the report
            date_for_xero = f"{report_date.year},{report_date.month},{report_date.day}"
            
            # Get invoices
            invoices = self._get_unpaid_invoices(accounting_api, tenant_id, date_for_xero)
            
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
                "period_type": period_type
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch report data: {str(e)}")
    
    def _get_unpaid_invoices(self, accounting_api, tenant_id: str, date_for_xero: str) -> List:
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
        
        while True:
            try:
                where_clause_unpaid = f'Type == "ACCREC" && Status == "AUTHORISED" && AmountDue > 0 && Date <= DateTime({date_for_xero})'
                
                invoices_response = accounting_api.get_invoices(
                    tenant_id,  # xero_tenant_id
                    empty,      # if_modified_since
                    where_clause_unpaid,  # where
                    empty,      # order
                    empty,      # ids
                    empty,      # invoice_numbers
                    empty,      # contact_ids
                    ["AUTHORISED"],  # statuses - more efficient than WHERE clause
                    page,       # page
                    empty,      # include_archived
                    empty,      # created_by_my_app
                    empty,      # unitdp
                    "True",     # summary_only
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
                    "True",     # summary_only
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
                break
        
        # Combine and filter based on business logic
        
        # Filter AUTHORISED invoices (AmountDue > 0 and Date <= report_date)
        for invoice in unpaid_invoices:
            if (invoice.type == "ACCREC" and 
                invoice.amount_due > 0 and 
                invoice.status == "AUTHORISED" and
                invoice.date and invoice.date <= report_date):
                all_invoices.append(invoice)
        
        # Filter PAID invoices (DueDate > report_date)
        for invoice in paid_invoices:
            if (invoice.type == "ACCREC" and
                invoice.status == "PAID" and
                invoice.due_date and invoice.due_date > report_date):
                all_invoices.append(invoice)
        
        return all_invoices
    
    def _get_credit_notes(self, accounting_api, tenant_id: str, date_for_xero: str) -> List:
        """Fetch all credit notes for the period"""
        credit_where_clauses = []
        credit_where_clauses.append(f'Type == "ACCRECCREDIT"')
        credit_where_clauses.append(f"Date <= DateTime({date_for_xero})")
        credit_where_clauses.append(f"RemainingCredit > 0")
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
        
        return credit_notes_response.credit_notes or []
    
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
