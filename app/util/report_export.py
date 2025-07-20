import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def generate_system_comments(invoice_details: Dict[str, List[Dict]], bucket_names: List[str]) -> str:
    """
    Generate system comments based on invoice details for each aging bucket.
    
    Args:
        invoice_details: Dictionary containing invoice details for each bucket
        bucket_names: List of bucket names (aging periods)
    
    Returns:
        Formatted string with comments for each bucket
    """
    comments = []
    
    for bucket_name in bucket_names:
        bucket_items = invoice_details.get(bucket_name, [])
        if bucket_items:
            # Add period header
            comments.append(f"{bucket_name}:")
            for item in bucket_items:
                item_number = item.get('item_number', 'Unknown')
                amount = item.get('amount', 0)
                is_negative = item.get('is_negative', False)
                item_type = item.get('item_type', 'invoice')
                
                # Format based on item type
                if item_type == "credit_note":
                    if is_negative:
                        comments.append(f"{item_number} (Credit Note) - {amount:,.2f}")
                    else:
                        comments.append(f"{item_number} (Credit Note) - {amount:,.2f}")
                elif item_type == "bank_transaction":
                    if is_negative:
                        comments.append(f"{item_number} (Bank Overpayment) - {amount:,.2f}")
                    else:
                        comments.append(f"{item_number} (Bank Transaction) - {amount:,.2f}")
                else:
                    # For invoices and other items
                    if is_negative:
                        if item_number == "Invoice Overpayments":
                            comments.append(f"Invoice Overpayments (Paid upfront for future invoices) - {amount:,.2f}")
                        else:
                            comments.append(f"{item_number} (Credit/Overpayment) - {amount:,.2f}")
                    else:
                        comments.append(f"{item_number} - {amount:,.2f}")
            comments.append("")  # Add empty line between buckets
    
    final_comments = "\n".join(comments) if comments else ""
    return final_comments


