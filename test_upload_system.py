#!/usr/bin/env python3
"""
Excel Upload System Complete Testing & Verification Script
Run this script to verify your system and generate test files
Last Updated: 2025-01-09
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import requests
from pathlib import Path

class UploadSystemTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.test_results = []
        self.project_root = Path.cwd()
        self.test_files_created = []
        
    def run_all_tests(self):
        """Run complete test suite"""
        print("=" * 60)
        print("EXCEL UPLOAD SYSTEM COMPLETE VERIFICATION")
        print("=" * 60)
        
        # Phase 1: System Setup Verification
        print("\n📋 PHASE 1: SYSTEM VERIFICATION")
        print("-" * 40)
        self.verify_folder_structure()
        self.verify_file_permissions()
        self.verify_dependencies()
        
        # Phase 2: Generate Test Data
        print("\n📋 PHASE 2: GENERATING TEST DATA")
        print("-" * 40)
        self.create_test_files()
        
        # Phase 3: Route Testing
        print("\n📋 PHASE 3: ROUTE VERIFICATION")
        print("-" * 40)
        self.test_routes()
        
        # Phase 4: Print Results
        print("\n📋 PHASE 4: TEST RESULTS")
        print("-" * 40)
        self.print_results()
    
    def verify_folder_structure(self):
        """Verify all required folders exist"""
        print("\n🔍 Checking folder structure...")
        
        folders_to_check = [
            ('upload_files', True),  # (folder_name, create_if_missing)
            ('blueprints', False),
            ('templates', False),
            ('utils', False)
        ]
        
        for folder, create in folders_to_check:
            folder_path = self.project_root / folder
            if folder_path.exists():
                print(f"  ✅ {folder}/ exists")
                self.test_results.append(('Folder Check', folder, 'PASS'))
            else:
                if create:
                    try:
                        folder_path.mkdir(parents=True, exist_ok=True)
                        print(f"  ✅ {folder}/ created")
                        self.test_results.append(('Folder Check', folder, 'CREATED'))
                    except Exception as e:
                        print(f"  ❌ {folder}/ could not be created: {e}")
                        self.test_results.append(('Folder Check', folder, 'FAIL'))
                else:
                    print(f"  ❌ {folder}/ missing")
                    self.test_results.append(('Folder Check', folder, 'MISSING'))
    
    def verify_file_permissions(self):
        """Check file permissions"""
        print("\n🔍 Checking file permissions...")
        
        upload_folder = self.project_root / "upload_files"
        test_file = upload_folder / ".permission_test"
        
        try:
            # Test write permission
            test_file.write_text("test")
            print("  ✅ Write permission OK")
            
            # Test read permission
            content = test_file.read_text()
            print("  ✅ Read permission OK")
            
            # Clean up
            test_file.unlink()
            print("  ✅ Delete permission OK")
            
            self.test_results.append(('Permissions', 'upload_files', 'PASS'))
        except Exception as e:
            print(f"  ❌ Permission error: {e}")
            self.test_results.append(('Permissions', 'upload_files', 'FAIL'))
    
    def verify_dependencies(self):
        """Check Python dependencies"""
        print("\n🔍 Checking Python dependencies...")
        
        required_packages = {
            'pandas': 'Data processing',
            'openpyxl': 'Excel file handling',
            'flask': 'Web framework',
            'flask_login': 'Authentication',
            'sqlalchemy': 'Database ORM'
        }
        
        for package, description in required_packages.items():
            try:
                __import__(package)
                print(f"  ✅ {package} ({description})")
                self.test_results.append(('Dependency', package, 'INSTALLED'))
            except ImportError:
                print(f"  ❌ {package} not installed - {description}")
                print(f"     Run: pip install {package}")
                self.test_results.append(('Dependency', package, 'MISSING'))
    
    def create_test_files(self):
        """Create comprehensive test Excel files"""
        print("\n📝 Creating test Excel files...")
        
        # Test File 1: Valid Employee Data with Skills
        self.create_valid_employee_file()
        
        # Test File 2: Invalid Data (various errors)
        self.create_invalid_employee_file()
        
        # Test File 3: Edge Cases
        self.create_edge_case_file()
        
        # Test File 4: Large Dataset
        self.create_large_dataset()
        
        # Test File 5: Overtime Data
        self.create_overtime_file()
        
        print(f"\n  ✅ Created {len(self.test_files_created)} test files")
    
    def create_valid_employee_file(self):
        """Create a valid employee file with skills"""
        data = {
            'Last Name': ['Smith', 'Johnson', 'Williams', 'Brown', 'Davis'],
            'First Name': ['John', 'Sarah', 'Michael', 'Emily', 'Robert'],
            'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
            'Crew Assigned': ['A', 'B', 'C', 'D', 'A'],
            'Current Job Position': ['Operator', 'Lead Operator', 'Technician', 'Supervisor', 'Maintenance'],
            'Email': ['john.smith@company.com', 'sarah.j@company.com', 'mike.w@company.com', 
                     'emily.b@company.com', 'robert.d@company.com'],
            # Skills (qualifications)
            'Forklift Certified': ['Yes', 'Yes', 'No', 'Yes', 'Yes'],
            'OSHA 10': ['Yes', 'Yes', 'Yes', 'No', 'Yes'],
            'First Aid': ['No', 'Yes', 'Yes', 'Yes', 'No'],
            'Welding': ['No', 'No', 'Yes', 'No', 'Yes'],
            'Leadership Training': ['No', 'Yes', 'No', 'Yes', 'No']
        }
        
        df = pd.DataFrame(data)
        filename = 'test_valid_employees.xlsx'
        filepath = self.project_root / filename
        df.to_excel(filepath, index=False, sheet_name='Employee Data')
        
        print(f"  ✅ Created: {filename}")
        self.test_files_created.append(filename)
        return filepath
    
    def create_invalid_employee_file(self):
        """Create file with various validation errors"""
        data = {
            'Last Name': ['', 'Johnson', 'Williams', 'Brown', 'Davis', 'Wilson'],  # Missing first
            'First Name': ['John', '', 'Michael', 'Emily', 'Robert', 'Jane'],  # Missing second
            'Employee ID': ['', 'EMP002', 'EMP003', 'EMP003', 'EMP005', 'EMP006'],  # Missing first, duplicate
            'Crew Assigned': ['A', 'E', 'C', '5', 'A', 'B'],  # Invalid E and 5
            'Current Job Position': ['Operator', 'Lead', '', 'Supervisor', 'Tech', 'Manager'],  # Missing third
            'Email': ['john.smith', 'sarah.j@company', 'invalid-email', 'emily.b@company.com', 
                     'robert.d@company.com', 'jane@company.com'],  # Invalid formats
            'Skill 1': ['Yes', 'Maybe', 'Y', 'N', '1', 'True']  # Invalid "Maybe"
        }
        
        df = pd.DataFrame(data)
        filename = 'test_invalid_employees.xlsx'
        filepath = self.project_root / filename
        df.to_excel(filepath, index=False, sheet_name='Employee Data')
        
        print(f"  ✅ Created: {filename} (with intentional errors)")
        self.test_files_created.append(filename)
        return filepath
    
    def create_edge_case_file(self):
        """Create file with edge cases"""
        data = {
            'Last Name': ['O\'Brien', 'José-María', 'Van Der Berg', 'Lee', '李'],
            'First Name': ['Seán', 'François', 'Hans-Jürgen', 'Min-Ji', '明'],
            'Employee ID': ['EMP-007', 'EMP_008', 'EMP.009', 'EMP010', 'EMP011'],
            'Crew Assigned': ['a', 'B', 'c', 'D', 'A'],  # Mixed case
            'Current Job Position': ['Sr. Operator', 'Jr. Tech', 'Lead/Supervisor', 'Operator II', 'Tech 3'],
            'Email': ['sean.obrien@company.com', 'francois@company.com', 'hans@company.com',
                     'minji@company.com', 'ming@company.com'],
            # Many skills with various formats
            'Certification #1': ['x', 'X', '', None, 'yes'],
            'Certification #2': ['NO', 'no', 'n', 'N', '0'],
            'Special (Skill)': ['TRUE', 'true', 'False', 'false', '']
        }
        
        df = pd.DataFrame(data)
        filename = 'test_edge_cases.xlsx'
        filepath = self.project_root / filename
        df.to_excel(filepath, index=False, sheet_name='Employee Data')
        
        print(f"  ✅ Created: {filename} (edge cases)")
        self.test_files_created.append(filename)
        return filepath
    
    def create_large_dataset(self):
        """Create a large dataset for performance testing"""
        np.random.seed(42)
        num_employees = 500
        
        crews = ['A', 'B', 'C', 'D']
        positions = ['Operator', 'Technician', 'Lead Operator', 'Supervisor', 'Maintenance', 
                    'Quality Control', 'Safety Officer', 'Trainer']
        
        data = {
            'Last Name': [f'LastName{i:03d}' for i in range(num_employees)],
            'First Name': [f'FirstName{i:03d}' for i in range(num_employees)],
            'Employee ID': [f'EMP{i:04d}' for i in range(num_employees)],
            'Crew Assigned': np.random.choice(crews, num_employees),
            'Current Job Position': np.random.choice(positions, num_employees),
            'Email': [f'employee{i:03d}@company.com' for i in range(num_employees)]
        }
        
        # Add 20 random skills
        for skill_num in range(1, 21):
            skill_name = f'Skill_{skill_num:02d}'
            # 30% chance of having each skill
            data[skill_name] = np.random.choice(['Yes', 'No', ''], 
                                               num_employees, 
                                               p=[0.3, 0.3, 0.4])
        
        df = pd.DataFrame(data)
        filename = 'test_large_dataset.xlsx'
        filepath = self.project_root / filename
        df.to_excel(filepath, index=False, sheet_name='Employee Data')
        
        print(f"  ✅ Created: {filename} ({num_employees} employees)")
        self.test_files_created.append(filename)
        return filepath
    
    def create_overtime_file(self):
        """Create overtime data file"""
        employees = ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005', 'EMP006']
        data_rows = []
        
        # Generate 13 weeks of data for each employee
        start_date = datetime(2024, 10, 7)  # A Monday
        
        for emp_id in employees:
            for week_num in range(13):
                week_date = start_date + timedelta(weeks=week_num)
                
                # Generate realistic hours
                regular = 40
                overtime = np.random.choice([0, 0, 0, 4, 8, 10, 12, 16], p=[0.3, 0.2, 0.1, 0.15, 0.1, 0.05, 0.05, 0.05])
                
                # High OT for EMP006 to test warnings
                if emp_id == 'EMP006':
                    overtime = np.random.choice([20, 24, 28, 32], p=[0.25, 0.25, 0.25, 0.25])
                
                data_rows.append({
                    'Employee ID': emp_id,
                    'Week Start Date': week_date.strftime('%Y-%m-%d'),
                    'Regular Hours': regular,
                    'Overtime Hours': overtime,
                    'Total Hours': regular + overtime,
                    'Notes': f'Week {week_num + 1}'
                })
        
        df = pd.DataFrame(data_rows)
        filename = 'test_overtime_data.xlsx'
        filepath = self.project_root / filename
        df.to_excel(filepath, index=False, sheet_name='Overtime Data')
        
        print(f"  ✅ Created: {filename} ({len(employees)} employees, 13 weeks each)")
        self.test_files_created.append(filename)
        return filepath
    
    def test_routes(self):
        """Test that routes are accessible"""
        print("\n🌐 Testing route accessibility...")
        print("  ℹ️  Make sure your Flask app is running on localhost:5000")
        
        routes_to_test = [
            ('/test-upload-route', 'GET', 'Test endpoint'),
            ('/upload-employees', 'GET', 'Upload page'),
            ('/download-employee-template', 'GET', 'Template download'),
            ('/upload-history', 'GET', 'Upload history')
        ]
        
        for route, method, description in routes_to_test:
            url = f"{self.base_url}{route}"
            try:
                if method == 'GET':
                    response = requests.get(url, timeout=2, allow_redirects=False)
                    
                    if response.status_code in [200, 302]:  # 302 is redirect (login required)
                        print(f"  ✅ {route} - {description}")
                        self.test_results.append(('Route Test', route, 'ACCESSIBLE'))
                    else:
                        print(f"  ⚠️  {route} - Status: {response.status_code}")
                        self.test_results.append(('Route Test', route, f'STATUS_{response.status_code}'))
            except requests.exceptions.ConnectionError:
                print(f"  ⚠️  Cannot connect to {self.base_url} - Is the server running?")
                self.test_results.append(('Route Test', route, 'NO_CONNECTION'))
                break
            except Exception as e:
                print(f"  ❌ {route} - Error: {e}")
                self.test_results.append(('Route Test', route, 'ERROR'))
    
    def print_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)
        
        # Count results
        passed = sum(1 for _, _, status in self.test_results if status in ['PASS', 'INSTALLED', 'ACCESSIBLE', 'CREATED'])
        failed = sum(1 for _, _, status in self.test_results if status in ['FAIL', 'MISSING', 'ERROR'])
        warnings = sum(1 for _, _, status in self.test_results if status not in ['PASS', 'INSTALLED', 'ACCESSIBLE', 'CREATED', 'FAIL', 'MISSING', 'ERROR'])
        
        print(f"\n📊 Results: {passed} Passed, {failed} Failed, {warnings} Warnings")
        
        # Detailed results
        print("\n📋 Detailed Results:")
        for category, item, status in self.test_results:
            if status in ['PASS', 'INSTALLED', 'ACCESSIBLE', 'CREATED']:
                symbol = '✅'
            elif status in ['FAIL', 'MISSING', 'ERROR']:
                symbol = '❌'
            else:
                symbol = '⚠️'
            
            print(f"  {symbol} {category}: {item} - {status}")
        
        # Test files created
        if self.test_files_created:
            print(f"\n📁 Test Files Created ({len(self.test_files_created)}):")
            for filename in self.test_files_created:
                print(f"  • {filename}")
        
        # Next steps
        print("\n🎯 NEXT STEPS:")
        print("-" * 40)
        
        if failed > 0:
            print("1. Fix the failed items above")
            print("2. Re-run this test script")
        else:
            print("1. Start your Flask application")
            print("2. Log in as a supervisor")
            print("3. Go to /upload-employees")
            print("4. Test with the generated files:")
            print("   a. Start with 'test_valid_employees.xlsx'")
            print("   b. Then try 'test_invalid_employees.xlsx' to see error handling")
            print("   c. Test 'test_large_dataset.xlsx' for performance")
            print("   d. Upload 'test_overtime_data.xlsx' for overtime data")
        
        print("\n📌 Your Excel Format:")
        print("  • Last Name, First Name, Employee ID (required)")
        print("  • Crew Assigned (A, B, C, or D)")
        print("  • Current Job Position")
        print("  • Email (optional but needed for login)")
        print("  • Skill columns: Use Yes/No values")
        print("  • Default password: password123")

def main():
    """Run the complete test suite"""
    print("\n🚀 Starting Excel Upload System Testing")
    print("This script will verify your setup and create test files\n")
    
    tester = UploadSystemTester()
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Testing complete!")
    print("Check the test files created in your project directory")
    print("Follow the NEXT STEPS above to complete testing\n")

if __name__ == "__main__":
    main()
