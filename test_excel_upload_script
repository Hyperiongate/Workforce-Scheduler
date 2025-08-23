#!/usr/bin/env python3
"""
Test script to verify the Excel upload system is working correctly
This script creates test Excel files and can test the upload endpoints
"""

import pandas as pd
import os
from datetime import datetime, timedelta, date
import random

def create_test_data_files():
    """Create various test Excel files for testing the upload system"""
    
    # Create test directory
    test_dir = "test_excel_files"
    os.makedirs(test_dir, exist_ok=True)
    
    print("Creating test Excel files...")
    
    # 1. Valid Employee Data
    employees_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'First Name': ['John', 'Jane', 'Mike', 'Sarah', 'David'],
        'Last Name': ['Doe', 'Smith', 'Johnson', 'Williams', 'Brown'],
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'mike.johnson@company.com', 
                  'sarah.williams@company.com', 'david.brown@company.com'],
        'Crew': ['A', 'B', 'C', 'D', 'A'],
        'Department': ['Operations', 'Operations', 'Maintenance', 'Operations', 'Maintenance'],
        'Position': ['Machine Operator', 'Lead Operator', 'Technician', 'Machine Operator', 'Senior Technician']
    }
    
    df_employees = pd.DataFrame(employees_data)
    df_employees.to_excel(f"{test_dir}/test_valid_employees.xlsx", index=False, sheet_name="Employee Data")
    print("✓ Created: test_valid_employees.xlsx")
    
    # 2. Invalid Employee Data (for testing validation)
    invalid_data = {
        'Employee ID': ['EMP001', '', 'EMP003', 'EMP003', 'EMP005'],  # Missing ID and duplicate
        'First Name': ['John', 'Jane', '', 'Sarah', 'David'],  # Missing first name
        'Last Name': ['Doe', 'Smith', 'Johnson', 'Williams', ''],  # Missing last name
        'Email': ['john.doe@company', 'invalid-email', 'mike.johnson@company.com', 
                  'sarah.williams@company.com', 'david.brown@company.com'],  # Invalid emails
        'Crew': ['A', 'E', 'C', '5', 'A'],  # Invalid crews
        'Department': ['Operations', 'Operations', 'Maintenance', 'Operations', 'Maintenance'],
        'Position': ['Machine Operator', 'Lead Operator', 'Technician', 'Machine Operator', 'Senior Technician']
    }
    
    df_invalid = pd.DataFrame(invalid_data)
    df_invalid.to_excel(f"{test_dir}/test_invalid_employees.xlsx", index=False, sheet_name="Employee Data")
    print("✓ Created: test_invalid_employees.xlsx")
    
    # 3. Large Dataset (500 employees)
    large_data = {
        'Employee ID': [f'EMP{str(i).zfill(4)}' for i in range(1, 501)],
        'First Name': [random.choice(['John', 'Jane', 'Mike', 'Sarah', 'David', 'Lisa', 'Robert', 'Mary']) for _ in range(500)],
        'Last Name': [random.choice(['Doe', 'Smith', 'Johnson', 'Williams', 'Brown', 'Davis', 'Miller', 'Wilson']) for _ in range(500)],
        'Email': [f'employee{i}@company.com' for i in range(1, 501)],
        'Crew': [random.choice(['A', 'B', 'C', 'D']) for _ in range(500)],
        'Department': [random.choice(['Operations', 'Maintenance', 'Quality', 'Shipping']) for _ in range(500)],
        'Position': [random.choice(['Machine Operator', 'Lead Operator', 'Technician', 'Supervisor']) for _ in range(500)]
    }
    
    df_large = pd.DataFrame(large_data)
    df_large.to_excel(f"{test_dir}/test_large_dataset.xlsx", index=False, sheet_name="Employee Data")
    print("✓ Created: test_large_dataset.xlsx (500 employees)")
    
    # 4. Overtime History Data
    overtime_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005', 'EMP006'],
        'Employee Name': ['John Doe', 'Jane Smith', 'Mike Johnson', 'Sarah Williams', 'David Brown', 'High OT Worker']
    }
    
    # Add 13 weeks of overtime data
    for week in range(1, 14):
        overtime_hours = []
        for emp_idx in range(6):
            if emp_idx == 5:  # High OT worker
                hours = random.uniform(50, 65)  # Consistently high OT
            else:
                hours = random.uniform(0, 20) if random.random() > 0.3 else 0
            overtime_hours.append(round(hours, 1))
        overtime_data[f'Week {week}'] = overtime_hours
    
    df_overtime = pd.DataFrame(overtime_data)
    df_overtime.to_excel(f"{test_dir}/test_overtime_history.xlsx", index=False, sheet_name="Overtime History")
    print("✓ Created: test_overtime_history.xlsx")
    
    # 5. Bulk Update Data
    bulk_update_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'Crew': ['B', '', 'D', '', 'A'],  # Some updates, some blank
        'Department': ['Maintenance', '', '', 'Quality', ''],
        'Position': ['', 'Lead Operator', '', 'Supervisor', '']
    }
    
    df_bulk = pd.DataFrame(bulk_update_data)
    df_bulk.to_excel(f"{test_dir}/test_bulk_update.xlsx", index=False, sheet_name="Bulk Update")
    print("✓ Created: test_bulk_update.xlsx")
    
    # 6. Empty file
    df_empty = pd.DataFrame()
    df_empty.to_excel(f"{test_dir}/test_empty_file.xlsx", index=False)
    print("✓ Created: test_empty_file.xlsx")
    
    # 7. Wrong sheet name
    df_wrong_sheet = pd.DataFrame(employees_data)
    df_wrong_sheet.to_excel(f"{test_dir}/test_wrong_sheet.xlsx", index=False, sheet_name="Wrong Sheet Name")
    print("✓ Created: test_wrong_sheet.xlsx")
    
    print(f"\nAll test files created in '{test_dir}' directory!")
    print("\nTest scenarios:")
    print("1. test_valid_employees.xlsx - Should upload successfully")
    print("2. test_invalid_employees.xlsx - Should fail validation with specific errors")
    print("3. test_large_dataset.xlsx - Test performance with 500 records")
    print("4. test_overtime_history.xlsx - For testing overtime upload")
    print("5. test_bulk_update.xlsx - For testing bulk updates")
    print("6. test_empty_file.xlsx - Should show 'no data' error")
    print("7. test_wrong_sheet.xlsx - Should show sheet name error")
    
    return test_dir

