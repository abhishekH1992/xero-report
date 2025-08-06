import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.util.report_helper import (
    format_account_number, 
    format_date_range_for_excel
)


def export_cashflow_to_excel(
    cashflow_data: Dict[str, Any],
    date_ranges: List[Tuple[str, str]],
    filename: str = "cashflow_report",
    output_dir: str = "tmp",
    report_date: str = None
) -> str:
    """
    Export CashFlow report data to Excel with multiple sheets for ASB, ANZ, and Other banks (BNZ, ICBC, CCB, Kiwi Bank).
    
    Args:
        cashflow_data: Dictionary containing cashflow data for all connections
        date_ranges: List of date ranges used in the report
        filename: Base filename for the Excel file
        output_dir: Directory to save the Excel file
        report_date: Report date string in YYYY-MM-DD format
    
    Returns:
        Path to the generated Excel file
    """
    os.makedirs(output_dir, exist_ok=True)
    wb = openpyxl.Workbook()
    
    # Remove default sheet
    wb.remove(wb.active)
    
    # Create sheets
    bank_balance_sheet = wb.create_sheet("Bank Balance Sheet")
    asb_sheet = wb.create_sheet("ASB")
    anz_sheet = wb.create_sheet("ANZ")
    other_sheet = wb.create_sheet("Other")
    
    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="366092")
    header_alignment = Alignment("center", "center")
    title_font = Font(bold=True, size=14)
    title_alignment = Alignment("center")
    border = Border(
        left=Side("thin"), right=Side("thin"),
        top=Side("thin"), bottom=Side("thin")
    )
    
    # Create Bank Balance Sheet with ownership grouping
    create_bank_balance_sheet(bank_balance_sheet, cashflow_data, date_ranges,
                             header_font, header_fill, header_alignment,
                             title_font, title_alignment, border, report_date)
    
    # Create ASB, ANZ, and BNZ sheets
    create_bank_sheet(asb_sheet, "ASB", cashflow_data, date_ranges, 
                     header_font, header_fill, header_alignment, 
                     title_font, title_alignment, border)
    
    create_bank_sheet(anz_sheet, "ANZ", cashflow_data, date_ranges,
                     header_font, header_fill, header_alignment,
                     title_font, title_alignment, border)
    
    create_other_banks_sheet(other_sheet, cashflow_data, date_ranges,
                     header_font, header_fill, header_alignment,
                     title_font, title_alignment, border)
    
    # Save file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"{filename}_{timestamp}.xlsx")
    wb.save(path)
    return path


