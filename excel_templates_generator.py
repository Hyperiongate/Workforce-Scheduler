# excel_templates_generator.py
# Save this file in your project root or utils folder

import pandas as pd
import io
from datetime import datetime, date, timedelta
from flask import send_file
import xlsxwriter

def create_employee_import_template():
    """Create comprehensive employee import template with instructions"""
    
    # Create template data structure
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'First Name': ['John', 'Jane', 'Bob'],
        'Last Name': ['Smith', 'Doe', 'Johnson'],
        'Email': ['john.smith@company.com', 'jane.doe@company.com', 'bob.johnson@company.com'],
        'Crew': ['A', 'B', 'C'],
        'Position': ['Operator', 'Supervisor', 'Technician'],
        'Department': ['Production', 'Production', 'Maintenance'],
        'Hire Date': ['2020-01-15', '2019-06-20', '2021-03-10'],
        'Phone': ['555-0101', '555-0102', '555-0103'],
        'Emergency Contact': ['Mary Smith', 'John Doe', 'Alice Johnson'],
        'Emergency Phone': ['555-9101', '555-9102', '555-9103'],
        'Skills': ['Forklift,Safety,First Aid', 'Leadership,Safety,Training', 'Electrical,Mechanical,Welding']
    }
    
    # Instructions for the template
    instructions = [
        "EMPLOYEE IMPORT TEMPLATE INSTRUCTIONS",
        "",
        "1. REQUIRED FIELDS:",
        "   - Employee ID: Unique identifier for each employee",
        "   - First Name & Last Name: Employee's full name",
        "   - Email: Must be unique for each employee",
        "   - Crew: Must be A, B, C, or D",
        "   - Position: Job title/role",
        "",
        "2. DATE FORMAT:",
        "   - Use YYYY-MM-DD format (e.g., 2023-12-31)",
        "",
        "3. SKILLS:",
        "   - List multiple skills separated by commas",
        "   - No spaces after commas",
        "",
        "4. IMPORTANT NOTES:",
        "   - Do not modify column headers",
        "   - Delete the example rows before importing your data",
        "   - Save as .xlsx format",
        "   - Maximum 1000 employees per upload",
        "",
        "5. CREW ASSIGNMENTS:",
        "   - Crews A & B typically work day shifts",
        "   - Crews C & D typically work night shifts",
        "   - Ensure balanced crew sizes (approximately 25% each)",
        "",
        "6. DATA VALIDATION:",
        "   - Employee IDs must be unique",
        "   - Emails must be valid format and unique",
        "   - Crew must be exactly A, B, C, or D",
        "   - Dates must be in correct format"
    ]
    
    # Validation rules
    validation_rules = {
        'Employee ID': 'Required, Unique, Max 20 characters',
        'First Name': 'Required, Max 50 characters',
        'Last Name': 'Required, Max 50 characters', 
        'Email': 'Required, Unique, Valid email format',
        'Crew': 'Required, Must be A, B, C, or D',
        'Position': 'Required, Max 100 characters',
        'Department': 'Optional, Max 100 characters',
        'Hire Date': 'Optional, Format: YYYY-MM-DD',
        'Phone': 'Optional, Max 20 characters',
        'Emergency Contact': 'Optional, Max 100 characters',
        'Emergency Phone': 'Optional, Max 20 characters',
        'Skills': 'Optional, Comma-separated list'
    }
    
    # Create Excel file with multiple sheets
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Get workbook and add formats
        workbook = writer.book
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4CAF50',
            'font_color': 'white',
            'border': 1
        })
        example_format = workbook.add_format({
            'bg_color': '#E8F5E9',
            'border': 1
        })
        
        # Sheet 1: Instructions
        df_instructions = pd.DataFrame(instructions, columns=['Instructions'])
        df_instructions.to_excel(writer, sheet_name='Instructions', index=False)
        worksheet_inst = writer.sheets['Instructions']
        worksheet_inst.set_column('A:A', 80)
        
        # Sheet 2: Validation Rules
        df_validation = pd.DataFrame(list(validation_rules.items()), 
                                   columns=['Field', 'Validation Rules'])
        df_validation.to_excel(writer, sheet_name='Validation Rules', index=False)
        worksheet_val = writer.sheets['Validation Rules']
        worksheet_val.set_column('A:A', 20)
        worksheet_val.set_column('B:B', 50)
        
        # Sheet 3: Employee Data Template
        df_template = pd.DataFrame(template_data)
        df_template.to_excel(writer, sheet_name='Employee Data', index=False)
        worksheet = writer.sheets['Employee Data']
        
        # Format the template sheet
        for col_num, col_name in enumerate(df_template.columns):
            worksheet.write(0, col_num, col_name, header_format)
            
        # Set column widths
        column_widths = {
            'A:A': 15,  # Employee ID
            'B:B': 15,  # First Name
            'C:C': 15,  # Last Name
            'D:D': 30,  # Email
            'E:E': 10,  # Crew
            'F:F': 20,  # Position
            'G:G': 20,  # Department
            'H:H': 15,  # Hire Date
            'I:I': 15,  # Phone
            'J:J': 25,  # Emergency Contact
            'K:K': 15,  # Emergency Phone
            'L:L': 40   # Skills
        }
        
        for col_range, width in column_widths.items():
            worksheet.set_column(col_range, width)
            
        # Add data validation for Crew column
        worksheet.data_validation('E2:E1000', {
            'validate': 'list',
            'source': ['A', 'B', 'C', 'D'],
            'error_title': 'Invalid Crew',
            'error_message': 'Crew must be A, B, C, or D'
        })
        
        # Format example rows
        for row in range(1, 4):
            for col in range(12):
                worksheet.write(row, col, template_data[list(template_data.keys())[col]][row-1], example_format)
    
    output.seek(0)
    return output


