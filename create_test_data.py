#!/usr/bin/env python3
"""
Complete Test Data Generator for Excel Upload System
Creates various test Excel files for thorough testing
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

def create_valid_employees():
    """Create a valid employee test file with 5 employees"""
    data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'First Name': ['John', 'Jane', 'Bob', 'Alice', 'Charlie'],
        'Last Name': ['Doe', 'Smith', 'Johnson', 'Williams', 'Brown'],
        'Email': ['john.doe@company.com', 'jane.smith@company.com', 'bob.johnson@company.com', 
                  'alice.williams@company.com', 'charlie.brown@company.com'],
        'Crew': ['A', 'B', 'C', 'D', 'A'],
        'Position': ['Operator', 'Technician', 'Supervisor', 'Operator', 'Technician'],
        'Department': ['Production', 'Maintenance', 'Production', 'Production', 'Maintenance'],
        'Hire Date': ['2020-01-15', '2019-06-01', '2021-03-20', '2022-02-10', '2023-01-05'],
        'Phone': ['555-0101', '555-0102', '555-0103', '555-0104', '555-0105'],
        'Emergency Contact': ['Mary Doe (555-0201)', 'Jim Smith (555-0202)', 'Alice Johnson (555-0203)',
                            'Bob Williams (555-0204)', 'Diana Brown (555-0205)'],
        'Skills': ['Forklift, Safety', 'Electrical, HVAC', 'Leadership, Forklift', 
                   'Safety', 'Electrical, Plumbing'],
        'Is Supervisor': ['No', 'No', 'Yes', 'No', 'No']
    }
    
    df = pd.DataFrame(data)
    
    with pd.ExcelWriter('test_valid_employees.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add instructions sheet
        instructions = pd.DataFrame({
            'Instructions': [
                'This is a valid test file with 5 employees',
                'All required fields are filled correctly',
                'Use this to test successful imports',
                'Expected Result: All 5 employees should import successfully'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    print("✅ Created: test_valid_employees.xlsx")
    return 'test_valid_employees.xlsx'

def create_invalid_employees():
    """Create test file with various validation errors"""
    data = {
        'Employee ID': ['', 'EMP002', 'EMP003', 'EMP004', 'EMP005', 'EMP001'],  # First missing, last duplicate
        'First Name': ['John', '', 'Bob123', 'Alice', 'Charlie', 'John'],  # Second missing, third has numbers
        'Last Name': ['Doe', 'Smith', '', 'Williams', 'Brown', 'Doe'],  # Third missing
        'Email': ['john.doe@company.com', 'invalid-email', 'bob.johnson@company.com', 
                  '', 'charlie.brown@company.com', 'john.doe@company.com'],  # Invalid format, missing
        'Crew': ['A', 'E', 'C', 'D', '5', 'A'],  # Invalid crews E and 5
        'Position': ['Operator', 'Unknown Position', 'Supervisor', 'Operator', 'Technician', 'Operator'],
        'Department': ['Production', 'Maintenance', 'Production', 'Production', 'Maintenance', 'Production'],
        'Hire Date': ['2020-01-15', 'invalid-date', '2021-03-20', '2022-02-10', '2023-01-05', '2020-01-15'],
        'Phone': ['555-0101', '555-0102', '555-0103', '555-0104', 'invalid-phone', '555-0101'],
        'Emergency Contact': ['Mary Doe (555-0201)', 'Jim Smith (555-0202)', '', '', 'Diana Brown (555-0205)', 'Mary Doe (555-0201)'],
        'Skills': ['Forklift, Safety', 'Electrical, HVAC', 'Leadership, Forklift', 
                   'Safety', 'Electrical, Plumbing', 'Forklift, Safety'],
        'Is Supervisor': ['No', 'Maybe', 'Yes', 'No', 'No', 'No']  # Invalid value "Maybe"
    }
    
    df = pd.DataFrame(data)
    
    with pd.ExcelWriter('test_invalid_employees.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add expected errors sheet
        errors = pd.DataFrame({
            'Expected Errors': [
                'Row 2: Missing Employee ID',
                'Row 3: Missing First Name', 
                'Row 3: Invalid email format',
                'Row 4: Missing Last Name',
                'Row 4: Invalid crew "E"',
                'Row 5: Missing Email',
                'Row 6: Invalid crew "5"',
                'Row 6: Invalid phone format',
                'Row 7: Duplicate Employee ID (EMP001)',
                'Various: Invalid date formats',
                'Various: Invalid supervisor values'
            ]
        })
        errors.to_excel(writer, sheet_name='Expected Errors', index=False)
    
    print("✅ Created: test_invalid_employees.xlsx")
    return 'test_invalid_employees.xlsx'

def create_large_dataset():
    """Create a large dataset for performance testing"""
    num_employees = 500
    crews = ['A', 'B', 'C', 'D']
    positions = ['Operator', 'Technician', 'Supervisor', 'Lead Operator', 'Maintenance Tech']
    departments = ['Production', 'Maintenance', 'Quality', 'Warehouse', 'Shipping']
    skills_list = ['Forklift', 'Safety', 'Electrical', 'HVAC', 'Plumbing', 'Welding', 
                   'Leadership', 'Training', 'First Aid', 'Hazmat']
    
    data = {
        'Employee ID': [f'EMP{str(i).zfill(4)}' for i in range(1, num_employees + 1)],
        'First Name': [random.choice(['John', 'Jane', 'Bob', 'Alice', 'Charlie', 'David', 
                                     'Emma', 'Frank', 'Grace', 'Henry']) for _ in range(num_employees)],
        'Last Name': [random.choice(['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 
                                    'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']) for _ in range(num_employees)],
        'Email': [f'employee{i}@company.com' for i in range(1, num_employees + 1)],
        'Crew': [random.choice(crews) for _ in range(num_employees)],
        'Position': [random.choice(positions) for _ in range(num_employees)],
        'Department': [random.choice(departments) for _ in range(num_employees)],
        'Hire Date': [(datetime.now() - timedelta(days=random.randint(30, 3650))).strftime('%Y-%m-%d') 
                      for _ in range(num_employees)],
        'Phone': [f'555-{random.randint(1000, 9999)}' for _ in range(num_employees)],
        'Emergency Contact': [f'Contact Person ({random.randint(555, 999)}-{random.randint(1000, 9999)})' 
                            for _ in range(num_employees)],
        'Skills': [', '.join(random.sample(skills_list, random.randint(1, 4))) for _ in range(num_employees)],
        'Is Supervisor': ['Yes' if random.random() > 0.9 else 'No' for _ in range(num_employees)]
    }
    
    df = pd.DataFrame(data)
    
    with pd.ExcelWriter('test_large_dataset.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Add summary sheet
        summary = pd.DataFrame({
            'Summary': [
                f'Total Employees: {num_employees}',
                f'Crews: {", ".join(crews)}',
                f'Positions: {len(positions)}',
                f'Departments: {len(departments)}',
                'Use this for performance testing',
                'Expected Result: Should process within 30 seconds'
            ]
        })
        summary.to_excel(writer, sheet_name='Summary', index=False)
    
    print(f"✅ Created: test_large_dataset.xlsx ({num_employees} employees)")
    return 'test_large_dataset.xlsx'

def create_overtime_history():
    """Create overtime history test file"""
    employees = ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005']
    
    # Generate 13 weeks of overtime data
    data = {'Employee ID': employees}
    
    for week in range(1, 14):
        week_data = []
        for emp in employees:
            # Regular hours between 35-45, with some overtime
            regular = random.randint(35, 40)
            overtime = random.choice([0, 0, 0, 4, 8, 12, 16])  # Most weeks no OT
            total = regular + overtime
            week_data.append(total)
        data[f'Week {week}'] = week_data
    
    # Add high overtime employee
    high_ot_employee = {
        'Employee ID': 'EMP006'
    }
    for week in range(1, 14):
        high_ot_employee[f'Week {week}'] = random.randint(48, 60)  # Consistently high OT
    
    df = pd.DataFrame(data)
    df = pd.concat([df, pd.DataFrame([high_ot_employee])], ignore_index=True)
    
    with pd.ExcelWriter('test_overtime_history.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Overtime Data', index=False)
        
        # Add summary sheet
        summary_data = []
        for _, row in df.iterrows():
            emp_id = row['Employee ID']
            total_hours = sum(row[f'Week {i}'] for i in range(1, 14))
            avg_hours = total_hours / 13
            summary_data.append({
                'Employee ID': emp_id,
                'Total Hours (13 weeks)': total_hours,
                'Average Weekly Hours': round(avg_hours, 1),
                'Estimated OT Hours': max(0, total_hours - (40 * 13))
            })
        
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
    
    print("✅ Created: test_overtime_history.xlsx")
    return 'test_overtime_history.xlsx'

def create_bulk_update():
    """Create bulk update test file"""
    data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
        'Crew': ['B', 'C', 'D', 'A', None],  # Changing crews, last one no change
        'Position': [None, 'Lead Operator', None, 'Supervisor', 'Senior Technician'],  # Some position updates
        'Department': ['Maintenance', None, None, 'Quality', None],  # Some dept changes
        'Skills': ['Forklift, Safety, Welding', None, 'Leadership, Training', None, 'Electrical, HVAC, Plumbing']
    }
    
    df = pd.DataFrame(data)
    
    with pd.ExcelWriter('test_bulk_update.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Bulk Update', index=False)
        
        # Add instructions
        instructions = pd.DataFrame({
            'Instructions': [
                'Bulk Update Test File',
                'Only non-empty cells will update existing data',
                'Employee ID is required to identify records',
                'Leave cells blank to keep existing values',
                '',
                'This file will update:',
                '- EMP001: Change crew to B, department to Maintenance, add Welding skill',
                '- EMP002: Promote to Lead Operator, change crew to C',
                '- EMP003: Change crew to D, add Leadership and Training skills',
                '- EMP004: Promote to Supervisor, change crew to A and department to Quality',
                '- EMP005: Promote to Senior Technician, update skills'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    print("✅ Created: test_bulk_update.xlsx")
    return 'test_bulk_update.xlsx'

def create_empty_file():
    """Create an empty Excel file for testing"""
    df = pd.DataFrame()
    
    with pd.ExcelWriter('test_empty.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
    
    print("✅ Created: test_empty.xlsx")
    return 'test_empty.xlsx'

def create_wrong_sheet_name():
    """Create file with wrong sheet name"""
    data = {
        'Employee ID': ['EMP001'],
        'First Name': ['John'],
        'Last Name': ['Doe'],
        'Email': ['john.doe@company.com'],
        'Crew': ['A']
    }
    
    df = pd.DataFrame(data)
    
    with pd.ExcelWriter('test_wrong_sheet.xlsx', engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Wrong Sheet Name', index=False)  # Wrong sheet name
    
    print("✅ Created: test_wrong_sheet.xlsx")
    return 'test_wrong_sheet.xlsx'

def create_all_test_files():
    """Create all test files"""
    print("\n" + "="*50)
    print("Creating Test Excel Files for Upload System")
    print("="*50 + "\n")
    
    files_created = []
    
    # Create each test file
    files_created.append(create_valid_employees())
    files_created.append(create_invalid_employees())
    files_created.append(create_large_dataset())
    files_created.append(create_overtime_history())
    files_created.append(create_bulk_update())
    files_created.append(create_empty_file())
    files_created.append(create_wrong_sheet_name())
    
    print("\n" + "="*50)
    print("✅ All test files created successfully!")
    print("="*50 + "\n")
    
    print("Test Files Created:")
    print("-" * 30)
    for i, filename in enumerate(files_created, 1):
        print(f"{i}. {filename}")
    
    print("\n📋 Testing Instructions:")
    print("-" * 30)
    print("1. Start with 'test_valid_employees.xlsx' - should import successfully")
    print("2. Then try 'test_invalid_employees.xlsx' - should show validation errors")
    print("3. Test performance with 'test_large_dataset.xlsx'")
    print("4. Test overtime upload with 'test_overtime_history.xlsx'")
    print("5. Test bulk updates with 'test_bulk_update.xlsx'")
    print("6. Test edge cases with 'test_empty.xlsx' and 'test_wrong_sheet.xlsx'")
    print("\n⚠️  Make sure you're logged in as a supervisor to access upload features!")
    
    # Check if files were created in current directory
    current_dir = os.getcwd()
    print(f"\n📁 Files created in: {current_dir}")
    
    return files_created

if __name__ == "__main__":
    create_all_test_files()
