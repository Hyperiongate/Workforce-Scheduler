#!/usr/bin/env python3
"""
TEST DATA GENERATOR for Excel Upload System
COMPLETE TESTING SCRIPT - Run this to create test files
DATE: 2025-09-20
PURPOSE: Generate comprehensive test Excel files for your upload system
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import os

def create_test_files():
    """Create all test Excel files for the upload system"""
    
    print("Creating test Excel files for upload system...")
    
    # ==========================================
    # 1. VALID EMPLOYEE DATA - HEADER-BASED QUALIFICATIONS
    # ==========================================
    
    print("1. Creating valid employee data file...")
    
    # Using YOUR exact headers from the system
    valid_employee_data = {
        'Last Name': ['Smith', 'Johnson', 'Williams', 'Brown', 'Davis'],
        'First Name': ['John', 'Sarah', 'Michael', 'Emily', 'Robert'],
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'Crew Assigned': ['A', 'B', 'C', 'D', 'A'],
        'Current Job Position': ['Operator', 'Lead Operator', 'Technician', 'Supervisor', 'Maintenance'],
        'Email': [
            'john.smith@company.com',
            'sarah.johnson@company.com', 
            'mike.williams@company.com',
            'emily.brown@company.com',
            'robert.davis@company.com'
        ],
        # Qualification columns - headers define the skills
        'OSHA 10 Certification': ['Yes', 'Yes', 'No', 'Yes', 'No'],
        'Forklift License': ['Yes', 'No', 'Yes', 'No', 'Yes'],
        'First Aid Certified': ['No', 'Yes', 'Yes', 'Yes', 'No'],
        'Crane Operator': ['No', 'No', 'Yes', 'No', 'Yes'],
        'Welding Certified': ['Yes', 'No', 'No', 'No', 'Yes'],
        'Leadership Training': ['No', 'Yes', 'No', 'Yes', 'No'],
        'Electrical License': ['No', 'No', 'Yes', 'No', 'No'],
        'Spanish Language': ['Yes', 'Yes', 'No', 'No', 'No'],
        'Six Sigma Training': ['No', 'No', 'No', 'Yes', 'No'],
        'CDL License': ['No', 'No', 'No', 'No', 'Yes']
    }
    
    df_valid = pd.DataFrame(valid_employee_data)
    
    # Create Excel file with instructions
    with pd.ExcelWriter('test_valid_employees.xlsx', engine='openpyxl') as writer:
        df_valid.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add instructions sheet
        instructions = pd.DataFrame({
            'Instructions': [
                'This is a VALID test file for the header-based qualification system',
                'Column headers define qualifications/skills',
                'Employee cells contain Yes/No values',
                'This file should pass validation completely',
                'Use this to test successful upload functionality'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    print("   ✓ test_valid_employees.xlsx created")
    
    # ==========================================
    # 2. INVALID EMPLOYEE DATA - VARIOUS ERRORS
    # ==========================================
    
    print("2. Creating invalid employee data file...")
    
    invalid_employee_data = {
        'Last Name': ['Smith', '', 'Williams', 'Brown', 'Davis', 'Wilson'],
        'First Name': ['John', 'Sarah', '', 'Emily', 'Robert', 'Jane'],
        'Employee ID': ['EMP001', '', 'EMP003', 'EMP001', 'EMP005', 'EMP006'],  # Missing and duplicate
        'Crew Assigned': ['A', 'B', 'E', 'D', '5', 'C'],  # Invalid crews E and 5
        'Current Job Position': ['Operator', 'Lead Operator', '', 'Supervisor', 'Maintenance', 'Technician'],
        'Email': [
            'john.smith@company.com',
            'invalid-email',  # Invalid format
            'mike.williams@company.com',
            'emily.brown@company.com',
            'robert.davis@company.com',
            'jane.wilson@company.com'
        ],
        'OSHA 10 Certification': ['Yes', 'Maybe', 'No', 'Yes', 'No', 'Yes'],  # Invalid "Maybe"
        'Forklift License': ['Yes', 'No', 'INVALID', 'No', 'Yes', 'No'],  # Invalid value
        'First Aid Certified': ['No', 'Yes', 'Yes', 'Yes', 'No', 'Yes']
    }
    
    df_invalid = pd.DataFrame(invalid_employee_data)
    
    with pd.ExcelWriter('test_invalid_employees.xlsx', engine='openpyxl') as writer:
        df_invalid.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add error documentation
        errors_doc = pd.DataFrame({
            'Expected Errors': [
                'Row 2: Missing Last Name',
                'Row 3: Missing First Name', 
                'Row 2: Missing Employee ID',
                'Row 4: Duplicate Employee ID (EMP001)',
                'Row 3: Invalid Crew (E)',
                'Row 5: Invalid Crew (5)',
                'Row 3: Missing Current Job Position',
                'Row 2: Invalid email format',
                'Row 2: Invalid qualification value (Maybe)',
                'Row 3: Invalid qualification value (INVALID)'
            ]
        })
        errors_doc.to_excel(writer, sheet_name='Expected Errors', index=False)
    
    print("   ✓ test_invalid_employees.xlsx created")
    
    # ==========================================
    # 3. LARGE DATASET - PERFORMANCE TEST
    # ==========================================
    
    print("3. Creating large dataset for performance testing...")
    
    # Generate 500 employees
    large_data = []
    crews = ['A', 'B', 'C', 'D']
    positions = ['Operator', 'Lead Operator', 'Technician', 'Supervisor', 'Maintenance', 'Quality Control']
    
    for i in range(1, 501):
        employee = {
            'Last Name': f'LastName{i:03d}',
            'First Name': f'FirstName{i:03d}',
            'Employee ID': f'EMP{i:03d}',
            'Crew Assigned': crews[i % 4],
            'Current Job Position': positions[i % len(positions)],
            'Email': f'employee{i:03d}@company.com',
            'OSHA 10 Certification': 'Yes' if i % 3 == 0 else 'No',
            'Forklift License': 'Yes' if i % 5 == 0 else 'No',
            'First Aid Certified': 'Yes' if i % 4 == 0 else 'No',
            'Crane Operator': 'Yes' if i % 7 == 0 else 'No',
            'Welding Certified': 'Yes' if i % 6 == 0 else 'No',
            'Leadership Training': 'Yes' if i % 8 == 0 else 'No',
            'Electrical License': 'Yes' if i % 10 == 0 else 'No',
            'Spanish Language': 'Yes' if i % 9 == 0 else 'No'
        }
        large_data.append(employee)
    
    df_large = pd.DataFrame(large_data)
    df_large.to_excel('test_large_dataset.xlsx', sheet_name='Employee Data', index=False)
    
    print("   ✓ test_large_dataset.xlsx created (500 employees)")
    
    # ==========================================
    # 4. OVERTIME HISTORY DATA
    # ==========================================
    
    print("4. Creating overtime history test file...")
    
    # Create 13 weeks of data for 6 employees
    overtime_data = []
    employees = ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005', 'EMP006']
    
    # Start 13 weeks ago
    start_date = date.today() - timedelta(weeks=13)
    
    for emp_id in employees:
        for week in range(13):
            week_start = start_date + timedelta(weeks=week)
            
            # Generate realistic overtime data
            if emp_id == 'EMP006':  # High OT employee
                regular_hours = 40
                overtime_hours = np.random.randint(15, 25)
            elif emp_id in ['EMP001', 'EMP003']:  # Medium OT
                regular_hours = 40
                overtime_hours = np.random.randint(5, 15)
            else:  # Low OT
                regular_hours = 40
                overtime_hours = np.random.randint(0, 8)
            
            overtime_data.append({
                'Employee ID': emp_id,
                'Week Start Date': week_start.strftime('%Y-%m-%d'),
                'Regular Hours': regular_hours,
                'Overtime Hours': overtime_hours,
                'Total Hours': regular_hours + overtime_hours,
                'Notes': f'Week {week + 1}'
            })
    
    df_overtime = pd.DataFrame(overtime_data)
    df_overtime.to_excel('test_overtime_history.xlsx', sheet_name='Overtime Data', index=False)
    
    print("   ✓ test_overtime_history.xlsx created (13 weeks x 6 employees)")
    
    # ==========================================
    # 5. BULK UPDATE DATA
    # ==========================================
    
    print("5. Creating bulk update test file...")
    
    bulk_update_data = {
        'Last Name': ['Smith', 'Johnson', 'Brown', 'Davis'],
        'First Name': ['John', 'Sarah', 'Emily', 'Robert'],
        'Employee ID': ['EMP001', 'EMP002', 'EMP004', 'EMP005'],
        'Crew Assigned': ['B', 'A', 'C', 'D'],  # Changed crews
        'Current Job Position': ['Lead Operator', 'Supervisor', 'Lead Technician', 'Maintenance Lead'],  # Promotions
        'Email': [
            'j.smith@company.com',  # Updated email
            'sarah.johnson@company.com',
            'e.brown@company.com',  # Updated email
            'robert.davis@company.com'
        ],
        'OSHA 30 Certification': ['Yes', 'Yes', 'Yes', 'No'],  # New qualification
        'Management Training': ['Yes', 'Yes', 'No', 'No'],  # New qualification
        'Forklift License': ['Yes', 'No', 'Yes', 'Yes']  # Updated existing
    }
    
    df_bulk_update = pd.DataFrame(bulk_update_data)
    
    with pd.ExcelWriter('test_bulk_update.xlsx', engine='openpyxl') as writer:
        df_bulk_update.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add update documentation
        updates_doc = pd.DataFrame({
            'Updates Made': [
                'EMP001: Crew A→B, Operator→Lead Operator, Add OSHA 30 & Management Training',
                'EMP002: Crew B→A, Lead Operator→Supervisor, Add OSHA 30 & Management Training',
                'EMP004: Position→Lead Technician, Add OSHA 30',
                'EMP005: Position→Maintenance Lead, Add Forklift License',
                'All: New qualification columns added',
                'Email updates for EMP001 and EMP004'
            ]
        })
        updates_doc.to_excel(writer, sheet_name='Update Details', index=False)
    
    print("   ✓ test_bulk_update.xlsx created")
    
    # ==========================================
    # 6. EDGE CASE FILES
    # ==========================================
    
    print("6. Creating edge case test files...")
    
    # Empty file
    empty_df = pd.DataFrame()
    empty_df.to_excel('test_empty_file.xlsx', index=False)
    print("   ✓ test_empty_file.xlsx created")
    
    # Wrong sheet name
    wrong_sheet_data = {
        'Last Name': ['Test'],
        'First Name': ['User'],
        'Employee ID': ['TEST001'],
        'Crew Assigned': ['A'],
        'Current Job Position': ['Tester'],
        'Email': ['test@company.com']
    }
    df_wrong_sheet = pd.DataFrame(wrong_sheet_data)
    df_wrong_sheet.to_excel('test_wrong_sheet.xlsx', sheet_name='Data', index=False)  # Wrong sheet name
    print("   ✓ test_wrong_sheet.xlsx created")
    
    # ==========================================
    # SUMMARY
    # ==========================================
    
    print("\n" + "="*50)
    print("TEST FILES CREATED SUCCESSFULLY!")
    print("="*50)
    
    files_created = [
        'test_valid_employees.xlsx - Clean data for successful import',
        'test_invalid_employees.xlsx - Various errors for validation testing',
        'test_large_dataset.xlsx - 500 employees for performance testing',
        'test_overtime_history.xlsx - 13 weeks of OT data for 6 employees',
        'test_bulk_update.xlsx - Updates for existing employees',
        'test_empty_file.xlsx - Empty file edge case',
        'test_wrong_sheet.xlsx - Wrong sheet name edge case'
    ]
    
    for i, file_desc in enumerate(files_created, 1):
        print(f"{i}. {file_desc}")
    
    print("\nUSAGE:")
    print("1. Upload test_valid_employees.xlsx first to populate your system")
    print("2. Test validation with test_invalid_employees.xlsx")
    print("3. Test performance with test_large_dataset.xlsx")
    print("4. Upload overtime data with test_overtime_history.xlsx")
    print("5. Test updates with test_bulk_update.xlsx")
    print("6. Test edge cases with empty and wrong sheet files")
    
    print("\nNOTE: The header-based system treats column headers as qualification names.")
    print("Cells should contain Yes/No values to indicate if employee has that skill.")

if __name__ == "__main__":
    create_test_files()
