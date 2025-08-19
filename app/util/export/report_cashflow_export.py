import os
import json
from pathlib import Path
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
        
        # Sort connections by company name (tenant_name) in ascending order
        connections = sorted(connections, key=lambda x: x.tenant_name.strip())
        
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
        
        # Add report title
        ws[f"A{current_row}"] = f"Cash balance report - {cash_summary['report_date']}"
        ws[f"A{current_row}"].font = Font(bold=True, size=16)
        ws[f"A{current_row}"].alignment = Alignment("center")
        ws.merge_cells(f"A{current_row}:I{current_row}")
        current_row += 1
        
        # Add signature lines in the same column
        ws[f"A{current_row}"] = "Prepared by: AI / Sophie Lee"
        ws[f"A{current_row}"].font = Font(bold=True)
        ws[f"A{current_row}"].alignment = Alignment("center")
        ws.merge_cells(f"A{current_row}:I{current_row}")
        current_row += 1
        
        ws[f"A{current_row}"] = "Reviewed by: Financial Controller"
        ws[f"A{current_row}"].font = Font(bold=True)
        ws[f"A{current_row}"].alignment = Alignment("center")
        ws.merge_cells(f"A{current_row}:I{current_row}")
        current_row += 1
        
        ws[f"A{current_row}"] = "Approved by: Financial Controller"
        ws[f"A{current_row}"].font = Font(bold=True)
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
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["fully_owned"] - cash_summary["periods"][previous_period]["fully_owned"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(color="FF0000")  # Red text
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
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["partially_owned"] - cash_summary["periods"][previous_period]["partially_owned"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(color="FF0000")  # Red text
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
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["total_available_cash"] - cash_summary["periods"][previous_period]["total_available_cash"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                cell.font = Font(bold=True)
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(bold=True, color="FF0000")  # Red text
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
        
        if len(date_ranges) > 1:
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
            # Add red formatting for negative values
            if period_summary["minimum_cash_holding_excess"] < 0:
                cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                cell.font = Font(bold=True, color="FF0000")  # Red text
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["minimum_cash_holding_excess"] - cash_summary["periods"][previous_period]["minimum_cash_holding_excess"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.font = Font(bold=True)
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(bold=True, color="FF0000")  # Red text

        # Add new column data
        if len(date_ranges) > 1:
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
            # Add red formatting for negative values
            if period_summary["total_available_cash"] < 0:
                cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                cell.font = Font(color="FF0000")  # Red text
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["total_available_cash"] - cash_summary["periods"][previous_period]["total_available_cash"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(color="FF0000")  # Red text
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
            # Add red formatting for negative values
            if period_summary["total_with_term_deposit"] < 0:
                cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                cell.font = Font(bold=True, color="FF0000")  # Red text
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["total_available_cash"] - cash_summary["periods"][previous_period]["total_available_cash"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                cell.font = Font(bold=True)
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(bold=True, color="FF0000")  # Red text
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
        if len(date_ranges) > 1:
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
            cell.value = period_summary["not_owned"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            if period_summary["not_owned"] < 0:
                cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                cell.font = Font(color="FF0000")  # Red text
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["not_owned"] - cash_summary["periods"][previous_period]["not_owned"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(color="FF0000")  # Red text
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
            cell.value = period_summary["final_cash_balance"]
            cell.number_format = '"$"#,##0.00'
            cell.border = border
            cell.font = Font(bold=True)
            if period_summary["final_cash_balance"] < 0:
                cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                cell.font = Font(color="FF0000")  # Red text
            col_idx += 1
        
        # Add difference column if multiple periods
        if len(date_ranges) > 1:
            periods_list = list(cash_summary["periods"].keys())
            if len(periods_list) >= 2:
                latest_period = periods_list[0]
                previous_period = periods_list[1]
                difference = cash_summary["periods"][latest_period]["final_cash_balance"] - cash_summary["periods"][previous_period]["final_cash_balance"]
                cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                cell.value = difference
                cell.number_format = '"$"#,##0.00'
                cell.border = border
                cell.font = Font(bold=True)
                # Add red formatting for negative values
                if difference < 0:
                    cell.fill = PatternFill("solid", fgColor="FFE6E6")  # Soft red background
                    cell.font = Font(bold=True, color="FF0000")  # Red text
                col_idx += 1
            
        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
        cell.value = "Total Cash"
        cell.border = border
        cell.alignment = Alignment(wrap_text=True)
        cell.font = Font(bold=True)
        
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
            
            # Sort connections by company name (tenant_name) in ascending order
            connections_in_group = sorted(connections_in_group, key=lambda x: x.tenant_name.strip())
            
            # Group connections by bank (ASB, ANZ, etc.)
            bank_groups = {}
            
            for connection in connections_in_group:
                connection_name = connection.tenant_name
                if connection_name in cashflow_data:
                    for account_data in cashflow_data[connection_name].get('accounts', []):
                        bank_name = account_data.get('bank_name', 'Unknown')
                        if bank_name not in bank_groups:
                            bank_groups[bank_name] = []
                        bank_groups[bank_name].append({
                            'connection': connection,
                            'account_data': account_data
                        })
            
            # Process each bank group (sorted by bank name for consistent ordering)
            for bank_name, bank_accounts in sorted(bank_groups.items()):
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

                # Merge and write Spent header (immediately after Balance)
                spent_cols = ["GST Payment", "Interest Payment", "Loan Payment", "Payroll", "Rates", "Others", "GST Refund"]
                spent_start_idx = 4 + balance_cols
                spent_end_idx = spent_start_idx + len(spent_cols) - 1
                spent_start_col = get_column_letter(spent_start_idx)
                spent_end_col = get_column_letter(spent_end_idx)
                ws.merge_cells(f"{spent_start_col}{current_row}:{spent_end_col}{current_row}")
                cell = ws[f"{spent_start_col}{current_row}"]
                cell.value = "Spent"
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = border

                # Merge and write Received header (immediately after Balance)
                received_cols = ["Income", "Rental Income"]
                received_start_idx = spent_end_idx + 1
                received_end_idx   = received_start_idx + len(received_cols) - 1
                received_start_col = get_column_letter(received_start_idx)
                received_end_col = get_column_letter(received_end_idx)
                ws.merge_cells(f"{received_start_col}{current_row}:{received_end_col}{current_row}")
                cell = ws[f"{received_start_col}{current_row}"]
                cell.value = "Received"
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
                for col_idx, header in enumerate(additional_headers, received_end_idx + 1):
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

                for val in spent_cols:
                    cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                    cell.value = val
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = header_fill
                    cell.alignment = Alignment("center")
                    cell.border = border
                    col_idx += 1

                for val in received_cols:
                    cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                    cell.value = val
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

                    for _ in spent_cols:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = 0
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1

                    for _ in received_cols:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = 0
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1
                    
                    # Add additional columns
                    min_balance_from_json = ""
                    try:
                        # Try multiple approaches to find the JSON file
                        json_file_path = None
                        cwd = os.getcwd()
                        account_balance_json_path = Path(cwd) / "data" / "min_account_balance_by_account.json"
                        if account_balance_json_path.exists():
                            json_file_path = account_balance_json_path
                        
                        if json_file_path and json_file_path.exists():
                            with open(json_file_path, 'r') as f:
                                min_balance_data = json.load(f)
                                account_number = account_data.get('account_number', '')
                                if account_number:
                                    # Remove dashes from account number to match JSON format
                                    clean_account_number = account_number.replace('-', '')
                                    
                                    # Search through all tenant accounts for this account number
                                    for tenant_id, tenant_accounts in min_balance_data.items():
                                        if clean_account_number in tenant_accounts:
                                            min_balance_from_json = tenant_accounts[clean_account_number]
                                            break
                    except Exception as e:
                        print(f"Error reading JSON: {e}")
                        print(f"Falling back to database min_balance values")
                        min_balance_from_json = ""
                    
                    ws[f"{get_column_letter(col_idx)}{current_row}"] = min_balance_from_json
                    ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                    # Format as currency if there's a value
                    if min_balance_from_json:
                        ws[f"{get_column_letter(col_idx)}{current_row}"].number_format = '"$"#,##0.00'
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

                    for _ in spent_cols:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = 0
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1

                    for _ in received_cols:
                        cell = ws[f"{get_column_letter(col_idx)}{current_row}"]
                        cell.value = 0
                        cell.number_format = '"$"#,##0.00'
                        cell.border = border
                        col_idx += 1
                    
                    # Add blank columns for totals
                    for _ in range(3):  # Minimum Balance, Next due date, Payment amount
                        ws[f"{get_column_letter(col_idx)}{current_row}"] = ""
                        ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                        col_idx += 1
                    
                    current_row += 1
                
                # Add spacing between banks
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
        for i in range(4 + balance_cols, 4 + balance_cols + 12):
            ws.column_dimensions[get_column_letter(i)].width = 20
        
    finally:
        session.close()

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
    for connection_name, connection_data in cashflow_data.items():
        connection_id = connection_data.get('connection_id', None)
        connection_info = {
            "connection_name": connection_name,
            "connection_id": connection_id,
            "banks": []
        }
        
        # Process each bank account
        for account_data in connection_data.get('accounts', []):
            bank_info = {
                "bank_name": account_data.get('bank_name'),
                "account_number": format_account_number(account_data.get('account_number', '')),
                "periods": []
            }
            
            # Process each period
            for key, (start_date, end_date) in enumerate(date_ranges):
                period_key = f"{start_date}_{end_date}"
                period_data = account_data.get('periods', {}).get(period_key, {})
                
                period_info = {
                    "date_range": f"{start_date} - {end_date}",
                    "opening_balance": period_data.get('opening_balance', 0),
                    "cash_received": period_data.get('cash_received', 0),
                    "cash_spent": period_data.get('cash_spent', 0),
                    "closing_balance": period_data.get('closing_balance', 0),
                    "spent": account_data.get('spent', {}),
                    "received": account_data.get('received', {})
                }
                bank_info["periods"].append(period_info)
            
            connection_info["banks"].append(bank_info)
        
        response["connections"].append(connection_info)
    
    return response