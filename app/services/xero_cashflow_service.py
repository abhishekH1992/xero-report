from typing import Dict, Any, List, Tuple
from datetime import datetime
from xero_python.accounting.api.accounting_api import AccountingApi, empty
from app.util.token_manager import TokenManager

from app.util.xero_connection import create_xero_api_client
from app.util.report_helper import (
    calculate_date_ranges
)
from app.services.xero_auth import XeroAuthService
from app.database.models import XeroConnection
from app.util.db_session_manager import DatabaseSessionManager
from app.util.export.report_cashflow_export import export_cashflow_to_excel, generate_cashflow_json_response
from fastapi import HTTPException


class XeroCashFlowService:
    """Service for generating CashFlow reports from Xero data."""
    
    def __init__(self, xero_auth_service: XeroAuthService):
        self.xero_auth_service = xero_auth_service
        self.token_manager = TokenManager(xero_auth_service)
        self.session_manager = DatabaseSessionManager()
    
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
        connection_ids: str = None
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

        # Use session manager like aged receivables
        with self.session_manager.get_session() as session:
            try:
                connections = []
                
                # Get connections
                if connection_ids:
                    connection_ids = [cid.strip() for cid in connection_ids.split(',')]
                    for cid in connection_ids:
                        connection = self.xero_auth_service.get_connection(cid)
                        if connection:
                            connections.append(connection)
                        else:
                            print(f"[CASHFLOW] Connection with ID {cid} was not found in the database")
                            continue
                else:
                    # Get all connections and filter for app 1 only
                    all_connections = self.xero_auth_service.get_all_connections()
                    connections = [
                        conn for conn in all_connections 
                        if conn.business_type not in ["Project", "Stonewood Developments"]
                    ]
                
                if not connections:
                    raise ValueError("No active Xero connections found")
                
                cashflow_data = {}
                errors = []
                
                # Process each connection
                for connection in connections:
                    try:
                        connection_data = await self._process_connection(
                            connection, date_ranges
                        )
                        # Include connection_id in the data structure
                        connection_data['connection_id'] = connection.tenant_id
                        cashflow_data[connection.tenant_name] = connection_data
                    except Exception as e:
                        error_msg = f"Error processing connection {connection.tenant_name}: {str(e)}"
                        print(f"[CASHFLOW] {error_msg}")
                        errors.append({
                            "connection_name": connection.tenant_name,
                            "connection_id": connection.id,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        })
                        # Continue with other connections even if one fails
                        continue
                
                return {
                    "data": cashflow_data,
                    "errors": errors
                }
                
            except Exception as e:
                # Session will automatically rollback on exception
                print(f"[CASHFLOW] Error in main method: {str(e)}")
                raise
            # Session automatically closes here
    
    async def _process_connection(
        self, 
        connection: XeroConnection, 
        date_ranges: List[Tuple[str, str]],
    ) -> Dict[str, Any]:
        """
        Process a single connection to get cashflow data.
        
        Args:
            connection: Xero connection object
            date_ranges: List of date ranges
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
        for key, (start_date, end_date) in enumerate(date_ranges):
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
                        self._add_period_data_to_connection(
                            connection_data, 
                            account_details, 
                            account_data, 
                            start_date, 
                            end_date, 
                            accounting_api,
                            str(connection.tenant_id),
                            connection.id,
                            key
                        )
                            
                        
            except Exception as e:
                print(f"[CASHFLOW] Error processing period {start_date}-{end_date}: {str(e)}")
                continue
        
        # Calculate final totals and summaries
        # final_totals = self._calculate_final_totals(connection_data)
        final_totals = {}
        connection_data["final_totals"] = final_totals
        
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
            
            # Accounts to exclude from calculations
            excluded_accounts = ["389026059757103", "389026059757102"]
            
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
                                                if account_details:
                                                    # Get account number for exclusion check
                                                    account_number = getattr(account_details, 'bank_account_number', '')
                                                    
                                                    # Skip excluded accounts
                                                    if account_number in excluded_accounts:
                                                        continue
                                                    
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
                                # For fallback case, we need to get account details to check account number
                                try:
                                    account_details = self._get_account_details(accounting_api, tenant_id, account_id)
                                    if account_details:
                                        # Get account number for exclusion check
                                        account_number = getattr(account_details, 'bank_account_number', '')
                                        
                                        # Skip excluded accounts
                                        if account_number in excluded_accounts:
                                            continue
                                        
                                        bank_data[account_id] = {
                                            "account_name": account_name,
                                            "opening_balance": opening_balance,
                                            "cash_received": cash_received,
                                            "cash_spent": cash_spent,
                                            "closing_balance": closing_balance
                                        }
                                except Exception as e:
                                    print(f"[CASHFLOW] Error getting account details for {account_id} in fallback: {e}")
            
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
            # Separate CCB and BOC based on account number prefix
            if account_number.startswith('8888'):
                setattr(account, 'bank_name', 'BOC')
            elif account_number.startswith('8886'):
                setattr(account, 'bank_name', 'CCB')
            else:
                setattr(account, 'bank_name', 'CCB / BOC')
            return True
        # Kiwi Bank: account number starts with 38
        elif account_number.startswith('38'):
            setattr(account, 'bank_name', 'Kiwi Bank')
            return True

        
        return False
    
    def _add_period_data_to_connection(self, connection_data: Dict[str, Any], account_details: Any, 
                                      period_data: Dict[str, Any], start_date: str, end_date: str, 
                                      accounting_api: AccountingApi, tenant_id: str, connection_db_id: int, key: int):
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
                "periods": {},
                "spent": {},
                "received": {}
                # Do NOT initialize spent/received here - they will be added only for key == 0
            }
            connection_data["accounts"].append(existing_account)
        
        # Add period data
        period_key = f"{start_date}_{end_date}"
        period_info = {
            "opening_balance": period_data.get("opening_balance", 0),
            "cash_received": period_data.get("cash_received", 0),
            "cash_spent": period_data.get("cash_spent", 0),
            "closing_balance": period_data.get("closing_balance", 0)
        }
        
        if key == 0:
            # Only for the most recent period: collect transaction data and add spent/received
            bank_transaction_data = self._get_bank_transaction_data(
                accounting_api, tenant_id, account_id, start_date, end_date, connection_db_id
            )
            period_info["spent"] = bank_transaction_data.get("spent", {})
            period_info["received"] = bank_transaction_data.get("received", {})
                
            # Also set the account-level spent/received for the first time
            existing_account["spent"] = bank_transaction_data.get("spent", {})
            existing_account["received"] = bank_transaction_data.get("received", {})
        else:
            # For older periods (key > 0): ensure NO spent/received fields exist
            # This ensures older periods are completely clean
            pass
        
        existing_account["periods"][period_key] = period_info


    def _get_bank_transaction_data(self, accounting_api: AccountingApi, tenant_id: str, account_id: str, start_date: str, end_date: str, connection_db_id: int) -> Dict[str, Any]:
        """
        Get bank transaction and payment data for a specific date range.
        
        Args:
            accounting_api: Xero Accounting API client
            tenant_id: Xero tenant ID
            account_id: Account ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            connection_db_id: Database connection ID
            
        Returns:
            Dictionary with spent and received categories
        """
        try:
            # 1.1. Get all bank transactions for the account
            all_transactions = self._get_all_bank_transactions_for_account(
                accounting_api, tenant_id, account_id, start_date, end_date
            )
            
            # 1.2. Get all payments for the account
            all_payments = self._get_all_payments_for_account(
                accounting_api, tenant_id, account_id, start_date, end_date
            )
            
            # 1.3. Get specific bank transaction details with line items
            detailed_transactions = self._get_detailed_bank_transactions(
                accounting_api, tenant_id, all_transactions
            )
            
            # 1.4. Get specific payment details with line items
            detailed_payments = self._get_detailed_payments(
                accounting_api, tenant_id, all_payments, connection_db_id, start_date, end_date
            )
            
            # 1.5. Merge and categorize all transactions and payments
            all_line_items = detailed_transactions + detailed_payments
            
            # Get both simple and subcategorized data
            categorized_data = self.get_categorized_cashflow(all_line_items, connection_db_id)
            
            # Write debug data to JSON
            # with open("simple_categorized_debug.json", "w") as f:
            #     import json
            #     json.dump(categorized_data, f, indent=2, default=str)
            
            return categorized_data
            
        except Exception as e:
            print(f"[CASHFLOW] Error getting transaction data: {str(e)}")
            # return self._get_empty_categories()
            return {}

    def _get_all_bank_transactions_for_account(
        self, 
        accounting_api: AccountingApi, 
        tenant_id: str, 
        account_id: str,
        start_date: str, 
        end_date: str
    ) -> List[Any]:
        """
        Get all bank transactions for a specific account and date range.
        
        Args:
            accounting_api: Xero accounting API client
            tenant_id: Xero tenant ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of bank transactions
        """
        # Convert dates to Xero format
        start_date_xero = f"DateTime({start_date.replace('-', ',')})"
        end_date_xero = f"DateTime({end_date.replace('-', ',')})"
        
        # Build where clause and include specific bank account filter
        where_clause = (
            f'Date >= {start_date_xero} && Date <= {end_date_xero} && '
            f'Status == "AUTHORISED" && BankAccount.AccountID == Guid("{account_id}")'
        )
        
        try:
            all_transactions: List[Any] = []
            page = 1
            page_size = 1000
            
            while True:
                response = accounting_api.get_bank_transactions(
                    tenant_id,
                    empty,              # if_modified_since
                    where_clause,       # where
                    "Date ASC",        # order
                    page,               # page
                    empty,              # unitdp
                    page_size           # page_size
                )
                
                batch = getattr(response, 'bank_transactions', None) or []
                if not batch:
                    break
                
                all_transactions.extend(batch)
                
                if len(batch) < page_size:
                    break
                
                page += 1
            
            return all_transactions
            
        except Exception as e:
            print(f"[CASHFLOW] Error fetching bank transactions: {str(e)}")
            return []

    def _get_all_payments_for_account(
        self, 
        accounting_api: AccountingApi, 
        tenant_id: str, 
        account_id: str,
        start_date: str, 
        end_date: str
    ) -> List[Any]:
        """
        Get all payments for a specific account and date range.
        
        Args:
            accounting_api: Xero accounting API client
            tenant_id: Xero tenant ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of payments
        """
        # Convert dates to Xero format
        start_date_xero = f"DateTime({start_date.replace('-', ',')})"
        end_date_xero = f"DateTime({end_date.replace('-', ',')})"
        
        # Build where clause and include specific bank account filter
        where_clause = (
            f'Date >= {start_date_xero} && Date <= {end_date_xero} && '
            f'Status == "AUTHORISED" && Account.AccountID == Guid("{account_id}")'
        )
        
        try:
            all_payments: List[Any] = []
            page = 1
            page_size = 1000
            
            while True:
                response = accounting_api.get_payments(
                    tenant_id,
                    empty,              # if_modified_since
                    where_clause,       # where
                    "Date ASC",        # order
                    page,               # page
                    empty,              # unitdp
                    page_size           # page_size
                )
                
                batch = getattr(response, 'payments', None) or []
                if not batch:
                    break
                
                all_payments.extend(batch)
                
                if len(batch) < page_size:
                    break
                
                page += 1
            
            return all_payments
            
        except Exception as e:
            print(f"[CASHFLOW] Error fetching payments: {str(e)}")
            return []

    def _get_detailed_bank_transactions(
        self, 
        accounting_api: AccountingApi, 
        tenant_id: str, 
        transactions: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Get detailed line items for each bank transaction.
        
        Args:
            accounting_api: Xero accounting API client
            tenant_id: Xero tenant ID
            transactions: List of bank transactions
            
        Returns:
            List of detailed transactions with line items
        """
        detailed_transactions = []
        
        for transaction in transactions:
            try:
                # Get specific bank transaction details
                detailed_transaction = accounting_api.get_bank_transaction(
                    tenant_id,
                    transaction.bank_transaction_id
                )
                
                if detailed_transaction and detailed_transaction.bank_transactions:
                    transaction_detail = detailed_transaction.bank_transactions[0]
                    
                    # Extract line items
                    line_items = []
                    if transaction_detail.line_items:
                        for i, line_item in enumerate(transaction_detail.line_items):
                            line_items.append({
                                "type": transaction.type,
                                "accountCode": line_item.account_code,
                                "unitAmount": float(line_item.unit_amount or 0.0),
                                "quantity": float(line_item.quantity or 1.0),
                                "lineAmount": float(line_item.line_amount or 0.0),
                                "description": line_item.description or "",
                                "taxAmount": float(line_item.tax_amount or 0.0)
                            })
                    else:
                        # If no line items, create a default line item using the transaction's account code
                        # This happens when bank transactions don't have detailed line items
                        # Try to get account code from the bank account
                        account_code = getattr(transaction_detail.bank_account, 'code', '') if hasattr(transaction_detail, 'bank_account') else ''
                        if account_code:
                            line_items.append({
                                "type": transaction.type,
                                "accountCode": account_code,
                                "unitAmount": float(transaction_detail.total or 0.0),
                                "quantity": 1.0,
                                "lineAmount": float(transaction_detail.total or 0.0),
                                "description": f"Bank transaction {transaction_detail.type}",
                                "taxAmount": 0.0
                            })
                    
                    detailed_transactions.append({
                        "transaction_id": transaction.bank_transaction_id,
                        "type": transaction.type,
                        "total": transaction.total or 0.0,
                        "lineItems": line_items
                    })
                    
            except Exception as e:
                print(f"[CASHFLOW] Error getting detailed transaction {transaction.bank_transaction_id}: {str(e)}")
                continue
        
        return detailed_transactions

    def _get_detailed_payments(self, accounting_api: AccountingApi, tenant_id: str, payments: List, connection_db_id: str, report_start_date: str = None, report_end_date: str = None) -> List[Dict]:
        """
        Get detailed line items for payments
        
        Args:
            accounting_api: Xero Accounting API client
            tenant_id: Xero tenant ID
            payments: List of payments to process
            connection_db_id: Database connection ID
            report_start_date: Report start date (YYYY-MM-DD) for filtering
            report_end_date: Report end date (YYYY-MM-DD) for filtering
        """
        detailed_payments = []
        
        # Convert report dates to datetime for comparison
        from datetime import datetime
        start_date = None
        end_date = None
        if report_start_date and report_end_date:
            start_date = datetime.strptime(report_start_date, "%Y-%m-%d")
            end_date = datetime.strptime(report_end_date, "%Y-%m-%d")
        
        for payment in payments:
            try:
                payment_detail = accounting_api.get_payment(
                    tenant_id,
                    payment.payment_id
                )
                
                # Extract line items from the invoice, not from payment directly
                line_items = []
                
                # Handle the case where payment_detail might be a list or have a different structure
                if hasattr(payment_detail, 'payments') and payment_detail.payments:
                    # If it's a list of payments, take the first one
                    payment = payment_detail.payments[0]
                else:
                    payment = payment_detail
                
                # Check if payment has an invoice with line items
                if hasattr(payment, 'invoice') and payment.invoice:
                    # Filter out payments for old invoices that are outside the report period
                    if start_date and end_date:
                        invoice_date_str = getattr(payment.invoice, 'date_string', None)
                        if invoice_date_str:
                            try:
                                # Parse invoice date (format: "2025-07-01T00:00:00")
                                invoice_date = datetime.strptime(invoice_date_str.split('T')[0], "%Y-%m-%d")
                                
                                # Skip payments for invoices that are outside the report period
                                if invoice_date < start_date or invoice_date > end_date:
                                    continue
                                    
                            except (ValueError, AttributeError) as e:
                                print(f"[CASHFLOW] Warning: Could not parse invoice date for payment {payment.payment_id}: {e}")
                                # Continue processing if we can't parse the date
                    
                    if hasattr(payment.invoice, 'line_items') and payment.invoice.line_items:
                        for line_item in payment.invoice.line_items:
                            line_items.append({
                                "accountCode": line_item.account_code if hasattr(line_item, 'account_code') else payment.account.code if hasattr(payment, 'account') and payment.account else "Unknown",
                                "unitAmount": float(line_item.unit_amount) if hasattr(line_item, 'unit_amount') and line_item.unit_amount else 0.0,
                                "quantity": float(line_item.quantity) if hasattr(line_item, 'quantity') and line_item.quantity else 1.0,
                                "lineAmount": float(line_item.line_amount) if hasattr(line_item, 'line_amount') and line_item.line_amount else 0.0,
                                "description": line_item.description if hasattr(line_item, 'description') else "Payment",
                                "taxAmount": float(line_item.tax_amount) if hasattr(line_item, 'tax_amount') and line_item.tax_amount else 0.0
                            })
                    else:
                        # Fallback: create a default line item using payment details
                        account_code = payment.account.code if hasattr(payment, 'account') and payment.account else "Unknown"
                        line_items.append({
                            "accountCode": account_code,
                            "unitAmount": float(payment.amount) if hasattr(payment, 'amount') and payment.amount else 0.0,
                            "quantity": 1.0,
                            "lineAmount": float(payment.amount) if hasattr(payment, 'amount') and payment.amount else 0.0,
                            "description": "Payment",
                            "taxAmount": 0.0
                        })
                
                if line_items:
                    detailed_payments.append({
                        "transaction_id": payment.payment_id,
                        "type": payment.payment_type,
                        "total": payment.amount if hasattr(payment, 'amount') else 0.0,
                        "lineItems": line_items
                    })
                    
            except Exception as e:
                print(f"[CASHFLOW] Error getting detailed payment {payment.payment_id}: {e}")
                continue
                
        return detailed_payments

    def _simple_categorize_spend_received(self, all_line_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Simple categorization: just separate into spend vs received based on payment types.
        No subcategories yet - just the basic separation.
        """
        # Initialize simple structure
        simple_categorized = {
            "spent": {
                "total": 0.0,
                "data": []
            },
            "received": {
                "total": 0.0,
                "data": []
            }
        }
        
        # Payment types that indicate money going OUT (spent)
        spend_payment_types = {
            "SPEND",
            "ACCPAYPAYMENT",
            "APCREDITPAYMENT",
            "APPREPAYMENTPAYMENT",
            "APOVERPAYMENTPAYMENT",
            "ARCREDITPAYMENT",
            "SPEND-OVERPAYMENT",
            "SPEND-PREPAYMENT",
            "SPEND-TRANSFER",
        }
        
        # Payment types that indicate money coming IN (received)
        received_payment_types = {
            "RECEIVE",
            "ACCRECPAYMENT",
            "AROVERPAYMENTPAYMENT",
            "ARPREPAYMENTPAYMENT",
            "RECEIVE-TRANSFER",
            "RECEIVE-OVERPAYMENT",
            "RECEIVE-PREPAYMENT",

        }
        
        for item in all_line_items:
            item_type = item.get("type", "")
            item_total = float(item.get("total", 0.0))
            
            # Categorize based on payment type
            if item_type in spend_payment_types:
                # This is money going OUT (spent)
                simple_categorized["spent"]["total"] += item_total
                
                # Clean line items and handle proportional distribution if needed
                clean_line_items = self._process_line_items_with_distribution(item.get("lineItems", []), item_total)
                
                simple_categorized["spent"]["data"].append({
                    "transaction_id": item["transaction_id"],
                    "type": item_type,
                    "total": item_total,
                    "lineItems": clean_line_items
                })
                
            elif item_type in received_payment_types:
                # This is money coming IN (received)
                simple_categorized["received"]["total"] += item_total
                
                # Clean line items and handle proportional distribution if needed
                clean_line_items = self._process_line_items_with_distribution(item.get("lineItems", []), item_total)
                
                simple_categorized["received"]["data"].append({
                    "transaction_id": item["transaction_id"],
                    "type": item_type,
                    "total": item_total,
                    "lineItems": clean_line_items
                })
                
            else:
                # Unknown payment type - need to investigate
                # For now, add to spent as default
                simple_categorized["spent"]["total"] += item_total
                
                # Clean line items and handle proportional distribution if needed
                clean_line_items = self._process_line_items_with_distribution(item.get("lineItems", []), item_total)
                
                simple_categorized["spent"]["data"].append({
                    "transaction_id": item["transaction_id"],
                    "type": item_type,
                    "total": item_total,
                    "lineItems": clean_line_items,
                    "note": "Unknown payment type - defaulted to spent"
                })
        
        return simple_categorized

    def get_categorized_cashflow(self, all_line_items: List[Dict[str, Any]], connection_id: int) -> Dict[str, Any]:
        """
        Get both simple and subcategorized cashflow data.
        
        Args:
            all_line_items: List of all line items from transactions and payments
            connection_id: The database connection ID
            
        Returns:
            Dictionary containing both simple and subcategorized data
        """
        # Get simple categorization first
        simple_categorized = self._simple_categorize_spend_received(all_line_items)
        
        # Then apply subcategory mapping
        subcategorized = self._categorize_to_subcategories(simple_categorized, connection_id)
        
        return subcategorized

    def _get_account_mappings(self, connection_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Get account code mappings from database for a specific connection.
        
        Args:
            connection_id: The database connection ID
            
        Returns:
            Dictionary mapping account codes to their category information
        """
        try:
            from app.database.models import XeroAccount, XeroCategory
            
            # Use session manager for database operations
            with self.session_manager.get_session() as session:
                accounts = session.query(
                    XeroAccount.account_code,
                    XeroAccount.connection_id,
                    XeroCategory.name,
                    XeroCategory.type
                ).join(
                    XeroCategory, XeroAccount.category_id == XeroCategory.id
                ).filter(
                    XeroAccount.connection_id == connection_id
                ).all()
                
                # Create mapping: account_code -> category info
                account_mappings = {}
                for account in accounts:
                    account_mappings[account.account_code] = {
                        "name": account.name,
                        "type": account.type,
                    }
                
                return account_mappings
                
        except Exception as e:
            print(f"[CASHFLOW] Error getting account mappings: {e}")
            return {}

    def _categorize_to_subcategories(self, simple_categorized: Dict[str, Any], connection_id: int) -> Dict[str, Any]:
        """
        Categorize transactions into subcategories based on account codes and database categories.
        
        Args:
            simple_categorized: The simple categorized data
            connection_id: The database connection ID
            
        Returns:
            Data categorized into subcategories
        """
        # Get account mappings from database
        account_mappings = self._get_account_mappings(connection_id)
        
        # Initialize subcategory structure with totals
        subcategorized = {
            "spent": {
                "gst_payment": {"total": 0.0, "data": []},
                "interest_payment": {"total": 0.0, "data": []},
                "loan_payment": {"total": 0.0, "data": []},
                "payroll": {"total": 0.0, "data": []},
                "rates": {"total": 0.0, "data": []},
                "others": {"total": 0.0, "data": []},
                "gst_refund": {"total": 0.0, "data": []}
            },
            "received": {
                "gst_refund": {"total": 0.0, "data": []},
                "income": {"total": 0.0, "data": []},
                "rental_income": {"total": 0.0, "data": []}
            }
        }
        
        # Process spent transactions
        for transaction in simple_categorized.get("spent", {}).get("data", []):
            # Split transaction based on line items and their distributed amounts
            for line_item in transaction.get("lineItems", []):
                account_code = line_item.get("accountCode")
                if not account_code:
                    continue
                
                category_info = account_mappings.get(account_code, {})
                category_name = (category_info.get("name") or "").lower()
                category_type = (category_info.get("type") or "").lower()
                
                # Use distributedAmount if available, otherwise use transaction total
                # For spent transactions, we need to calculate the amount for this line item
                if "distributedAmount" in line_item:
                    amount_for_category = line_item.get("distributedAmount", 0.0)
                else:
                    # If no distributedAmount, calculate proportionally from transaction total
                    transaction_total = float(transaction.get("total", 0.0))
                    line_amount = float(line_item.get("lineAmount", 0.0))
                    total_line_amounts = sum(float(li.get("lineAmount", 0.0)) for li in transaction.get("lineItems", []))
                    
                    if total_line_amounts > 0:
                        amount_for_category = (line_amount / total_line_amounts) * transaction_total
                    else:
                        amount_for_category = transaction_total
                
                # Create a transaction entry for this line item
                line_transaction = {
                    "transaction_id": transaction["transaction_id"],
                    "type": transaction["type"],
                    "lineItems": [line_item],
                    "category_name": category_info.get("name"),
                    "category_type": category_info.get("type")
                }

                # Categorize based on category name
                if category_type == "interestexpense":
                    subcategorized["spent"]["interest_payment"]["data"].append(line_transaction)
                    subcategorized["spent"]["interest_payment"]["total"] += amount_for_category
                elif category_type == "payroll":
                    subcategorized["spent"]["payroll"]["data"].append(line_transaction)
                    subcategorized["spent"]["payroll"]["total"] += amount_for_category
                elif category_type == "rates":
                    subcategorized["spent"]["rates"]["data"].append(line_transaction)
                    subcategorized["spent"]["rates"]["total"] += amount_for_category
                elif category_type == 'loan':
                    subcategorized["spent"]["loan_payment"]["data"].append(line_transaction)
                    subcategorized["spent"]["loan_payment"]["total"] += amount_for_category
                elif category_type == "gst":
                    subcategorized["spent"]["gst_payment"]["data"].append(line_transaction)
                    subcategorized["spent"]["gst_payment"]["total"] += amount_for_category
                else:
                    subcategorized["spent"]["others"]["data"].append(line_transaction)
                    subcategorized["spent"]["others"]["total"] += amount_for_category
        
                # Process received transactions
        for transaction in simple_categorized.get("received", {}).get("data", []):
            # Split transaction based on line items and their distributed amounts
            for line_item in transaction.get("lineItems", []):
                account_code = line_item.get("accountCode")
                if not account_code:
                    continue
                
                category_info = account_mappings.get(account_code, {})
                category_type = (category_info.get("type") or "").lower()
                
                # Use distributedAmount if available, otherwise use transaction total
                if "distributedAmount" in line_item:
                    amount_for_category = line_item.get("distributedAmount", 0.0)
                else:
                    # If no distributedAmount, calculate proportionally from transaction total
                    transaction_total = float(transaction.get("total", 0.0))
                    line_amount = float(line_item.get("lineAmount", 0.0))
                    total_line_amounts = sum(float(li.get("lineAmount", 0.0)) for li in transaction.get("lineItems", []))
                    
                    if total_line_amounts > 0:
                        amount_for_category = (line_amount / total_line_amounts) * transaction_total
                    else:
                        amount_for_category = transaction_total
                
                # Create a transaction entry for this line item
                line_transaction = {
                    "transaction_id": transaction["transaction_id"],
                    "type": transaction["type"],
                    "lineItems": [line_item],
                    "category_name": category_info.get("name"),
                    "category_type": category_info.get("type")
                }
                
                # Check if it's rental income
                if category_type == "gst":
                    subcategorized["received"]["gst_refund"]["data"].append(line_transaction)
                    subcategorized["received"]["gst_refund"]["total"] += amount_for_category
                elif category_type == "rent":
                    subcategorized["received"]["rental_income"]["data"].append(line_transaction)
                    subcategorized["received"]["rental_income"]["total"] += amount_for_category
                else:
                    # All other income goes to general income
                    subcategorized["received"]["income"]["data"].append(line_transaction)
                    subcategorized["received"]["income"]["total"] += amount_for_category
        
        return subcategorized

    def _process_line_items_with_distribution(self, line_items: List[Dict[str, Any]], payment_total: float) -> List[Dict[str, Any]]:
        """
        Process line items and apply proportional distribution if there are multiple items with different account codes.
        
        Args:
            line_items: List of line items from the transaction
            payment_total: Total payment amount for this transaction
            
        Returns:
            Processed line items with distributed amounts
        """
        print(f"[CASHFLOW DEV DEBUG] line_items={line_items}")
        if not line_items or len(line_items) <= 1:
            # Single line item or no line items - no distribution needed
            clean_line_items = []
            for line_item in line_items:
                clean_line_items.append({
                    "accountCode": line_item.get("accountCode"),
                    "lineAmount": line_item.get("lineAmount"),
                    "description": line_item.get("description"),
                })
            return clean_line_items
        
        # Check if we have multiple line items with different account codes
        account_codes = set()
        for line_item in line_items:
            account_code = line_item.get("accountCode")
            if account_code:
                account_codes.add(account_code)
        
        if len(account_codes) <= 1:
            # All line items have the same account code - no distribution needed
            clean_line_items = []
            for line_item in line_items:
                clean_line_items.append({
                    "accountCode": line_item.get("accountCode"),
                    "lineAmount": line_item.get("lineAmount"),
                    "description": line_item.get("description"),
                })
            return clean_line_items
        
        # Multiple line items with different account codes - apply proportional distribution
        total_invoice_amount = sum(float(line_item.get("lineAmount", 0.0)) for line_item in line_items)
        
        if total_invoice_amount <= 0:
            # Fallback to original amounts if total is invalid
            clean_line_items = []
            for line_item in line_items:
                clean_line_items.append({
                    "accountCode": line_item.get("accountCode"),
                    "lineAmount": line_item.get("lineAmount"),
                    "description": line_item.get("description"),
                })
            return clean_line_items
        
        # Calculate proportional distribution
        clean_line_items = []
        for line_item in line_items:
            original_amount = float(line_item.get("lineAmount", 0.0))
            percentage = (original_amount / total_invoice_amount) * 100
            distributed_amount = (original_amount / total_invoice_amount) * payment_total
            
            clean_line_items.append({
                "accountCode": line_item.get("accountCode"),
                "lineAmount": line_item.get("lineAmount"),
                "description": line_item.get("description"),
                "distributedAmount": round(distributed_amount, 2)
            })
        
        return clean_line_items

    async def generate_cashflow_report(self, report_date: str, period: int, period_of: str, connection_ids: str) -> Dict[str, Any]:
        """
        Generate cashflow report
        """

        if report_date:
            try:
                parsed_date = datetime.strptime(report_date, "%Y-%m-%d").date()
                report_date_obj = parsed_date
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid report_date format. Use YYYY-MM-DD.")
        else:
            report_date_obj = datetime.utcnow().date()
        
        report_date_str = report_date_obj.strftime("%Y-%m-%d")
        
        try:
            # Get cashflow data
            result = await self.get_cashflow_data(
                report_date=report_date_str,
                period=period,
                period_of=period_of,
                connection_ids=connection_ids
            )
            
            # Extract data and errors from result
            cashflow_data = result.get("data", {})
            errors = result.get("errors", [])
            
            # Calculate date ranges for export
            date_ranges = calculate_date_ranges(report_date_str, period, period_of)
            
            # Export to Excel - use absolute path to ensure both app and worker use same location
            excel_file_path = export_cashflow_to_excel(
                cashflow_data=cashflow_data,
                date_ranges=date_ranges,
                filename="cashflow_report",
                output_dir=os.getenv('OUTPUT_DIR'),
                report_date=report_date_str
            )

            # Generate JSON response
            json_response = generate_cashflow_json_response(
                cashflow_data=cashflow_data,
                date_ranges=date_ranges,
                excel_file_path=excel_file_path,
                errors=errors
            )

        except Exception as e:
            print(f"[CASHFLOW DEV DEBUG] Error generating cashflow report: {e}")
            return {
                "error": str(e)
            }
            
        return json_response