def export_report_to_excel(
    data: List[Dict[str, Any]],
    columns: List[Dict[str, str]],
    filename: str,
    sheet_name: str = "Report",
    title: Optional[str] = None,
    organization_name: Optional[str] = None,
    report_date: Optional[str] = None,
    output_dir: str = "tmp",
    include_totals: bool = True,
    include_percentages: bool = True
) -> str:
    """
    Generic function to export report data to Excel with formatting.
    
    Args:
        data: List of dictionaries containing the report data
        columns: List of column definitions with keys:
                 - 'header': Display name for the column header
                 - 'key': Key in the data dictionary to extract value
                 - 'width': Optional column width (default: 15)
                 - 'format': Optional format type ('currency', 'percentage', 'date', 'number')
        filename: Name of the Excel file (without extension)
        sheet_name: Name of the worksheet
        title: Optional title to add at the top of the sheet
        output_dir: Directory to save the Excel file
        include_totals: Whether to add totals row at the bottom
        include_percentages: Whether to add percentage row after totals
        organization_name: Name of the organization/company
        report_date: Date for the report (e.g., "As at 31 July 2025")
    
    Returns:
        str: Full path to the created Excel file
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a new workbook and select the active sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    
    # Define styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    title_font = Font(bold=True, size=14)
    title_alignment = Alignment(horizontal="center")
    
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    current_row = 1
    
    # Add title if provided
    if title:
        ws.merge_cells(f'A1:{get_column_letter(len(columns))}1')
        ws['A1'] = title
        ws['A1'].font = title_font
        ws['A1'].alignment = title_alignment
        current_row = 2
    
    # Add organization name if provided
    if organization_name:
        ws.merge_cells(f'A{current_row}:{get_column_letter(len(columns))}{current_row}')
        ws[f'A{current_row}'] = organization_name
        ws[f'A{current_row}'].font = Font(bold=True, size=12)
        ws[f'A{current_row}'].alignment = Alignment(horizontal="center")
        current_row += 1
    
    # Add report date if provided
    if report_date:
        ws.merge_cells(f'A{current_row}:{get_column_letter(len(columns))}{current_row}')
        ws[f'A{current_row}'] = report_date
        ws[f'A{current_row}'].font = Font(size=11)
        ws[f'A{current_row}'].alignment = Alignment(horizontal="center")
        current_row += 1
    
    # Add "Ageing by due date" subtitle
    ws.merge_cells(f'A{current_row}:{get_column_letter(len(columns))}{current_row}')
    ws[f'A{current_row}'] = "Ageing by due date"
    ws[f'A{current_row}'].font = Font(size=11)
    ws[f'A{current_row}'].alignment = Alignment(horizontal="center")
    current_row += 1
    
    # Add headers
    for col_idx, column in enumerate(columns, 1):
        cell = ws.cell(row=current_row, column=col_idx)
        cell.value = column['header']
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = border
        
        # Set column width
        width = column.get('width', 15)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    current_row += 1
    
    # Write data rows
    for row_idx, row_data in enumerate(data, start=current_row + 1):
        for col_idx, column in enumerate(columns, start=1):
            cell_value = row_data.get(column['key'], '')
            
            cell = ws.cell(row=row_idx, column=col_idx)
            
            # Apply formatting based on column type
            format_type = column.get('format')
            if format_type == 'currency' and isinstance(cell_value, (int, float)):
                cell.number_format = '"$"#,##0.00'
                cell.value = cell_value
            elif format_type == 'percentage' and isinstance(cell_value, (int, float)):
                cell.number_format = '0.00%'
                cell.value = cell_value / 100 if cell_value > 1 else cell_value
            elif format_type == 'date':
                if hasattr(cell_value, 'strftime'):
                    cell.value = cell_value
                    cell.number_format = 'dd/mm/yyyy'
                else:
                    cell.value = cell_value
            elif format_type == 'number' and isinstance(cell_value, (int, float)):
                cell.number_format = '#,##0.00'
                cell.value = cell_value
            else:
                cell.value = cell_value
            
            # Special formatting for System Comments column
            if column['key'] == 'System Comments' and isinstance(cell_value, str) and cell_value:
                # Set text wrapping and alignment for better readability
                cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                # Ensure the cell is visible and properly sized
                cell.font = Font(size=10)
                # Set a minimum row height for System Comments
                if row_idx > current_row:  # Skip header row
                    ws.row_dimensions[row_idx].height = max(60, len(cell_value.split('\n')) * 15)
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            
            cell.border = border
    
    # Add totals row if requested
    if include_totals and data:
        totals_row = current_row
        current_row += 1
        
        # Calculate totals for each column
        column_totals = {}
        for column in columns:
            key = column['key']
            if key not in ('Contact', 'Comments', 'System Comments'):  # Skip non-numeric columns
                total = sum(row_data.get(key, 0) for row_data in data if isinstance(row_data.get(key), (int, float)))
                column_totals[key] = total
        
        # Add totals row
        for col_idx, column in enumerate(columns, 1):
            cell = ws.cell(row=totals_row, column=col_idx)
            
            if column['key'] == 'Business Unit':
                cell.value = "Total"
                cell.font = Font(bold=True)
            elif column['key'] in ('Company', 'Contact', 'Comments', 'System Comments'):
                cell.value = ""
            else:
                value = column_totals.get(column['key'], 0)
                cell.value = value
                cell.font = Font(bold=True)
                
                # Apply formatting
                format_type = column.get('format')
                if format_type == 'currency' and isinstance(value, (int, float)):
                    cell.number_format = '"$"#,##0.00'
                elif format_type == 'percentage' and isinstance(value, (int, float)):
                    cell.number_format = '0.00%'
                elif format_type == 'number' and isinstance(value, (int, float)):
                    cell.number_format = '#,##0.00'
            
            cell.border = border
            cell.alignment = Alignment(horizontal="left", vertical="center")
    
    # Add percentages row if requested
    if include_percentages and data and include_totals:
        percentages_row = current_row
        current_row += 1
        
        # Calculate grand total for percentage calculation (use the "Total" column)
        grand_total = column_totals.get('Total', 0)
        
        # Add percentages row
        for col_idx, column in enumerate(columns, 1):
            cell = ws.cell(row=percentages_row, column=col_idx)
            
            if column['key'] == 'Business Unit':
                cell.value = "Percentage"
                cell.font = Font(bold=True)
            elif column['key'] in ('Comments', 'System Comments'):
                cell.value = ""
            elif column['key'] == 'Total':
                cell.value = 1.0  # 100% for the Total column
                cell.font = Font(bold=True)
                cell.number_format = '0.00%'
            else:
                total = column_totals.get(column['key'], 0)
                if grand_total > 0:
                    percentage = (total / grand_total)
                else:
                    percentage = 0
                cell.value = percentage
                cell.font = Font(bold=True)
                cell.number_format = '0.00%'
            
            cell.border = border
            cell.alignment = Alignment(horizontal="left", vertical="center")
    
    # Auto-adjust row heights
    for row in ws.iter_rows():
        max_height = 0
        for cell in row:
            if cell.value:
                # Estimate height based on content length
                content_length = len(str(cell.value))
                estimated_height = max(15, min(50, content_length * 0.8))
                max_height = max(max_height, estimated_height)
        if max_height > 0:
            ws.row_dimensions[row[0].row].height = max_height
    
    # Save the workbook
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(output_dir, f"{filename}_{timestamp}.xlsx")
    wb.save(file_path)
    
    return file_path


def format_currency(value: float) -> str:
    """Helper function to format currency values."""
    return f"${value:,.2f}"


def format_percentage(value: float) -> str:
    """Helper function to format percentage values."""
    return f"{value:.2f}%" 