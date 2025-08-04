from typing import Dict, Any, List, Tuple
from datetime import datetime
from xero_python.accounting.api.accounting_api import AccountingApi, empty
from xero_python.finance.api.finance_api import FinanceApi
from xero_python.api_client import ApiClient
from app.util.token_manager import TokenManager

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
        self.token_manager = TokenManager(xero_auth_service)
    
    @classmethod
    def get_service_dependency(cls):
        """FastAPI dependency function for XeroCashFlowService"""
        from fastapi import Depends
        from app.services.xero_auth import XeroAuthService
        
        def _get_service(xero_auth_service: XeroAuthService = Depends(XeroAuthService.get_service_dependency())) -> XeroCashFlowService:
            return cls(xero_auth_service)
        
        return _get_service
    
    async def get_cashflow_data(
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
        errors = []
        
        # Process each connection
        for connection in connections:
            try:
                connection_data = await self._process_connection(
                    connection, date_ranges, report_date
                )
                cashflow_data[connection.tenant_name] = connection_data
            except Exception as e:
                error_msg = f"Error processing connection {connection.tenant_name}: {str(e)}"
                print(f"[CASHFLOW] {error_msg}")
                errors.append({
                    "connection_name": connection.tenant_name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                # Continue with other connections even if one fails
                continue
        
        return {
            "data": cashflow_data,
            "errors": errors
        }
    
    async def _process_connection(
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

        # Ensure we have a valid token before making API calls
        connection = await self.token_manager.ensure_valid_token(connection, connection.tenant_id, connection.app_id)

        # Create API client
        accounting_api = create_xero_api_client(connection, str(connection.tenant_id), self.xero_auth_service)
        
        connection_data = {
            "accounts": []
        }
        
        # Get bank summary data for each date range
        for start_date, end_date in date_ranges:
            try:
                bank_summary_data = self._get_bank_summary_data(
                    accounting_api, str(connection.tenant_id), start_date, end_date
                )
                
                # Process each account in the summary
                for account_id, account_data in bank_summary_data.items():
                    # Check if this account is ASB or ANZ by getting account details
                    account_details = self._get_account_details(accounting_api, str(connection.tenant_id), account_id)
                    
                    if account_details and self._is_supported_bank_account(account_details):
                        # Add period data to existing account or create new one
                        self._add_period_data_to_connection(connection_data, account_details, account_data, start_date, end_date)
                        
            except Exception as e:
                print(f"[CASHFLOW] Error processing period {start_date}-{end_date}: {str(e)}")
                continue
        
        return connection_data
    

    
    def _get_bank_summary_data(
        self, 
        accounting_api: AccountingApi, 
        tenant_id: str,
        start_date: str, 
        end_date: str
    ) -> Dict[str, Any]:
        """
        Get bank summary report data for a specific date range.
        
        Args:
            accounting_api: Xero Accounting API client
            tenant_id: Xero tenant ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        
        Returns:
            Dictionary containing bank summary data
        """
        try:
            from datetime import datetime
            
            # Convert string dates to datetime objects
            from_date = datetime.strptime(start_date, "%Y-%m-%d")
            to_date = datetime.strptime(end_date, "%Y-%m-%d")
            
            # Get bank summary report
            report_response = accounting_api.get_report_bank_summary(
                tenant_id,
                from_date,
                to_date
            )

            bank_data = {}
            
            if report_response and hasattr(report_response, 'reports') and report_response.reports:
                report = report_response.reports[0]
                
                if hasattr(report, 'rows') and report.rows:
                    for row in report.rows:
                        # Handle Section rows that contain the actual bank account data
                        if hasattr(row, 'row_type') and row.row_type.value == "Section" and hasattr(row, 'rows') and row.rows:
                            for sub_row in row.rows:
                                if hasattr(sub_row, 'row_type') and sub_row.row_type.value == "Row" and hasattr(sub_row, 'cells') and sub_row.cells:
                                    # Extract account data from sub_row
                                    account_name = ""
                                    account_id = ""
                                    opening_balance = 0
                                    cash_received = 0
                                    cash_spent = 0
                                    closing_balance = 0
                                    
                                    if len(sub_row.cells) >= 5:
                                        # Account name and ID
                                        if sub_row.cells[0].attributes:
                                            for attr in sub_row.cells[0].attributes:
                                                if attr.id == "accountID":
                                                    account_id = attr.value
                                                    break
                                        account_name = sub_row.cells[0].value
                                        
                                        # Balances
                                        opening_balance = float(sub_row.cells[1].value or 0)
                                        cash_received = float(sub_row.cells[2].value or 0)
                                        cash_spent = float(sub_row.cells[3].value or 0)
                                        closing_balance = float(sub_row.cells[4].value or 0)
                                        
                                        # Get account details to check if it's ASB or ANZ
                                        if account_id:
                                            try:
                                                account_details = self._get_account_details(accounting_api, tenant_id, account_id)
                                                if self._is_supported_bank_account(account_details):
                                                    bank_data[account_id] = {
                                                        'account_name': account_name,
                                                        'bank_name': getattr(account_details, 'bank_name', ''),
                                                        'opening_balance': opening_balance,
                                                        'cash_received': cash_received,
                                                        'cash_spent': cash_spent,
                                                        'closing_balance': closing_balance
                                                    }
                                            except Exception as e:
                                                print(f"[CASHFLOW] Error getting account details for {account_id}: {e}")
                        
                        # Handle direct Row rows (fallback)
                        elif hasattr(row, 'row_type') and row.row_type.value == "Row" and hasattr(row, 'cells') and row.cells:
                            # Extract account data from row
                            account_name = ""
                            account_id = ""
                            opening_balance = 0
                            cash_received = 0
                            cash_spent = 0
                            closing_balance = 0
                            
                            for i, cell in enumerate(row.cells):
                                if i == 0:  # Bank account name
                                    account_name = getattr(cell, 'value', '')
                                    # Get account ID from attributes
                                    if hasattr(cell, 'attributes') and cell.attributes:
                                        for attr in cell.attributes:
                                            if hasattr(attr, 'id') and attr.id == "accountID":
                                                account_id = getattr(attr, 'value', '')
                                elif i == 1:  # Opening balance
                                    opening_balance = float(getattr(cell, 'value', '0'))
                                elif i == 2:  # Cash received
                                    cash_received = float(getattr(cell, 'value', '0'))
                                elif i == 3:  # Cash spent
                                    cash_spent = float(getattr(cell, 'value', '0'))
                                elif i == 4:  # Closing balance
                                    closing_balance = float(getattr(cell, 'value', '0'))
                            
                            if account_id:
                                bank_data[account_id] = {
                                    "account_name": account_name,
                                    "opening_balance": opening_balance,
                                    "cash_received": cash_received,
                                    "cash_spent": cash_spent,
                                    "closing_balance": closing_balance
                                }
            
            print(f"[CASHFLOW] Final bank_data: {bank_data}")
            return bank_data
            
        except Exception as e:
            print(f"[CASHFLOW] Error getting bank summary for period {start_date}-{end_date}: {str(e)}")
            return {}
    
    def _get_account_details(self, accounting_api: AccountingApi, tenant_id: str, account_id: str) -> Any:
        """
        Get account details by account ID.
        
        Args:
            accounting_api: Xero Accounting API client
            tenant_id: Xero tenant ID
            account_id: Account ID
        
        Returns:
            Account object or None
        """
        try:
            account_response = accounting_api.get_account(tenant_id, account_id)
            if account_response and hasattr(account_response, 'accounts') and account_response.accounts:
                return account_response.accounts[0]
            return None
        except Exception as e:
            print(f"[CASHFLOW] Error getting account details for {account_id}: {str(e)}")
            return None
    
    def _is_supported_bank_account(self, account: Any) -> bool:
        """
        Check if account is ASB, ANZ, BNZ, ICBC, CCB/BOC, Kiwi Bank, or Hua Xia Bank.
        
        Supported banks:
        - ASB: account numbers starting with 12
        - ANZ: account numbers starting with 01 or 06
        - BNZ: account numbers starting with 02
        - ICBC: account numbers starting with 10
        - CCB/BOC: account numbers starting with 88
        - Kiwi Bank: account numbers starting with 38
        - Hua Xia Bank: account numbers starting with 17
        
        Args:
            account: Account object
        
        Returns:
            True if supported bank account, False otherwise
        """
        account_number = getattr(account, 'bank_account_number', '')
        
        # ASB bank: account number starts with 12
        if account_number.startswith('12'):
            setattr(account, 'bank_name', 'ASB')
            return True
        # ANZ bank: account number starts with 01 or 06
        elif account_number.startswith('01') or account_number.startswith('06'):
            setattr(account, 'bank_name', 'ANZ')
            return True
        # BNZ bank: account number starts with 02
        elif account_number.startswith('02'):
            setattr(account, 'bank_name', 'BNZ')
            return True
        # ICBC bank: account number starts with 10
        elif account_number.startswith('10'):
            setattr(account, 'bank_name', 'ICBC')
            return True
        # Hua Xia Bank: account number starts with 17
        elif account_number.startswith('17'):
            setattr(account, 'bank_name', 'Hua Xia Bank')
            return True
        # CCB/BOC bank: account number starts with 88
        elif account_number.startswith('88'):
            setattr(account, 'bank_name', 'CCB / BOC')
            return True
        # Kiwi Bank: account number starts with 38
        elif account_number.startswith('38'):
            setattr(account, 'bank_name', 'Kiwi Bank')
            return True

        
        return False
    
    def _add_period_data_to_connection(self, connection_data: Dict[str, Any], account_details: Any, 
                                      period_data: Dict[str, Any], start_date: str, end_date: str):
        """
        Add period data to connection data structure.
        
        Args:
            connection_data: Connection data dictionary
            account_details: Account details object
            period_data: Period data from bank summary
            start_date: Start date
            end_date: End date
        """
        account_id = getattr(account_details, 'account_id', '')
        account_number = getattr(account_details, 'bank_account_number', '')
        bank_name = getattr(account_details, 'bank_name', '')
        
        # Find existing account or create new one
        existing_account = None
        for account in connection_data["accounts"]:
            if account["account_id"] == account_id:
                existing_account = account
                break
        
        if not existing_account:
            # Create new account entry
            existing_account = {
                "account_id": account_id,
                "account_number": account_number,
                "account_name": getattr(account_details, 'name', ''),
                "bank_name": bank_name,
                "periods": {}
            }
            connection_data["accounts"].append(existing_account)
        
        # Add period data
        period_key = f"{start_date}_{end_date}"
        existing_account["periods"][period_key] = {
            "opening_balance": period_data.get("opening_balance", 0),
            "cash_received": period_data.get("cash_received", 0),
            "cash_spent": period_data.get("cash_spent", 0),
            "closing_balance": period_data.get("closing_balance", 0)
        }
