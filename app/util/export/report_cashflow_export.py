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
    output_dir: str = "tmp"
) -> str:
    """
    Export CashFlow report data to Excel with multiple sheets.
    
    Args:
        cashflow_data: Dictionary containing cashflow data for all connections
        date_ranges: List of date ranges used in the report
        filename: Base filename for the Excel file
        output_dir: Directory to save the Excel file
    
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
    
    # Create Bank Balance Sheet (blank for now)
    create_bank_balance_sheet(bank_balance_sheet, title_font, title_alignment)
    
    # Create ASB and ANZ sheets
    create_bank_sheet(asb_sheet, "ASB", cashflow_data, date_ranges, 
                     header_font, header_fill, header_alignment, 
                     title_font, title_alignment, border)
    
    create_bank_sheet(anz_sheet, "ANZ", cashflow_data, date_ranges,
                     header_font, header_fill, header_alignment,
                     title_font, title_alignment, border)
    
    # Save file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"{filename}_{timestamp}.xlsx")
    wb.save(path)
    return path


def create_bank_balance_sheet(ws, title_font, title_alignment):
    """Create the Bank Balance Sheet (blank for now)."""
    ws["A1"] = "Bank Balance Sheet"
    ws["A1"].font = title_font
    ws["A1"].alignment = title_alignment
    ws.merge_cells("A1:Z1")


def create_bank_sheet(ws, bank_name: str, cashflow_data: Dict[str, Any], 
                     date_ranges: List[Tuple[str, str]], header_font, header_fill, 
                     header_alignment, title_font, title_alignment, border):
    """Create ASB or ANZ sheet with cashflow data."""
    current_row = 1
    
    # Title
    ws.merge_cells(f"A{current_row}:Z{current_row}")
    ws[f"A{current_row}"] = f"{bank_name} Cash Flow Report"
    ws[f"A{current_row}"].font = title_font
    ws[f"A{current_row}"].alignment = title_alignment
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
    
    ws[f"C{current_row}"] = "Connection Name"
    ws[f"C{current_row}"].font = header_font
    ws[f"C{current_row}"].fill = header_fill
    ws[f"C{current_row}"].alignment = header_alignment
    ws[f"C{current_row}"].border = border
    
    # Add date range columns
    col_idx = 4
    for start_date, end_date in date_ranges:
        date_range_label = format_date_range_for_excel(start_date, end_date)
        ws.merge_cells(f"{get_column_letter(col_idx)}{current_row}:{get_column_letter(col_idx+3)}{current_row}")
        ws[f"{get_column_letter(col_idx)}{current_row}"] = date_range_label
        ws[f"{get_column_letter(col_idx)}{current_row}"].font = header_font
        ws[f"{get_column_letter(col_idx)}{current_row}"].fill = header_fill
        ws[f"{get_column_letter(col_idx)}{current_row}"].alignment = header_alignment
        ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
        col_idx += 4
    
    # Set column widths
    ws.column_dimensions['A'].width = 25  # Account Number
    ws.column_dimensions['B'].width = 25  # Account Name
    ws.column_dimensions['C'].width = 30  # Connection Name
    
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
        ws[f"{get_column_letter(col_idx)}{current_row}"] = "Opening"
        ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
        ws[f"{get_column_letter(col_idx)}{current_row}"].alignment = Alignment("center")
        ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
        
        ws[f"{get_column_letter(col_idx+1)}{current_row}"] = "Cash Received"
        ws[f"{get_column_letter(col_idx+1)}{current_row}"].font = Font(bold=True)
        ws[f"{get_column_letter(col_idx+1)}{current_row}"].alignment = Alignment("center")
        ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
        
        ws[f"{get_column_letter(col_idx+2)}{current_row}"] = "Cash Spent"
        ws[f"{get_column_letter(col_idx+2)}{current_row}"].font = Font(bold=True)
        ws[f"{get_column_letter(col_idx+2)}{current_row}"].alignment = Alignment("center")
        ws[f"{get_column_letter(col_idx+2)}{current_row}"].border = border
        
        ws[f"{get_column_letter(col_idx+3)}{current_row}"] = "Available"
        ws[f"{get_column_letter(col_idx+3)}{current_row}"].font = Font(bold=True)
        ws[f"{get_column_letter(col_idx+3)}{current_row}"].alignment = Alignment("center")
        ws[f"{get_column_letter(col_idx+3)}{current_row}"].border = border
        col_idx += 4
    
    current_row += 1
    
    # Data rows
    total_row = current_row
    
    # Process data for this bank
    for connection_name, connection_data in cashflow_data.items():
        for account_data in connection_data.get('accounts', []):
            if account_data.get('bank_name') == bank_name:
                account_number = format_account_number(account_data.get('account_number', ''))
                
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
                    cash_received = period_data.get('cash_received', 0)
                    cash_spent = period_data.get('cash_spent', 0)
                    closing_balance = period_data.get('closing_balance', 0)
                    
                    ws[f"{get_column_letter(col_idx)}{current_row}"] = float(opening_balance) if opening_balance else 0
                    ws[f"{get_column_letter(col_idx)}{current_row}"].number_format = '"$"#,##0.00'
                    ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
                    
                    ws[f"{get_column_letter(col_idx+1)}{current_row}"] = float(cash_received) if cash_received else 0
                    ws[f"{get_column_letter(col_idx+1)}{current_row}"].number_format = '"$"#,##0.00'
                    ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
                    
                    ws[f"{get_column_letter(col_idx+2)}{current_row}"] = float(cash_spent) if cash_spent else 0
                    ws[f"{get_column_letter(col_idx+2)}{current_row}"].number_format = '"$"#,##0.00'
                    ws[f"{get_column_letter(col_idx+2)}{current_row}"].border = border
                    
                    ws[f"{get_column_letter(col_idx+3)}{current_row}"] = float(closing_balance) if closing_balance else 0
                    ws[f"{get_column_letter(col_idx+3)}{current_row}"].number_format = '"$"#,##0.00'
                    ws[f"{get_column_letter(col_idx+3)}{current_row}"].border = border
                    
                    col_idx += 4
                
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
            cash_received_total = 0
            cash_spent_total = 0
            closing_total = 0
            
            # Sum up all values in the columns
            for row in range(total_row, current_row):
                opening_val = ws[f"{get_column_letter(col_idx)}{row}"].value or 0
                cash_received_val = ws[f"{get_column_letter(col_idx+1)}{row}"].value or 0
                cash_spent_val = ws[f"{get_column_letter(col_idx+2)}{row}"].value or 0
                closing_val = ws[f"{get_column_letter(col_idx+3)}{row}"].value or 0
                opening_total += opening_val
                cash_received_total += cash_received_val
                cash_spent_total += cash_spent_val
                closing_total += closing_val
            
            ws[f"{get_column_letter(col_idx)}{current_row}"] = opening_total
            ws[f"{get_column_letter(col_idx)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx)}{current_row}"].number_format = '"$"#,##0.00'
            ws[f"{get_column_letter(col_idx)}{current_row}"].border = border
            
            ws[f"{get_column_letter(col_idx+1)}{current_row}"] = cash_received_total
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].number_format = '"$"#,##0.00'
            ws[f"{get_column_letter(col_idx+1)}{current_row}"].border = border
            
            ws[f"{get_column_letter(col_idx+2)}{current_row}"] = cash_spent_total
            ws[f"{get_column_letter(col_idx+2)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx+2)}{current_row}"].number_format = '"$"#,##0.00'
            ws[f"{get_column_letter(col_idx+2)}{current_row}"].border = border
            
            ws[f"{get_column_letter(col_idx+3)}{current_row}"] = closing_total
            ws[f"{get_column_letter(col_idx+3)}{current_row}"].font = Font(bold=True)
            ws[f"{get_column_letter(col_idx+3)}{current_row}"].number_format = '"$"#,##0.00'
            ws[f"{get_column_letter(col_idx+3)}{current_row}"].border = border
            
            col_idx += 4
    

    
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
    excel_file_path: str
) -> Dict[str, Any]:
    """
    Generate JSON response for CashFlow report.
    
    Args:
        cashflow_data: Dictionary containing cashflow data
        date_ranges: List of date ranges used in the report
        excel_file_path: Path to the generated Excel file
    
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
        }
    }
    
    # Process each connection
    for connection_name, connection_data in cashflow_data.items():
        connection_info = {
            "connection_name": connection_name,
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