def create_overtime_history_template():
    """Create 13-week overtime history import template"""
    
    # Generate 13 weeks of dates starting from current week
    current_date = datetime.now().date()
    current_monday = current_date - timedelta(days=current_date.weekday())
    
    # Example data for 3 employees
    example_data = []
    employee_ids = ['EMP001', 'EMP002', 'EMP003']
    employee_names = ['John Smith', 'Jane Doe', 'Bob Johnson']
    
    for i, (emp_id, emp_name) in enumerate(zip(employee_ids, employee_names)):
        for week_num in range(13):
            week_start = current_monday - timedelta(weeks=week_num)
            week_end = week_start + timedelta(days=6)
            
            # Generate realistic overtime hours (0-20 hours per week)
            regular_hours = 40
            overtime_hours = round((8 + (i * 2) + (week_num % 3) * 2) * 0.8, 1)
            total_hours = regular_hours + overtime_hours
            
            example_data.append({
                'Employee ID': emp_id,
                'Employee Name': emp_name,
                'Week Start Date': week_start.strftime('%Y-%m-%d'),
                'Week End Date': week_end.strftime('%Y-%m-%d'),
                'Regular Hours': regular_hours,
                'Overtime Hours': overtime_hours,
                'Total Hours': total_hours,
                'Notes': f'Week {13-week_num}'
            })
    
    # Instructions
    instructions = [
        "OVERTIME HISTORY IMPORT TEMPLATE INSTRUCTIONS",
        "",
        "1. PURPOSE:",
        "   Import 13 weeks of overtime history for all employees",
        "",
        "2. REQUIRED FIELDS:",
        "   - Employee ID: Must match existing employee IDs in the system",
        "   - Week Start Date: Monday of each week (YYYY-MM-DD format)",
        "   - Regular Hours: Standard hours worked (typically 40)",
        "   - Overtime Hours: Hours worked beyond regular hours",
        "",
        "3. DATA REQUIREMENTS:",
        "   - Include exactly 13 weeks of data per employee",
        "   - Weeks should be consecutive, starting from most recent",
        "   - Week Start Date must be a Monday",
        "",
        "4. CALCULATION NOTES:",
        "   - Total Hours = Regular Hours + Overtime Hours",
        "   - System will validate this calculation",
        "",
        "5. IMPORT BEHAVIOR:",
        "   - This will REPLACE existing overtime history",
        "   - All employees must have 13 weeks of data",
        "   - Missing employees will have zero overtime recorded",
        "",
        "6. TIPS:",
        "   - Export current employees first to get correct Employee IDs",
        "   - Use Excel formulas to calculate dates and totals",
        "   - Maximum 10,000 rows per upload (13 weeks × ~750 employees)"
    ]
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#2196F3',
            'font_color': 'white',
            'border': 1
        })
        date_format = workbook.add_format({
            'num_format': 'yyyy-mm-dd',
            'border': 1
        })
        number_format = workbook.add_format({
            'num_format': '0.0',
            'border': 1
        })
        
        # Sheet 1: Instructions
        df_instructions = pd.DataFrame(instructions, columns=['Instructions'])
        df_instructions.to_excel(writer, sheet_name='Instructions', index=False)
        worksheet_inst = writer.sheets['Instructions']
        worksheet_inst.set_column('A:A', 80)
        
        # Sheet 2: Overtime Data
        df_overtime = pd.DataFrame(example_data)
        df_overtime.to_excel(writer, sheet_name='Overtime History', index=False)
        worksheet = writer.sheets['Overtime History']
        
        # Format headers
        for col_num, col_name in enumerate(df_overtime.columns):
            worksheet.write(0, col_num, col_name, header_format)
        
        # Set column widths and formats
        worksheet.set_column('A:A', 15)  # Employee ID
        worksheet.set_column('B:B', 20)  # Employee Name
        worksheet.set_column('C:D', 15)  # Dates
        worksheet.set_column('E:G', 15)  # Hours
        worksheet.set_column('H:H', 30)  # Notes
        
        # Add conditional formatting for high overtime (>15 hours)
        worksheet.conditional_format('F2:F10000', {
            'type': 'cell',
            'criteria': '>',
            'value': 15,
            'format': workbook.add_format({'bg_color': '#FFEB3B'})
        })
        
        # Add a summary sheet
        summary_data = {
            'Metric': ['Total Employees', 'Total Weeks', 'Average Weekly OT', 'Max Weekly OT', 'Total OT Hours'],
            'Value': [3, 13, 8.5, 12.0, 331.5],
            'Notes': ['Unique employees in dataset', 'Should be 13 for each employee', 
                     'Average across all employees/weeks', 'Highest single week', 
                     'Sum of all overtime hours']
        }
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Import Summary', index=False)
        worksheet_summary = writer.sheets['Import Summary']
        worksheet_summary.set_column('A:A', 20)
        worksheet_summary.set_column('B:B', 15)
        worksheet_summary.set_column('C:C', 40)
    
    output.seek(0)
    return output


