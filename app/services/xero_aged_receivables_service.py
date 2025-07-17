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
            Dict containing invoices, credit_notes, and bank_transactions
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
            bank_transactions = self._get_bank_transactions(accounting_api, tenant_id, date_for_xero)
            print(bank_transactions);
            return {
                "invoices": invoices,
                "credit_notes": credit_notes,
                "bank_transactions": bank_transactions,
                "report_date": report_date,
                "periods": periods,
                "period_of": period_of,
                "period_type": period_type
            }
            
        except Exception as e:
            print(f"[XERO AGED RECEIVABLES SERVICE] Error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch report data: {str(e)}")
    
    def _get_unpaid_invoices(self, accounting_api, tenant_id: str, date_for_xero: str) -> List:
        """Fetch all unpaid invoices"""
        where_clause = f'AmountDue>0 && Type == "ACCREC"'
        
        invoices_response = accounting_api.get_invoices(
            tenant_id,  # xero_tenant_id
            empty,      # if_modified_since
            where_clause,  # where
            empty,      # order
            empty,      # ids
            empty,      # invoice_numbers
            empty,      # contact_ids
            ["AUTHORISED"],  # statuses
        )
        
        return invoices_response.invoices or []
    
    def _get_credit_notes(self, accounting_api, tenant_id: str, date_for_xero: str) -> List:
        """Fetch all credit notes for the period"""
        credit_where_clauses = []
        credit_where_clauses.append(f"Date <= DateTime({date_for_xero})")
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

    
    @classmethod
    def get_service_dependency(cls):
        """FastAPI dependency function for XeroAgedReceivablesService"""
        from fastapi import Depends
        from app.services.xero_auth import XeroAuthService
        
        def _get_service(xero_auth_service: XeroAuthService = Depends(XeroAuthService.get_service_dependency())) -> XeroAgedReceivablesService:
            return cls(xero_auth_service)
        
        return _get_service