def create_bank_balance_sheet(ws, cashflow_data: Dict[str, Any], date_ranges: List[Tuple[str, str]], 
                             header_font, header_fill, header_alignment, title_font, title_alignment, border, report_date: str = None):
    """Create comprehensive Bank Balance Report grouped by ownership."""
    
    # Get ownership data from database
    from app.database.database import engine
    from app.database.models import XeroConnection
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get all connections with ownership data
        connections = session.query(XeroConnection).filter(XeroConnection.is_active == True).all()
        
        # Group connections by ownership
        ownership_groups = {
            "fully_owned": [],
            "partially_owned": [],
            "not_owned": []
        }
        
        for connection in connections:
            if connection.ownership == "fully_owned":
                ownership_groups["fully_owned"].append(connection)
            elif connection.ownership == "partially_owned":
                ownership_groups["partially_owned"].append(connection)
            elif connection.ownership == "not_owned":
                ownership_groups["not_owned"].append(connection)
        
        current_row = 1
        
        # Add Cash Balance Summary section at the top
        from app.util.report_helper import calculate_cash_balance_summary
        
        # Calculate cash balance summary
        cash_summary = calculate_cash_balance_summary(cashflow_data, date_ranges, ownership_groups, report_date)

        print(cash_summary)
        
        # Add report title
        ws[f"A{current_row}"] = f"Cash balance report - {cash_summary['report_date']}"
        ws[f"A{current_row}"].font = Font(bold=True, size=16)
        ws[f"A{current_row}"].alignment = Alignment("center")
        ws.merge_cells(f"A{current_row}:I{current_row}")
        current_row += 2
        
        # Write period headers
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_label = format_date_range_for_excel(start_date, end_date)
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = period_label
            cell.font = Font(bold=True)
            cell.alignment = Alignment("center")
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = "Difference"
            cell.font = Font(bold=True)
            cell.alignment = Alignment("center")
            cell.border = border
            col_idx += 1
        
        # Add new column header
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = ""
        
        current_row += 1
        
        # Add fully owned row
        ws[f"A{current_row}"] = "Total available cash"
        ws[f"A{current_row}"].font = Font(bold=True)
        ws[f"A{current_row}"].border = border
        ws.merge_cells(f"A{current_row}:C{current_row}")
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = period_summary["fully_owned"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            latest_period = list(cash_summary["periods"].keys())[0]
            previous_period = list(cash_summary["periods"].keys())[1]
            difference = cash_summary["periods"][latest_period]["fully_owned"] - cash_summary["periods"][previous_period]["fully_owned"]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = difference
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "100% owned entity"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)

        current_row += 1
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = period_summary["partially_owned"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            latest_period = list(cash_summary["periods"].keys())[0]
            previous_period = list(cash_summary["periods"].keys())[1]
            difference = cash_summary["periods"][latest_period]["partially_owned"] - cash_summary["periods"][previous_period]["partially_owned"]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = difference
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "Majority control - SWH / RCR & DG"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        
        current_row += 1
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = period_summary["total_available_cash"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            cell.font = Font(bold=True)
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            latest_period = list(cash_summary["periods"].keys())[0]
            previous_period = list(cash_summary["periods"].keys())[1]
            difference = cash_summary["periods"][latest_period]["total_available_cash"] - cash_summary["periods"][previous_period]["total_available_cash"]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = difference
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            cell.font = Font(bold=True)
            col_idx += 1
        
        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "100% + SWH"
        cell.border = border
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True)
        
        current_row += 1

        ws[f"A{current_row}"] = "Minimum cash holding"
        ws[f"A{current_row}"].font = Font(bold=True)
        ws[f"A{current_row}"].border = border
        ws.merge_cells(f"A{current_row}:C{current_row}")
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = cash_summary["minimum_cash_holding"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = 0  # No difference for static value
            cell.number_format = '"$"#,##0.00'
            cell.border = border
        
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = 0
        cell.number_format = '"$"#,##0.00'
        cell.border = border
        col_idx += 1

        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "Minimum cash holding"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        col_idx += 1

        current_row += 1
        
        # Add Minimum cash holding excess row
        ws[f"A{current_row}"] = "Minimum cash holding excess"
        ws[f"A{current_row}"].font = Font(bold=True)
        ws[f"A{current_row}"].border = border
        ws.merge_cells(f"A{current_row}:C{current_row}")
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = period_summary["minimum_cash_holding_excess"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            cell.font = Font(bold=True)
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            latest_period = list(cash_summary["periods"].keys())[0]
            previous_period = list(cash_summary["periods"].keys())[1]
            difference = cash_summary["periods"][latest_period]["minimum_cash_holding_excess"] - cash_summary["periods"][previous_period]["minimum_cash_holding_excess"]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = difference
            cell.font = Font(bold=True)
            cell.number_format = '"$"#,##0.00'
            cell.border = border

        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = 0
        cell.number_format = '"$"#,##0.00'
        cell.border = border
        cell.font = Font(bold=True)
        col_idx += 1
        
        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "Amount over/(under) minimum"
        cell.border = border
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True)
        
        current_row += 1
        
        # Add new row with 100% + SWH again
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = period_summary["total_available_cash"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            latest_period = list(cash_summary["periods"].keys())[0]
            previous_period = list(cash_summary["periods"].keys())[1]
            difference = cash_summary["periods"][latest_period]["total_available_cash"] - cash_summary["periods"][previous_period]["total_available_cash"]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = difference
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "100% + SWH"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        col_idx += 1
        
        current_row += 1
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = cash_summary["term_deposit"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = 0  # No difference for static value
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add new column data
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "Term Deposits"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        col_idx += 1
        
        current_row += 1
        
        # Add Total Cash section (with term deposit)
        ws[f"A{current_row}"] = "Total Cash"
        ws[f"A{current_row}"].font = Font(bold=True)
        ws[f"A{current_row}"].border = border
        ws.merge_cells(f"A{current_row}:C{current_row}")
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = period_summary["total_with_term_deposit"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            cell.font = Font(bold=True)
            col_idx += 1
        
        # Add difference column if multiple periods
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        latest_period = list(cash_summary["periods"].keys())[0]
        previous_period = list(cash_summary["periods"].keys())[1]
        difference = cash_summary["periods"][latest_period]["total_available_cash"] - cash_summary["periods"][previous_period]["total_available_cash"]
        cell.value = difference
        cell.number_format = '"$"#,##0.00'
        cell.border = border
        cell.font = Font(bold=True)
        col_idx += 1
            

        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "Total Cash"
        cell.border = border
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True)
        col_idx += 1

        current_row += 1

        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = 0
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = 0
        cell.number_format = '"$"#,##0.00'
        cell.border = border
        col_idx += 1
            
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "SW Key China"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        col_idx += 1

        current_row += 1
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = 0
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = 0
        cell.number_format = '"$"#,##0.00'
        cell.border = border
        col_idx += 1
            
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "LP/GP & SW developments"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)

        current_row += 1
        col_idx = 4
        for start_date, end_date in date_ranges:
            period_key = f"{start_date}_{end_date}"
            period_summary = cash_summary["periods"][period_key]
            cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
            cell.value = 0
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            col_idx += 1
        
        # Add difference column if multiple periods
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = 0
        cell.number_format = '"$"#,##0.00'
        cell.border = border
        col_idx += 1
            
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "Total Cash"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        
        current_row += 3
        
        # Process each ownership group
        ownership_titles = {
            "fully_owned": "100 percent owned by John and Michael",
            "partially_owned": "Not 100 percent owned by John and Michael", 
            "not_owned": "John and Michael has no ownership interest"
        }
        
        for ownership_type, title in ownership_titles.items():
            connections_in_group = ownership_groups[ownership_type]
            
            if not connections_in_group:
                continue
                
            # Calculate table width for title merging
            # 3 fixed columns (Account Number, Account Name, Company) + balance columns + additional columns
            balance_cols = len(date_ranges)
            if len(date_ranges) > 1:
                balance_cols += 1  # Add one more for difference column
            
            additional_cols = 3  # Minimum Balance, Next due date for Loan payment, Payment amount
            table_width = 3 + balance_cols + additional_cols
            last_column = get_column_letter(table_width)
            
            # Add ownership section title
            ws[f"A{current_row}"] = title
            ws[f"A{current_row}"].font = Font(bold=True, size=16)
            ws[f"A{current_row}"].alignment = Alignment("left")
            ws.merge_cells(f"A{current_row}:{last_column}{current_row}")
            current_row += 2
            
            # Group connections by bank (ASB, ANZ, etc.)
            bank_groups = {}
            # Accounts to exclude
            excluded_accounts = ["389026059757103", "389026059757102"]
            
            for connection in connections_in_group:
                connection_name = connection.tenant_name
                if connection_name in cashflow_data:
                    for account_data in cashflow_data[connection_name].get('accounts', []):
                        # Skip excluded accounts
                        account_number = account_data.get('account_number', '')
                        if account_number in excluded_accounts:
                            continue
                            
                        bank_name = account_data.get('bank_name', 'Unknown')
                        if bank_name not in bank_groups:
                            bank_groups[bank_name] = []
                        bank_groups[bank_name].append({
                            'connection': connection,
                            'account_data': account_data
                        })
            
            # Process each bank group
            for bank_name, bank_accounts in bank_groups.items():
                if not bank_accounts:
                    continue
                    
                # Add bank section
                ws[f"A{current_row}"] = f"Bank Name: {bank_name}"
                ws[f"A{current_row}"].font = Font(bold=True, size=14)
                ws[f"A{current_row}"].alignment = Alignment("left")
                ws.merge_cells(f"A{current_row}:{last_column}{current_row}")
                current_row += 1
                
                # Create headers
                headers = ["Account Number", "Account Name", "Company"]
                
                # Add Balance column header that spans all periods and difference
                balance_cols = len(date_ranges)
                if len(date_ranges) > 1:
                    balance_cols += 1  # Add one more for difference column
                
                # Write first three headers
                for col_idx, header in enumerate(headers, 1):
                    cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                    cell.value = header
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                    cell.border = border
                
                # Merge and write Balance header
                if balance_cols > 0:
                    start_col = get_column_letter(4)
                    end_col = get_column_letter(3 + balance_cols)
                    ws.merge_cells(f"{start_col}{current_row}:{end_col}{current_row}")
                    cell = ws[f"{start_col}{current_row}"]
                    cell.value = "Balance"
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                    cell.border = border
                
                # Add additional columns with blue background
                additional_headers = [
                    "Minimum Balance", 
                    "Next due date for Loan payment",
                    "Payment amount"
                ]
                
                # Write additional headers
                for col_idx, header in enumerate(additional_headers, 4 + balance_cols):
                    cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                    cell.value = header
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                    cell.border = border
                

                
                current_row += 1
                
                # Add sub-header row for Balance periods and difference
                ws[f"A{current_row}"] = ""
                ws[f"A{current_row}"].border = border
                ws[f"B{current_row}"] = ""
                ws[f"B{current_row}"].border = border
                ws[f"C{current_row}"] = ""
                ws[f"C{current_row}"].border = border
                
                # Add period sub-headers (latest first) with actual date ranges
                col_idx = 4
                for i in range(len(date_ranges)):
                    start_date, end_date = date_ranges[i]
                    period_label = format_date_range_for_excel(start_date, end_date)
                    cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                    cell.value = period_label
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = header_fill
                    cell.alignment = Alignment("center")
                    cell.border = border
                    col_idx += 1
                
                # Add difference sub-header
                if len(date_ranges) > 1:
                    cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                    cell.value = "Difference"
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = header_fill
                    cell.alignment = Alignment("center")
                    cell.border = border
                    col_idx += 1
                
                # Add blank cells for additional columns with white background
                for _ in range(3):  # Minimum Balance, Next due date, Payment amount
                    cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                    cell.value = ""
                    cell.border = border
                    # Keep white/transparent background
                    col_idx += 1
                
                current_row += 1
                
                # Write data rows
                for bank_account in bank_accounts:
                    account_data = bank_account['account_data']
                    connection = bank_account['connection']
                    
                    # Account details
                    ws[f"A{current_row}"] = format_account_number(account_data.get('account_number', ''))
                    ws[f"A{current_row}"].border = border
                    ws[f"B{current_row}"] = account_data.get('account_name', '')
                    ws[f"B{current_row}"].border = border
                    ws[f"C{current_row}"] = connection.tenant_name.strip()
                    ws[f"C{current_row}"].border = border
                    
                    # Add available/closing balances (latest first)
                    col_idx = 4
                    available_balances = []
                    
                    for i in range(len(date_ranges)):
                        start_date, end_date = date_ranges[i]
                        period_key = f"{start_date}_{end_date}"
                        period_data = account_data.get('periods', {}).get(period_key, {})
                        available_balance = period_data.get('closing_balance', 0)  # Use closing/available balance
                        available_balances.append(available_balance)
                        
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = float(available_balance) if available_balance else 0
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1
                    
                    # Add difference column (Period 1 available - Period 2 available)
                    if len(available_balances) > 1:
                        difference = available_balances[0] - available_balances[1]  # Period 1 - Period 2
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = float(difference)
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        
                        # Color coding for negative values
                        if difference < 0:
                            cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red
                            cell.font = Font(color="FF0000")  # Red text
                        
                        col_idx += 1
                    
                    # Add additional columns
                    ws[f"{get_column_letter(col_idx)}{current_row}"] = connection.min_balance or ""
                    ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                    col_idx += 1
                    ws[f"{get_column_letter(col_idx)}{current_row}"] = ""  # Next due date
                    ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                    col_idx += 1
                    ws[f"{get_column_letter(col_idx)}{current_row}"] = ""  # Payment amount
                    ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                    
                    current_row += 1
                
                # Add totals for this bank
                if bank_accounts:
                    ws[f"A{current_row}"] = "Total"
                    ws[f"A{current_row}"].font = Font(bold=True)
                    ws[f"A{current_row}"].border = border
                    ws[f"B{current_row}"] = ""
                    ws[f"B{current_row}"].border = border
                    ws[f"C{current_row}"] = ""
                    ws[f"C{current_row}"].border = border
                    
                    # Calculate totals for each period using available balances
                    col_idx = 4
                    bank_totals = [0] * len(date_ranges)
                    
                    for bank_account in bank_accounts:
                        account_data = bank_account['account_data']
                        for i in range(len(date_ranges)):
                            start_date, end_date = date_ranges[i]
                            period_key = f"{start_date}_{end_date}"
                            period_data = account_data.get('periods', {}).get(period_key, {})
                            available_balance = period_data.get('closing_balance', 0)  # Use available/closing balance
                            bank_totals[i] += available_balance
                    
                    # Write totals
                    for total in bank_totals:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = float(total)
                        cell.font = Font(bold=True)
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1
                    
                    # Add difference total
                    if len(bank_totals) > 1:
                        difference = bank_totals[0] - bank_totals[1]
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = float(difference)
                        cell.font = Font(bold=True)
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        
                        if difference < 0:
                            cell.fill = PatternFill("solid", fgColor="FFE6E6")
                            cell.font = Font(bold=True, color="FF0000")
                        
                        col_idx += 1
                    
                    # Add blank columns for totals
                    for _ in range(3):  # Minimum Balance, Next due date, Payment amount
                        ws[f"{get_column_letter(col_idx)}{current_row}"] = ""
                        ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                        col_idx += 1
                    
                    current_row += 1
                
                # Add spacing between banks
                current_row += 2
            
            # Add ownership group totals
            if ownership_groups[ownership_type]:
                # Add calculation section for fully_owned group
                if ownership_type == "fully_owned":
                    # Calculate total available cash for each period
                    period_totals = {}
                    for start_date, end_date in date_ranges:
                        period_key = f"{start_date}_{end_date}"
                        period_totals[period_key] = 0
                        for bank_name, bank_accounts in bank_groups.items():
                            for account_info in bank_accounts:
                                account_data = account_info['account_data']
                                period_data = account_data.get('periods', {}).get(period_key, {})
                                closing_balance = period_data.get('closing_balance', 0)
                                period_totals[period_key] += float(closing_balance) if closing_balance else 0
                    
                    # Static minimum cash holding
                    minimum_cash_holding = 5000000.00
                    
                    # Add calculation table headers
                    ws[f"A{current_row}"] = "Total available cash"
                    ws[f"A{current_row}"].font = Font(bold=True)
                    ws[f"A{current_row}"].border = border
                    ws.merge_cells(f"A{current_row}:C{current_row}")
                    
                    # Write period totals
                    col_idx = 4
                    for start_date, end_date in date_ranges:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = period_totals[f"{start_date}_{end_date}"]
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1
                    
                    # Add difference column if multiple periods
                    if len(date_ranges) > 1:
                        latest_period = list(period_totals.keys())[0]
                        previous_period = list(period_totals.keys())[1]
                        difference = period_totals[latest_period] - period_totals[previous_period]
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = difference
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                    
                    current_row += 1
                    
                    ws[f"A{current_row}"] = "Minimum cash holding"
                    ws[f"A{current_row}"].font = Font(bold=True)
                    ws[f"A{current_row}"].border = border
                    ws.merge_cells(f"A{current_row}:C{current_row}")

 
                    # Write minimum cash holding for each period
                    col_idx = 4
                    for start_date, end_date in date_ranges:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = minimum_cash_holding
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1
                    
                    # Add difference column if multiple periods
                    if len(date_ranges) > 1:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = 0  # No difference for static value
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                    
                    current_row += 1
                    
                    ws[f"A{current_row}"] = "Minimum cash holding excess"
                    ws[f"A{current_row}"].font = Font(bold=True)
                    ws[f"A{current_row}"].border = border
                    ws.merge_cells(f"A{current_row}:C{current_row}")

                    # Calculate and write excess for each period
                    col_idx = 4
                    for start_date, end_date in date_ranges:
                        period_key = f"{start_date}_{end_date}"
                        excess = period_totals[period_key] - minimum_cash_holding
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = excess
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        
                        # Apply red background and text if negative
                        if excess < 0:
                            cell.fill = PatternFill("solid", fgColor="FFCCCC")  # Light red background
                            cell.font = Font(bold=True, color="FF0000")  # Red text
                        
                        col_idx += 1
                    
                    # Add difference column if multiple periods
                    if len(date_ranges) > 1:
                        latest_excess = period_totals[list(period_totals.keys())[0]] - minimum_cash_holding
                        previous_excess = period_totals[list(period_totals.keys())[1]] - minimum_cash_holding
                        excess_difference = latest_excess - previous_excess
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = excess_difference
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        
                        # Apply red background and text if negative
                        if excess_difference < 0:
                            cell.fill = PatternFill("solid", fgColor="FFCCCC")  # Light red background
                            cell.font = Font(bold=True, color="FF0000")  # Red text
                    
                    current_row += 2
                else:
                    # For other ownership groups, calculate total available cash for each period
                    period_totals = {}
                    for start_date, end_date in date_ranges:
                        period_key = f"{start_date}_{end_date}"
                        period_totals[period_key] = 0
                        for bank_name, bank_accounts in bank_groups.items():
                            for account_info in bank_accounts:
                                account_data = account_info['account_data']
                                period_data = account_data.get('periods', {}).get(period_key, {})
                                closing_balance = period_data.get('closing_balance', 0)
                                period_totals[period_key] += float(closing_balance) if closing_balance else 0
                    
                    # Add calculation table headers
                    ws[f"A{current_row}"] = "Total available cash"
                    ws[f"A{current_row}"].font = Font(bold=True)
                    ws[f"A{current_row}"].border = border
                    ws.merge_cells(f"A{current_row}:C{current_row}")
                    
                    # Write period totals
                    col_idx = 4
                    for start_date, end_date in date_ranges:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = period_totals[f"{start_date}_{end_date}"]
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        
                        # Apply red background and text if negative
                        if cell.value < 0:
                            cell.fill = PatternFill("solid", fgColor="FFCCCC")  # Light red background
                            cell.font = Font(bold=True, color="FF0000")  # Red text
                        
                        col_idx += 1
                    
                    # Add difference column if multiple periods
                    if len(date_ranges) > 1:
                        latest_period = list(period_totals.keys())[0]
                        previous_period = list(period_totals.keys())[1]
                        difference = period_totals[latest_period] - period_totals[previous_period]
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = difference
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        
                        # Apply red background and text if negative
                        if difference < 0:
                            cell.fill = PatternFill("solid", fgColor="FFCCCC")  # Light red background
                            cell.font = Font(bold=True, color="FF0000")  # Red text
                    
                    current_row += 2
        
        # Set column widths
        ws.column_dimensions['A'].width = 25  # Account Number
        ws.column_dimensions['B'].width = 25  # Account Name
        ws.column_dimensions['C'].width = 30  # Company
        
        # Set width for balance columns
        balance_cols = len(date_ranges)
        if len(date_ranges) > 1:
            balance_cols += 1  # Add one more for difference column
        
        for i in range(4, 4 + balance_cols):
            ws.column_dimensions[get_column_letter(i)].width = 20
        
        # Set width for additional columns
        for i in range(4 + balance_cols, 4 + balance_cols + 3):
            ws.column_dimensions[get_column_letter(i)].width = 20
        
    finally:
        session.close()


def create_bank_sheet(ws, bank_name: str, cashflow_data: Dict[str, Any], 
                     date_ranges: List[Tuple[str, str]], header_font, header_fill, 
                     header_alignment, title_font, title_alignment, border):
    """Create ASB, ANZ, or BNZ sheet with cashflow data."""
    current_row = 1
    
    # Calculate table width based on date ranges
    # 3 fixed columns (Account Number, Account Name, Company) + 2 columns per date range
    table_width = 3 + (len(date_ranges) * 2)
    last_column = get_column_letter(table_width)
    
    # Title
    ws.merge_cells(f"A{current_row}:{last_column}{current_row}")
    ws[f"A{current_row}"] = f"{bank_name} Cash Flow Report"
    ws[f"A{current_row}"].font = title_font
    ws[f"A{current_row}"].alignment = Alignment("center")
    current_row += 1
    
    # Date ranges header row
    ws[f"A{current_row}"] = "Account Number"
    ws[f"A{current_row}"].font = header_font
    ws[f"A{current_row}"].fill = header_fill
    ws[f"A{current_row}"].alignment = header_alignment
    ws[f"A{current_row}"].border = border
    
    ws[f"B{current_row}"] = "Account Name"
    ws[f"B{current_row}"].font = header_font
    ws[f"B{current_row}"].fill = header_fill
    ws[f"B{current_row}"].alignment = header_alignment
    ws[f"B{current_row}"].border = border
    
    ws[f"C{current_row}"] = "Company"
    ws[f"C{current_row}"].font = header_font
    ws[f"C{current_row}"].fill = header_fill
    ws[f"C{current_row}"].alignment = header_alignment
    ws[f"C{current_row}"].border = border
    
    # Add Balance column header that spans all periods
    balance_cols = len(date_ranges) * 2  # 2 columns per period (Opening, Available)
    start_col = get_column_letter(4)
    end_col = get_column_letter(3 + balance_cols)
    ws.merge_cells(f"{start_col}{current_row}:{end_col}{current_row}")
    ws[f"{start_col}{current_row}"] = "Balance"
    ws[f"{start_col}{current_row}"].font = header_font
    ws[f"{start_col}{current_row}"].fill = header_fill
    ws[f"{start_col}{current_row}"].alignment = header_alignment
    ws[f"{start_col}{current_row}"].border = border
    
    # Set column widths
    ws.column_dimensions['A'].width = 25  # Account Number
    ws.column_dimensions['B'].width = 25  # Account Name
    ws.column_dimensions['C'].width = 30  # Company Name
    
    # Set width for amount columns (D onwards)
    col_idx = 4
    for start_date, end_date in date_ranges:
        # Set width for each of the 4 amount columns per period
        ws.column_dimensions[get_column_letter(col_idx)].width = 15      # Opening
        ws.column_dimensions[get_column_letter(col_idx+1)].width = 15    # Cash Received
        ws.column_dimensions[get_column_letter(col_idx+2)].width = 15    # Cash Spent
        ws.column_dimensions[get_column_letter(col_idx+3)].width = 15    # Available
        col_idx += 4
    
    current_row += 1
    
    # Sub-header row for Opening and Available balance
    ws[f"A{current_row}"] = ""
    ws[f"B{current_row}"] = ""
    ws[f"C{current_row}"] = ""
    
    col_idx = 4
    for start_date, end_date in date_ranges:
        # Add period label
        date_range_label = format_date_range_for_excel(start_date, end_date)
        ws.merge_cells(f"{get_column_letter(col_idx)}{current_row}:{get_column_letter(col_idx+1)}{current_row}")
        ws[f"{get_column_letter(col_idx)}{current_row}"] = date_range_label
        ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
        ws[f"{get_column_letter(col_idx)}{current_row}"].alignment = Alignment("center")
        ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
        col_idx += 2
    
    current_row += 1
    
    # Third sub-header row for individual columns
    ws[f"A{current_row}"] = ""
    ws[f"B{current_row}"] = ""
    ws[f"C{current_row}"] = ""
    
    col_idx = 4
    for start_date, end_date in date_ranges:
        ws[f"{get_column_letter(col_idx)}{current_row}"] = "Opening"
        ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
        ws[f"{get_column_letter(col_idx)}{current_row}"].alignment = Alignment("center")
        ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
        
        ws[f"{get_column_letter(col_idx+1)}{current_row}"] = "Available"
        ws[f"{get_column_letter(col_idx+1)}{current_row}"].font = Font(bold=True)
        ws[f"{get_column_letter(col_idx+1)}{current_row}"].alignment = Alignment("center")
        ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
        col_idx += 2
    
    current_row += 1
    
    # Data rows
    total_row = current_row
    
    # Process data for this bank
    # Accounts to exclude
    excluded_accounts = ["389026059757103", "389026059757102"]
    
    for connection_name, connection_data in cashflow_data.items():
        for account_data in connection_data.get('accounts', []):
            if account_data.get('bank_name') == bank_name:
                # Skip excluded accounts
                account_number_raw = account_data.get('account_number', '')
                if account_number_raw in excluded_accounts:
                    continue
                    
                account_number = format_account_number(account_number_raw)
                
                # Write account and connection name
                ws[f"A{current_row}"] = account_number
                ws[f"A{current_row}"].border = border
                ws[f"B{current_row}"] = account_data.get('account_name', '')
                ws[f"B{current_row}"].border = border
                ws[f"C{current_row}"] = connection_name
                ws[f"C{current_row}"].border = border
                
                # Write balance data for each date range
                col_idx = 4
                for start_date, end_date in date_ranges:
                    period_key = f"{start_date}_{end_date}"
                    period_data = account_data.get('periods', {}).get(period_key, {})
                    
                    opening_balance = period_data.get('opening_balance', 0)
                    closing_balance = period_data.get('closing_balance', 0)
                    
                    ws[f"{get_column_letter(col_idx)}{current_row}"] = float(opening_balance) if opening_balance else 0
                    ws[f"{get_column_letter(col_idx)}{current_row}"].number_format = '"$"#,##0.00'
                    ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                    
                    ws[f"{get_column_letter(col_idx+1)}{current_row}"] = float(closing_balance) if closing_balance else 0
                    ws[f"{get_column_letter(col_idx+1)}{current_row}"].number_format = '"$"#,##0.00'
                    ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
                    
                    col_idx += 2
                
                current_row += 1
    
    # Totals row
    if current_row > total_row:
        ws[f"A{current_row}"] = "Total"
        ws[f"A{current_row}"].font = Font(bold=True)
        ws[f"A{current_row}"].border = border
        ws[f"B{current_row}"] = ""
        ws[f"B{current_row}"].border = border
        ws[f"C{current_row}"] = ""
        ws[f"C{current_row}"].border = border
        
        # Calculate totals for each period
        col_idx = 4
        for start_date, end_date in date_ranges:
            opening_total = 0
            closing_total = 0
            
            # Sum up all values in the columns
            for row in range(total_row, current_row):
                opening_val = ws[f"{get_column_letter(col_idx)}{row}"].value or 0
                closing_val = ws[f"{get_column_letter(col_idx+1)}{row}"].value or 0
                opening_total += opening_val
                closing_total += closing_val
            
            ws[f"{get_column_letter(col_idx)}{current_row}"] = opening_total
            ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx)}{current_row}"].number_format = '"$"#,##0.00'
            ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
            
            ws[f"{get_column_letter(col_idx+1)}{current_row}"] = closing_total
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].number_format = '"$"#,##0.00'
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
            
            col_idx += 2
    

    
    # Auto-adjust row heights
    for row in ws.iter_rows():
        h = max(
            15,
            max(
                (len(str(c.value)) * 0.8) if c.value else 0
                for c in row
            )
        )
        ws.row_dimensions[row[0].row].height = min(50, h)