def create_bulk_update_template(template_type='employee'):
    """Create template for bulk updates of existing data"""
    
    if template_type == 'employee':
        # Employee update template
        update_fields = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
            'Action': ['UPDATE', 'UPDATE', 'DELETE'],
            'First Name': ['John', 'Jane', ''],
            'Last Name': ['Smith', 'Doe-Johnson', ''],
            'Email': ['john.smith@company.com', 'jane.johnson@company.com', ''],
            'Crew': ['B', 'B', ''],
            'Position': ['Senior Operator', 'Supervisor', ''],
            'Department': ['Production', 'Production', ''],
            'Phone': ['555-0101', '555-0102-NEW', ''],
            'Skills': ['Forklift,Safety,First Aid,Training', 'Leadership,Safety,Training,Budget', '']
        }
        
        instructions = [
            "BULK UPDATE TEMPLATE - EMPLOYEES",
            "",
            "ACTION TYPES:",
            "  UPDATE - Modify existing employee data",
            "  DELETE - Remove employee from system",
            "  NEW    - Add new employee (include all required fields)",
            "",
            "RULES:",
            "  - Employee ID is required and must exist (except for NEW)",
            "  - Leave fields blank to keep existing values",
            "  - For DELETE action, only Employee ID is needed",
            "  - Updates are processed in order listed"
        ]
        
    elif template_type == 'overtime':
        # Overtime adjustment template
        update_fields = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
            'Week Start Date': ['2024-01-01', '2024-01-01', '2024-01-08'],
            'Action': ['UPDATE', 'ADD', 'DELETE'],
            'Regular Hours': [40, 40, ''],
            'Overtime Hours': [12.5, 8.0, ''],
            'Total Hours': [52.5, 48.0, ''],
            'Adjustment Reason': ['Correction - missed clock out', 'Previously unrecorded', 'Duplicate entry']
        }
        
        instructions = [
            "BULK UPDATE TEMPLATE - OVERTIME",
            "",
            "ACTION TYPES:",
            "  UPDATE - Modify existing overtime record",
            "  ADD    - Add new overtime record", 
            "  DELETE - Remove overtime record",
            "",
            "RULES:",
            "  - Employee ID and Week Start Date identify the record",
            "  - Week Start Date must be a Monday",
            "  - Total Hours must equal Regular + Overtime",
            "  - Include reason for audit trail"
        ]
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Instructions sheet
        df_instructions = pd.DataFrame(instructions, columns=['Instructions'])
        df_instructions.to_excel(writer, sheet_name='Instructions', index=False)
        
        # Data sheet
        df_data = pd.DataFrame(update_fields)
        df_data.to_excel(writer, sheet_name='Bulk Updates', index=False)
        
        # Format
        workbook = writer.book
        worksheet = writer.sheets['Bulk Updates']
        
        # Add data validation for Action column
        action_col = list(update_fields.keys()).index('Action')
        worksheet.data_validation(f'{chr(65+action_col)}2:{chr(65+action_col)}1000', {
            'validate': 'list',
            'source': ['UPDATE', 'DELETE', 'NEW', 'ADD'],
            'error_title': 'Invalid Action',
            'error_message': 'Action must be UPDATE, DELETE, NEW, or ADD'
        })
    
    output.seek(0)
    return output
