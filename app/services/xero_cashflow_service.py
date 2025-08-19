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
from app.database.models import XeroCategory, XeroAccount
from app.util.db_session_manager import DatabaseSessionManager


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

        connections = [];
        
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
            connections = self.xero_auth_service.get_all_connections()
        
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
                            key, 
                            accounting_api,
                            str(connection.tenant_id),
                            connection.id
                        )
                        
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
                                      key: int, accounting_api: AccountingApi, tenant_id: str, connection_db_id: int):
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

        # Collect bank transaction data for all periods to capture actual balance changes
        bank_transaction_data = self._get_bank_transaction_data(
            accounting_api, tenant_id, account_id, start_date, end_date, connection_db_id
        )
        
        # If this is the first time we're adding spent/received data, initialize it
        if "spent" not in existing_account or not existing_account["spent"]:
            existing_account["spent"] = bank_transaction_data.get("spent", {})
            existing_account["received"] = bank_transaction_data.get("received", {})
        else:
            # Merge the data from this period with existing data
            for category in ["spent", "received"]:
                for subcategory in bank_transaction_data.get(category, {}):
                    if subcategory not in existing_account[category]:
                        existing_account[category][subcategory] = {"total": 0.0, "data": []}
                    
                    # Add totals
                    existing_account[category][subcategory]["total"] += bank_transaction_data[category][subcategory]["total"]
                    # Extend data arrays
                    existing_account[category][subcategory]["data"].extend(bank_transaction_data[category][subcategory]["data"])


    def _get_bank_transaction_data(self, accounting_api: AccountingApi, tenant_id: str, account_id: str, start_date: str, end_date: str, connection_db_id: int) -> Dict[str, Any]:
        """
        Get bank transaction data for a specific date range.
        
        Args:
            accounting_api: Xero Accounting API client
            tenant_id: Xero tenant ID
            account_id: Account ID
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dictionary with spent and received categories
        """
        try:
            # 1.1. Get all bank transactions for the account
            all_transactions = self._get_all_bank_transactions_for_account(
                accounting_api, tenant_id, account_id, start_date, end_date
            )
            
            # 1.2. Get specific bank transaction details with line items
            detailed_transactions = self._get_detailed_bank_transactions(
                accounting_api, tenant_id, all_transactions
            )
            
            # 1.3. Calculate spent and received based on account codes
            categorized_data = self._categorize_bank_transactions(detailed_transactions, connection_db_id)
            
            return categorized_data
            
        except Exception as e:
            print(f"[CASHFLOW] Error getting bank transaction data: {str(e)}")
            return self._get_empty_categories()

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

    def _get_category_mappings(self, connection_db_id: int) -> Dict[str, Any]:
        """
        Get category mappings from database for categorizing transactions.
        
        Returns:
            Dictionary with spent and received category mappings
        """
        try:
            # Use managed session and filter by connection
            with self.session_manager.get_session() as db:
                accounts = db.query(
                    XeroAccount.account_code,
                    XeroAccount.connection_id,
                    XeroCategory.name,
                    XeroCategory.type,
                    XeroCategory.is_income
                ).join(
                    XeroCategory, XeroAccount.category_id == XeroCategory.id
                ).filter(
                    XeroAccount.connection_id == connection_db_id
                ).all()
            
            # Initialize mappings
            category_mappings = {
                "spent": {
                    "gst_payment": [],
                    "interest_payment": [],
                    "loan_payment": [],
                    "payroll": [],
                    "rates": [],
                    "others": [],
                    "gst_refund": []
                },
                "received": {
                    "income": [],
                    "rental_income": []
                }
            }

            
            # Categorize accounts based on category type and is_income flag
            for account_code, connection_id, category_name, category_type, is_income in accounts:
                if is_income:
                    # Income categories
                    if category_type == "Rent":
                        category_mappings["received"]["rental_income"].append(account_code)
                    else:
                        category_mappings["received"]["income"].append(account_code)
                else:
                    # Expense categories
                    if category_name == "Interest Expense":
                        category_mappings["spent"]["interest_payment"].append(account_code)
                    elif category_name == "Staff Costs":
                        category_mappings["spent"]["payroll"].append(account_code)
                    elif category_name == "Rates":
                        category_mappings["spent"]["rates"].append(account_code)
                    elif category_type == "GST":
                        category_mappings["spent"]["gst_payment"].append(account_code)
                    elif category_type == "Loan":
                        category_mappings["spent"]["loan_payment"].append(account_code)
                    elif category_type == "Refund":
                        category_mappings["spent"]["gst_refund"].append(account_code)
                    else:
                        # Others: Get all with is_income false excluding Interest Expense, Staff Costs, Rates
                        if category_name not in ["Interest Expense", "Staff Costs", "Rates"]:
                            category_mappings["spent"]["others"].append(account_code)
            return category_mappings
            
        except Exception as e:
            print(f"Error getting category mappings: {e}")
            # Return empty mappings if there's an error
            return {
                "spent": {
                    "gst_payment": [],
                    "interest_payment": [],
                    "loan_payment": [],
                    "payroll": [],
                    "rates": [],
                    "others": [],
                    "gst_refund": []
                },
                "received": {
                    "income": [],
                    "rental_income": []
                }
            }

    def _categorize_bank_transactions(self, transactions: List[Dict[str, Any]], connection_db_id: int) -> Dict[str, Any]:
        """
        Categorize bank transactions into spent and received categories.
        
        Args:
            transactions: List of detailed transactions with line items
            
        Returns:
            Dictionary with spent and received categories
        """
        # Get category mappings from database for this connection
        category_mappings = self._get_category_mappings(connection_db_id)
        
        # Initialize categories
        categorized_data = {
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
                "income": {"total": 0.0, "data": []},
                "rental_income": {"total": 0.0, "data": []}
            }
        }
        
        for transaction in transactions:
            transaction_type = transaction.get("type", "")
            transaction_total = transaction.get("total", 0.0)
            
            # Process line items for categorization
            for line_item in transaction.get("lineItems", []):
                account_code = line_item.get("accountCode", "")
                line_amount = line_item.get("lineAmount", 0.0)
                
                # Categorize based on account code
                categorized = False
                
                # Check received categories first
                if account_code in category_mappings["received"]["income"]:
                    categorized_data["received"]["income"]["total"] += line_amount
                    categorized_data["received"]["income"]["data"].append({
                        "type": "bankTransaction",
                        "transaction_id": transaction["transaction_id"],
                        "accountCode": account_code,
                        "unitPrice": line_item["unitAmount"],
                        "quantity": line_item["quantity"],
                        "lineAmount": line_amount,
                        "description": line_item["description"],
                        "taxAmount": line_item["taxAmount"]
                    })
                    categorized = True
                    
                elif account_code in category_mappings["received"]["rental_income"]:
                    categorized_data["received"]["rental_income"]["total"] += line_amount
                    categorized_data["received"]["rental_income"]["data"].append({
                        "type": "bankTransaction",
                        "transaction_id": transaction["transaction_id"],
                        "accountCode": account_code,
                        "unitPrice": line_item["unitAmount"],
                        "quantity": line_item["quantity"],
                        "lineAmount": line_amount,
                        "description": line_item["description"],
                        "taxAmount": line_item["taxAmount"]
                    })
                    categorized = True
                
                # Check spent categories
                elif account_code in category_mappings["spent"]["interest_payment"]:
                    categorized_data["spent"]["interest_payment"]["total"] += line_amount
                    categorized_data["spent"]["interest_payment"]["data"].append({
                        "type": "bankTransaction",
                        "transaction_id": transaction["transaction_id"],
                        "accountCode": account_code,
                        "unitPrice": line_item["unitAmount"],
                        "quantity": line_item["quantity"],
                        "lineAmount": line_amount,
                        "description": line_item["description"],
                        "taxAmount": line_item["taxAmount"]
                    })
                    categorized = True
                    
                elif account_code in category_mappings["spent"]["payroll"]:
                    categorized_data["spent"]["payroll"]["total"] += line_amount
                    categorized_data["spent"]["payroll"]["data"].append({
                        "type": "bankTransaction",
                        "transaction_id": transaction["transaction_id"],
                        "accountCode": account_code,
                        "unitPrice": line_item["unitAmount"],
                        "quantity": line_item["quantity"],
                        "lineAmount": line_amount,
                        "description": line_item["description"],
                        "taxAmount": line_item["taxAmount"]
                    })
                    categorized = True
                    
                elif account_code in category_mappings["spent"]["rates"]:
                    categorized_data["spent"]["rates"]["total"] += line_amount
                    categorized_data["spent"]["rates"]["data"].append({
                        "type": "bankTransaction",
                        "transaction_id": transaction["transaction_id"],
                        "accountCode": account_code,
                        "unitPrice": line_item["unitAmount"],
                        "quantity": line_item["quantity"],
                        "lineAmount": line_amount,
                        "description": line_item["description"],
                        "taxAmount": line_item["taxAmount"]
                    })
                    categorized = True
                
                # If not categorized, add to "others" for spent items
                if not categorized:
                    categorized_data["spent"]["others"]["total"] += line_amount
                    categorized_data["spent"]["others"]["data"].append({
                        "type": "bankTransaction",
                        "transaction_id": transaction["transaction_id"],
                        "accountCode": account_code,
                        "unitPrice": line_item["unitAmount"],
                        "quantity": line_item["quantity"],
                        "lineAmount": line_amount,
                        "description": line_item["description"],
                        "taxAmount": line_item["taxAmount"]
                    })
        
        return categorized_data

    def _get_empty_categories(self) -> Dict[str, Any]:
        """
        Return empty category structure.
        """
        return {
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
                "income": {"total": 0.0, "data": []},
                "rental_income": {"total": 0.0, "data": []}
            }
        }