def generate_cashflow_json_response(
    cashflow_data: Dict[str, Any], 
    date_ranges: List[Tuple[str, str]],
    excel_file_path: str,
    errors: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate JSON response for CashFlow report.
    
    Args:
        cashflow_data: Dictionary containing cashflow data
        date_ranges: List of date ranges used in the report
        excel_file_path: Path to the generated Excel file
        errors: List of errors that occurred during processing
    
    Returns:
        JSON response dictionary
    """
    response = {
        "connections": [],
        "system_comments": "",
        "excel_file": excel_file_path,
        "generated_at": datetime.now().isoformat(),
        "report_config": {
            "date_ranges": [{"start": start, "end": end} for start, end in date_ranges]
        },
        "errors": errors or []
    }

    # Process each connection
    # Accounts to exclude
    excluded_accounts = ["389026059757103", "389026059757102"]
    
    for connection_name, connection_data in cashflow_data.items():
        connection_id = connection_data.get('connection_id', None)
        connection_info = {
            "connection_name": connection_name,
            "connection_id": connection_id,
            "banks": []
        }
        
        # Process each bank account
        for account_data in connection_data.get('accounts', []):
            # Skip excluded accounts
            account_number = account_data.get('account_number', '')
            if account_number in excluded_accounts:
                continue
            bank_info = {
                "bank_name": account_data.get('bank_name'),
                "account_number": format_account_number(account_data.get('account_number', '')),
                "periods": []
            }
            
            # Process each period
            for start_date, end_date in date_ranges:
                period_key = f"{start_date}_{end_date}"
                period_data = account_data.get('periods', {}).get(period_key, {})
                
                period_info = {
                    "date_range": f"{start_date} - {end_date}",
                    "opening_balance": period_data.get('opening_balance', 0),
                    "cash_received": period_data.get('cash_received', 0),
                    "cash_spent": period_data.get('cash_spent', 0),
                    "closing_balance": period_data.get('closing_balance', 0)
                }
                bank_info["periods"].append(period_info)
            
            connection_info["banks"].append(bank_info)
        
        response["connections"].append(connection_info)
    
    return response


def create_other_banks_sheet(ws, cashflow_data: Dict[str, Any], 
                            date_ranges: List[Tuple[str, str]], header_font, header_fill, 
                            header_alignment, title_font, title_alignment, border):
    """Create Other Banks sheet with BNZ, ICBC, CCB, and Kiwi Bank sections."""
    current_row = 1
    
    # Calculate table width based on date ranges
    # 3 fixed columns (Account Number, Account Name, Company) + 2 columns per date range
    table_width = 3 + (len(date_ranges) * 2)
    last_column = get_column_letter(table_width)
    
    # Title
    ws.merge_cells(f"A{current_row}:{last_column}{current_row}")
    ws[f"A{current_row}"] = "Other Banks Cash Flow Report"
    ws[f"A{current_row}"].font = title_font
    ws[f"A{current_row}"].alignment = Alignment("center")
    current_row += 1
    
    # Define the banks to include in "Other" sheet
    other_banks = ["BNZ", "ICBC", "CCB", "BOC", "Kiwi Bank", "Hua Xia Bank"]
    
    for bank_name in other_banks:
        # Check if we have data for this bank
        has_data = False
        for connection_name, connection_data in cashflow_data.items():
            for account_data in connection_data.get('accounts', []):
                if account_data.get('bank_name') == bank_name:
                    has_data = True
                    break
            if has_data:
                break
        
        if not has_data:
            continue
        
        # Bank section header
        ws[f"A{current_row}"] = bank_name
        ws[f"A{current_row}"].font = Font(bold=True, size=12)
        ws[f"A{current_row}"].alignment = Alignment("left")
        ws.merge_cells(f"A{current_row}:{last_column}{current_row}")
        current_row += 1
        
        # Date ranges header row
        ws[f"A{current_row}"] = "Account Number"
        ws[f"A{current_row}"].font = header_font
        ws[f"A{current_row}"].fill = header_fill
        ws[f"A{current_row}"].alignment = header_alignment
        ws[f"A{current_row}"].border = border
        
        ws[f"B{current_row}"] = "Account Name"
        ws[f"B{current_row}"].font = header_font
        ws[f"B{current_row}"].fill = header_fill
        ws[f"B{current_row}"].alignment = header_alignment
        ws[f"B{current_row}"].border = border
        
        ws[f"C{current_row}"] = "Company"
        ws[f"C{current_row}"].font = header_font
        ws[f"C{current_row}"].fill = header_fill
        ws[f"C{current_row}"].alignment = header_alignment
        ws[f"C{current_row}"].border = border
        
        # Add Balance column header that spans all periods
        balance_cols = len(date_ranges) * 2  # 2 columns per period (Opening, Available)
        start_col = get_column_letter(4)
        end_col = get_column_letter(3 + balance_cols)
        ws.merge_cells(f"{start_col}{current_row}:{end_col}{current_row}")
        ws[f"{start_col}{current_row}"] = "Balance"
        ws[f"{start_col}{current_row}"].font = header_font
        ws[f"{start_col}{current_row}"].fill = header_fill
        ws[f"{start_col}{current_row}"].alignment = header_alignment
        ws[f"{start_col}{current_row}"].border = border
        
        # Set column widths
        ws.column_dimensions['A'].width = 25  # Account Number
        ws.column_dimensions['B'].width = 25  # Account Name
        ws.column_dimensions['C'].width = 30  # Company Name
        
        # Set width for amount columns (D onwards)
        col_idx = 4
        for start_date, end_date in date_ranges:
            # Set width for each of the 2 amount columns per period
            ws.column_dimensions[get_column_letter(col_idx)].width = 15      # Opening
            ws.column_dimensions[get_column_letter(col_idx+1)].width = 15    # Available
            col_idx += 2
        
        current_row += 1
        
        # Sub-header row for Opening and Available balance
        ws[f"A{current_row}"] = ""
        ws[f"B{current_row}"] = ""
        ws[f"C{current_row}"] = ""
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            # Add period label
            date_range_label = format_date_range_for_excel(start_date, end_date)
            ws.merge_cells(f"{get_column_letter(col_idx)}{current_row}:{get_column_letter(col_idx+1)}{current_row}")
            ws[f"{get_column_letter(col_idx)}{current_row}"] = date_range_label
            ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx)}{current_row}"].alignment = Alignment("center")
            ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
            col_idx += 2
        
        current_row += 1
        
        # Third sub-header row for individual columns
        ws[f"A{current_row}"] = ""
        ws[f"B{current_row}"] = ""
        ws[f"C{current_row}"] = ""
        
        col_idx = 4
        for start_date, end_date in date_ranges:
            ws[f"{get_column_letter(col_idx)}{current_row}"] = "Opening"
            ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx)}{current_row}"].alignment = Alignment("center")
            ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
            
            ws[f"{get_column_letter(col_idx+1)}{current_row}"] = "Available"
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].alignment = Alignment("center")
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
            col_idx += 2
        
        current_row += 1
        
        # Data rows for this bank
        total_row = current_row
        
        # Process data for this specific bank
        # Accounts to exclude
        excluded_accounts = ["389026059757103", "389026059757102"]
        
        for connection_name, connection_data in cashflow_data.items():
            for account_data in connection_data.get('accounts', []):
                if account_data.get('bank_name') == bank_name:
                    # Skip excluded accounts
                    account_number_raw = account_data.get('account_number', '')
                    if account_number_raw in excluded_accounts:
                        continue
                        
                    account_number = format_account_number(account_number_raw)
                    
                    # Write account and connection name
                    ws[f"A{current_row}"] = account_number
                    ws[f"A{current_row}"].border = border
                    ws[f"B{current_row}"] = account_data.get('account_name', '')
                    ws[f"B{current_row}"].border = border
                    ws[f"C{current_row}"] = connection_name
                    ws[f"C{current_row}"].border = border
                    
                    # Write balance data for each date range
                    col_idx = 4
                    for start_date, end_date in date_ranges:
                        period_key = f"{start_date}_{end_date}"
                        period_data = account_data.get('periods', {}).get(period_key, {})
                        
                        opening_balance = period_data.get('opening_balance', 0)
                        closing_balance = period_data.get('closing_balance', 0)
                        
                        ws[f"{get_column_letter(col_idx)}{current_row}"] = float(opening_balance) if opening_balance else 0
                        ws[f"{get_column_letter(col_idx)}{current_row}"].number_format = '"$"#,##0.00'
                        ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                        
                        ws[f"{get_column_letter(col_idx+1)}{current_row}"] = float(closing_balance) if closing_balance else 0
                        ws[f"{get_column_letter(col_idx+1)}{current_row}"].number_format = '"$"#,##0.00'
                        ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
                        
                        col_idx += 2
                    
                    current_row += 1
        
        # Totals row for this bank
        if current_row > total_row:
            ws[f"A{current_row}"] = "Total"
            ws[f"A{current_row}"].font = Font(bold=True)
            ws[f"A{current_row}"].border = border
            ws[f"B{current_row}"] = ""
            ws[f"B{current_row}"].border = border
            ws[f"C{current_row}"] = ""
            ws[f"C{current_row}"].border = border
            
            # Calculate totals for each period
            col_idx = 4
            for start_date, end_date in date_ranges:
                opening_total = 0
                closing_total = 0
                
                # Sum up all values in the columns
                for row in range(total_row, current_row):
                    opening_val = ws[f"{get_column_letter(col_idx)}{row}"].value or 0
                    closing_val = ws[f"{get_column_letter(col_idx+1)}{row}"].value or 0
                    opening_total += opening_val
                    closing_total += closing_val
                
                ws[f"{get_column_letter(col_idx)}{current_row}"] = opening_total
                ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
                ws[f"{get_column_letter(col_idx)}{current_row}"].number_format = '"$"#,##0.00'
                ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                
                ws[f"{get_column_letter(col_idx+1)}{current_row}"] = closing_total
                ws[f"{get_column_letter(col_idx+1)}{current_row}"].font = Font(bold=True)
                ws[f"{get_column_letter(col_idx+1)}{current_row}"].number_format = '"$"#,##0.00'
                ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
                
                col_idx += 2
            
            current_row += 1
        
        # Add some spacing between bank sections
        current_row += 2
    
    # Auto-adjust row heights
    for row in ws.iter_rows():
        h = max(
            15,
            max(
                (len(str(c.value)) * 0.8) if c.value else 0
                for c in row
            )
        )
        ws.row_dimensions[row[0].row].height = min(50, h) 