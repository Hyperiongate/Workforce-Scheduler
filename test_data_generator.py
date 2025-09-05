#!/usr/bin/env python3
"""
Generate test Excel files for the Employee Upload System
Creates files with YOUR EXACT column format
"""

import pandas as pd
import random
from datetime import datetime, timedelta
import os

def create_test_files():
    """Generate various test Excel files"""
    
    print("=" * 60)
    print("GENERATING TEST EXCEL FILES")
    print("Using YOUR format: Last Name, First Name, Employee ID, Crew Assigned, Current Job Position, Email")
    print("=" * 60)
    
    # 1. Valid Employee Data (5 employees)
    print("\n📁 Creating test_valid_employees.xlsx...")
    valid_data = {
        'Last Name': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones'],
        'First Name': ['John', 'Sarah', 'Michael', 'Emily', 'David'],
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'Crew Assigned': ['A', 'B', 'C', 'D', 'A'],
        'Current Job Position': ['Operator', 'Lead Operator', 'Technician', 'Supervisor', 'Operator'],
        'Email': ['john.smith@company.com', 'sarah.j@company.com', 'mike.w@company.com', 
                  'emily.b@company.com', 'david.j@company.com']
    }
    df_valid = pd.DataFrame(valid_data)
    
    # Create Excel with YOUR sheet name
    with pd.ExcelWriter('test_valid_employees.xlsx', engine='openpyxl') as writer:
        df_valid.to_excel(writer, sheet_name='Employee Data', index=False)
    print("  ✅ Created: test_valid_employees.xlsx (5 valid employees)")
    
    # 2. Invalid Data File (with errors)
    print("\n📁 Creating test_invalid_employees.xlsx...")
    invalid_data = {
        'Last Name': ['Garcia', '', 'Martinez', 'Rodriguez', 'Lewis', 'Walker'],
        'First Name': ['Maria', 'James', 'Carlos', 'Ana', 'George', 'Lisa'],
        'Employee ID': ['EMP006', '', 'EMP008', 'EMP009', 'EMP006', 'EMP011'],  # Missing ID, duplicate
        'Crew Assigned': ['A', 'B', 'E', 'D', '5', 'C'],  # Invalid crews: E and 5
        'Current Job Position': ['Operator', 'Technician', 'Lead', 'Supervisor', 'Operator', 'Tech'],
        'Email': ['maria.g@company', 'james.invalid', 'carlos@company.com', 
                  'ana.r@company.com', 'george.l@company.com', 'lisa.w@company.com']  # Invalid emails
    }
    df_invalid = pd.DataFrame(invalid_data)
    
    with pd.ExcelWriter('test_invalid_employees.xlsx', engine='openpyxl') as writer:
        df_invalid.to_excel(writer, sheet_name='Employee Data', index=False)
    print("  ✅ Created: test_invalid_employees.xlsx (contains validation errors)")
    
    # 3. Large Dataset (500 employees)
    print("\n📁 Creating test_large_dataset.xlsx...")
    departments = ['Operations', 'Maintenance', 'Quality', 'Safety', 'Admin']
    positions = ['Operator', 'Lead Operator', 'Technician', 'Supervisor', 'Manager', 'Coordinator']
    crews = ['A', 'B', 'C', 'D']
    
    large_data = {
        'Last Name': [f'Employee{i:03d}' for i in range(1, 501)],
        'First Name': [random.choice(['John', 'Sarah', 'Mike', 'Emily', 'David', 'Lisa', 'James', 'Maria']) 
                      for _ in range(500)],
        'Employee ID': [f'EMP{i:04d}' for i in range(1000, 1500)],
        'Crew Assigned': [random.choice(crews) for _ in range(500)],
        'Current Job Position': [random.choice(positions) for _ in range(500)],
        'Email': [f'employee{i:03d}@company.com' for i in range(1000, 1500)]
    }
    df_large = pd.DataFrame(large_data)
    
    with pd.ExcelWriter('test_large_dataset.xlsx', engine='openpyxl') as writer:
        df_large.to_excel(writer, sheet_name='Employee Data', index=False)
    print("  ✅ Created: test_large_dataset.xlsx (500 employees)")
    
    # 4. Overtime History File
    print("\n📁 Creating test_overtime_history.xlsx...")
    
    # Generate 13 weeks of overtime data
    overtime_columns = ['Employee ID']
    base_date = datetime.now() - timedelta(weeks=13)
    
    for week in range(13):
        week_date = base_date + timedelta(weeks=week)
        week_label = f"Week {week_date.strftime('%m/%d/%Y')}"
        overtime_columns.append(week_label)
    
    # Create data for 6 employees
    overtime_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005', 'EMP006']
    }
    
    # Add random overtime hours for each week
    for week_col in overtime_columns[1:]:
        overtime_data[week_col] = [
            round(random.uniform(0, 20), 1) if random.random() > 0.3 else 0
            for _ in range(6)
        ]
    
    # Make EMP006 have consistently high overtime
    for week_col in overtime_columns[1:]:
        overtime_data[week_col][5] = round(random.uniform(15, 25), 1)
    
    df_overtime = pd.DataFrame(overtime_data)
    
    with pd.ExcelWriter('test_overtime_history.xlsx', engine='openpyxl') as writer:
        df_overtime.to_excel(writer, sheet_name='Overtime Data', index=False)
    print("  ✅ Created: test_overtime_history.xlsx (13 weeks of OT data)")
    
    # 5. Bulk Update File
    print("\n📁 Creating test_bulk_update.xlsx...")
    update_data = {
        'Last Name': ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones'],
        'First Name': ['John', 'Sarah', 'Michael', 'Emily', 'David'],
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'Crew Assigned': ['B', 'B', 'A', 'C', 'D'],  # Changed crews
        'Current Job Position': ['Lead Operator', 'Supervisor', 'Operator', 'Lead Operator', 'Technician'],  # Changed positions
        'Email': ['john.smith@newcompany.com', 'sarah.johnson@company.com', 'michael.w@company.com',
                  'emily.brown@company.com', 'david.jones@company.com']  # Some email updates
    }
    df_update = pd.DataFrame(update_data)
    
    with pd.ExcelWriter('test_bulk_update.xlsx', engine='openpyxl') as writer:
        df_update.to_excel(writer, sheet_name='Employee Data', index=False)
    print("  ✅ Created: test_bulk_update.xlsx (updates for existing employees)")
    
    # 6. Empty File
    print("\n📁 Creating test_empty.xlsx...")
    df_empty = pd.DataFrame(columns=['Last Name', 'First Name', 'Employee ID', 
                                     'Crew Assigned', 'Current Job Position', 'Email'])
    
    with pd.ExcelWriter('test_empty.xlsx', engine='openpyxl') as writer:
        df_empty.to_excel(writer, sheet_name='Employee Data', index=False)
    print("  ✅ Created: test_empty.xlsx (empty file with headers only)")
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST FILES CREATED SUCCESSFULLY!")
    print("=" * 60)
    
    print("\n📋 File Descriptions:")
    print("  • test_valid_employees.xlsx - 5 valid employees, ready to import")
    print("  • test_invalid_employees.xlsx - Contains errors for testing validation")
    print("  • test_large_dataset.xlsx - 500 employees for performance testing")
    print("  • test_overtime_history.xlsx - 13 weeks of OT data for 6 employees")
    print("  • test_bulk_update.xlsx - Updates for existing employees")
    print("  • test_empty.xlsx - Empty file with headers only")
    
    print("\n🚀 How to Test:")
    print("  1. Log in as a supervisor")
    print("  2. Go to Dashboard → Upload Data")
    print("  3. Try uploading each test file")
    print("  4. Check validation results")
    print("  5. Verify data imports correctly")
    
    print("\n⚠️  Expected Validation Errors in test_invalid_employees.xlsx:")
    print("  • Row 2: Missing First Name")
    print("  • Row 2: Missing Employee ID")
    print("  • Row 3: Invalid Crew 'E' (must be A, B, C, or D)")
    print("  • Row 5: Invalid Crew '5' (must be A, B, C, or D)")
    print("  • Row 5: Duplicate Employee ID 'EMP006'")
    print("  • Row 1 & 2: Invalid email formats")

def main():
    """Main function"""
    try:
        # Check if pandas is installed
        import pandas as pd
        import openpyxl
    except ImportError:
        print("❌ Required packages not installed!")
        print("Run: pip install pandas openpyxl")
        return
    
    # Create test files
    create_test_files()
    
    print("\n✅ All test files created in current directory!")
    print(f"📂 Files saved to: {os.getcwd()}")

if __name__ == "__main__":
    main()
