from typing import Dict, Any, List, Tuple
from datetime import datetime
from xero_python.accounting.api.accounting_api import AccountingApi, empty
from xero_python.finance.api.finance_api import FinanceApi
from xero_python.api_client import ApiClient

from app.util.xero_connection import create_xero_api_client
from app.util.report_helper import (
    calculate_date_ranges, 
    filter_bank_accounts
)
from app.services.xero_auth import XeroAuthService
from app.database.models import XeroConnection


class XeroCashFlowService:
    """Service for generating CashFlow reports from Xero data."""
    
    def __init__(self, xero_auth_service: XeroAuthService):
        self.xero_auth_service = xero_auth_service
    
    @classmethod
    def get_service_dependency(cls):
        """FastAPI dependency function for XeroCashFlowService"""
        from fastapi import Depends
        from app.services.xero_auth import XeroAuthService
        
        def _get_service(xero_auth_service: XeroAuthService = Depends(XeroAuthService.get_service_dependency())) -> XeroCashFlowService:
            return cls(xero_auth_service)
        
        return _get_service
    
    def get_cashflow_data(
        self,
        report_date: str,
        period: int = 2,
        period_of: str = "Week",
        connection_id: str = None
    ) -> Dict[str, Any]:
        """
        Get CashFlow data for all connections or a specific connection.
        
        Args:
            report_date: Report date in YYYY-MM-DD format
            period: Number of periods to go back
            period_of: Type of period (Week, Month, Year)
            connection_id: Specific connection ID (optional)
        
        Returns:
            Dictionary containing cashflow data for all connections
        """
        # Calculate date ranges
        date_ranges = calculate_date_ranges(report_date, period, period_of)
        
        # Get connections
        if connection_id:
            connections = [self.xero_auth_service.get_connection(connection_id)]
        else:
            connections = self.xero_auth_service.get_all_connections()
        
        if not connections:
            raise ValueError("No active Xero connections found")
        
        cashflow_data = {}
        
        # Process each connection
        for connection in connections:
            try:
                connection_data = self._process_connection(
                    connection, date_ranges, report_date
                )
                cashflow_data[connection.tenant_name] = connection_data
            except Exception as e:
                print(f"[CASHFLOW] Error processing connection {connection.tenant_name}: {str(e)}")
                # Continue with other connections even if one fails
                continue
        
        return cashflow_data
    
    def _process_connection(
        self, 
        connection: XeroConnection, 
        date_ranges: List[Tuple[str, str]], 
        report_date: str
    ) -> Dict[str, Any]:
        """
        Process a single connection to get cashflow data.
        
        Args:
            connection: Xero connection object
            date_ranges: List of date ranges
            report_date: Report date
        
        Returns:
            Dictionary containing connection's cashflow data
        """
        # Create API client
        accounting_api = create_xero_api_client(connection, str(connection.tenant_id), self.xero_auth_service)
        finance_api = FinanceApi(accounting_api.api_client)
        
                # Get bank accounts
        bank_accounts = self._get_bank_accounts(accounting_api, str(connection.tenant_id))
        
        # Filter for ASB and ANZ accounts
        filtered_accounts = filter_bank_accounts(bank_accounts)
        
        connection_data = {
            "accounts": []
        }
        
        # Process each bank account
        for account in filtered_accounts:
            account_data = self._process_bank_account(
                account, finance_api, str(connection.tenant_id), date_ranges, report_date
            )
            connection_data["accounts"].append(account_data)
        
        return connection_data
    
    def _get_bank_accounts(self, accounting_api: AccountingApi, tenant_id: str) -> List[Any]:
        """
        Get bank accounts from Xero.
        
        Args:
            accounting_api: Xero Accounting API client
            tenant_id: Xero tenant ID
        
        Returns:
            List of bank account objects
        """
        try:
            # Get accounts with filter for bank accounts
            accounts_response = accounting_api.get_accounts(
                tenant_id,
                empty,  # if_modified_since
                "BankAccountType == \"BANK\" AND Status == \"ACTIVE\"",  # where
            )
            return accounts_response.accounts
        except Exception as e:
            print(f"[CASHFLOW] Error getting bank accounts: {str(e)}")
            return []
    
    def _process_bank_account(
        self, 
        account: Any, 
        finance_api: FinanceApi, 
        tenant_id: str,
        date_ranges: List[Tuple[str, str]], 
        report_date: str
    ) -> Dict[str, Any]:
        """
        Process a single bank account to get balance data for all periods.
        
        Args:
            account: Bank account object
            finance_api: Xero Finance API client
            date_ranges: List of date ranges
            report_date: Report date
        
        Returns:
            Dictionary containing account's balance data for all periods
        """
        account_data = {
            "account_id": getattr(account, 'account_id', ''),
            "account_number": getattr(account, 'bank_account_number', ''),
            "account_name": getattr(account, 'name', ''),
            "bank_name": getattr(account, 'bank_name', ''),
            "periods": {}
        }
        
        # Get balance data for each date range
        for start_date, end_date in date_ranges:
            try:
                period_data = self._get_bank_statement_data(
                    finance_api, tenant_id, account.account_id, start_date, end_date
                )
                period_key = f"{start_date}_{end_date}"
                account_data["periods"][period_key] = period_data
            except Exception as e:
                print(f"[CASHFLOW] Error getting statement for account {account.account_id} period {start_date}-{end_date}: {str(e)}")
                # Set default values if API call fails
                period_key = f"{start_date}_{end_date}"
                account_data["periods"][period_key] = {
                    "opening_balance": 0,
                    "closing_balance": 0
                }
        
        return account_data
    
    def _get_bank_statement_data(
        self, 
        finance_api: FinanceApi, 
        tenant_id: str,
        account_id: str, 
        start_date: str, 
        end_date: str
    ) -> Dict[str, float]:
        """
        Get bank statement data for a specific account and date range.
        
        Args:
            finance_api: Xero Finance API client
            account_id: Bank account ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        
        Returns:
            Dictionary containing opening and closing balances
        """
        try:
            # Get bank statement using finance API
            statement_response = finance_api.get_bank_statement_accounting(
                tenant_id,      # xero_tenant_id
                account_id,     # bank_account_id
                start_date,     # from_date
                end_date,       # to_date
                "True"          # summary_only
            )
            
            # Extract balance data from response
            opening_balance = 0
            closing_balance = 0
            
            if statement_response and hasattr(statement_response, 'statements'):
                statements = statement_response.statements
                if statements:
                    # Get the first statement for opening balance
                    first_statement = statements[0]
                    opening_balance = getattr(first_statement, 'start_balance', 0)
                    
                    # Get the last statement for closing balance
                    last_statement = statements[-1]
                    closing_balance = getattr(last_statement, 'end_balance', 0)
            
            return {
                "opening_balance": float(opening_balance),
                "closing_balance": float(closing_balance)
            }
            
        except Exception as e:
            print(f"[CASHFLOW] Error getting bank statement for account {account_id}: {str(e)}")
            return {
                "opening_balance": 0,
                "closing_balance": 0
            }