def display_test_instructions():
    """Display instructions for testing the upload system"""
    
    print("\n" + "="*60)
    print("EXCEL UPLOAD SYSTEM - TESTING INSTRUCTIONS")
    print("="*60)
    
    print("\n1. SETUP:")
    print("   - Ensure your Flask app is running")
    print("   - Log in as a supervisor")
    print("   - Navigate to the Upload Employees page")
    
    print("\n2. TEST VALIDATION:")
    print("   a) Upload 'test_invalid_employees.xlsx'")
    print("   b) Click 'Validate File'")
    print("   c) You should see specific validation errors")
    
    print("\n3. TEST SUCCESSFUL UPLOAD:")
    print("   a) Upload 'test_valid_employees.xlsx'")
    print("   b) Click 'Validate File' - should pass")
    print("   c) Click 'Import Data' - should succeed")
    
    print("\n4. TEST PERFORMANCE:")
    print("   a) Upload 'test_large_dataset.xlsx'")
    print("   b) Time the validation and import process")
    
    print("\n5. TEST OVERTIME UPLOAD:")
    print("   a) Change upload type to 'Overtime History'")
    print("   b) Upload 'test_overtime_history.xlsx'")
    print("   c) Validate and import")
    
    print("\n6. TEST ERROR HANDLING:")
    print("   - Try uploading a non-Excel file")
    print("   - Try the empty file")
    print("   - Try without selecting a file")
    
    print("\n7. VERIFY RESULTS:")
    print("   - Check employee list shows new employees")
    print("   - Check upload history shows all attempts")
    print("   - Verify crew distribution updated")

def main():
    """Main function"""
    print("Excel Upload System - Test Data Generator")
    print("-" * 40)
    
    # Create test files
    test_dir = create_test_data_files()
    
    # Display instructions
    display_test_instructions()
    
    print(f"\n✅ Test files are ready in the '{test_dir}' directory!")
    print("Follow the instructions above to test your upload system.")

if __name__ == "__main__":
    main()
