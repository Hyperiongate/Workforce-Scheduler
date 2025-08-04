#!/usr/bin/env python3
"""
Comprehensive Test Suite for Excel Upload System
Run this to validate all functionality before moving forward
"""

import os
import sys
import time
import pandas as pd
import requests
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama for colored output
init()

class ExcelUploadTester:
    def __init__(self, base_url="http://localhost:5000", username="supervisor", password="password"):
        self.base_url = base_url
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.test_results = []
        self.test_files_dir = "test_files"
        
    def print_header(self, text):
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{text.center(60)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
    def print_test(self, test_name):
        print(f"{Fore.YELLOW}Testing:{Style.RESET_ALL} {test_name}")
        
    def print_success(self, message):
        print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {message}")
        self.test_results.append(("PASS", message))
        
    def print_failure(self, message):
        print(f"  {Fore.RED}✗{Style.RESET_ALL} {message}")
        self.test_results.append(("FAIL", message))
        
    def print_info(self, message):
        print(f"  {Fore.BLUE}ℹ{Style.RESET_ALL} {message}")
        
    def create_test_files(self):
        """Create all necessary test Excel files"""
        self.print_header("Creating Test Files")
        
        if not os.path.exists(self.test_files_dir):
            os.makedirs(self.test_files_dir)
            
        # Test 1: Valid employee data
        valid_data = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
            'First Name': ['John', 'Jane', 'Bob', 'Alice', 'Charlie'],
            'Last Name': ['Doe', 'Smith', 'Johnson', 'Williams', 'Brown'],
            'Crew': ['A', 'B', 'C', 'D', 'A'],
            'Position': ['Operator', 'Lead Operator', 'Supervisor', 'Operator', 'Technician'],
            'Department': ['Production', 'Production', 'Management', 'Production', 'Maintenance'],
            'Hire Date': ['2020-01-15', '2019-05-20', '2018-03-10', '2021-07-01', '2022-02-28'],
            'Email': ['john.doe@company.com', 'jane.smith@company.com', '', 'alice.w@company.com', ''],
            'Phone': ['555-0101', '555-0102', '555-0103', '', '555-0105']
        }
        df = pd.DataFrame(valid_data)
        df.to_excel(f"{self.test_files_dir}/test_valid_employees.xlsx", index=False, sheet_name='Employee Data')
        self.print_success("Created test_valid_employees.xlsx")
        
        # Test 2: Invalid data (various errors)
        invalid_data = {
            'Employee ID': ['EMP001', '', 'EMP003', 'EMP004', 'EMP001'],  # Missing ID, Duplicate
            'First Name': ['John', 'Jane', '', 'Alice', 'Charlie'],  # Missing first name
            'Last Name': ['Doe', 'Smith', 'Johnson', 'Williams', 'Brown'],
            'Crew': ['A', 'B', 'E', '5', 'A'],  # Invalid crew values
            'Position': ['Operator', 'Lead Operator', 'Supervisor', 'Operator', 'Technician'],
            'Department': ['Production', 'Production', 'Management', 'Production', 'Maintenance'],
            'Hire Date': ['2020-01-15', '2019-05-20', 'invalid-date', '2021-07-01', '2022-02-28'],
            'Email': ['john.doe@company', 'not-an-email', 'bob.j@company.com', 'alice.w@company.com', 'charlie@company.com']
        }
        df = pd.DataFrame(invalid_data)
        df.to_excel(f"{self.test_files_dir}/test_invalid_employees.xlsx", index=False, sheet_name='Employee Data')
        self.print_success("Created test_invalid_employees.xlsx")
        
        # Test 3: Large dataset
        large_data = {
            'Employee ID': [f'EMP{str(i).zfill(4)}' for i in range(1, 501)],
            'First Name': [f'FirstName{i}' for i in range(1, 501)],
            'Last Name': [f'LastName{i}' for i in range(1, 501)],
            'Crew': ['A', 'B', 'C', 'D'] * 125,
            'Position': ['Operator'] * 400 + ['Lead Operator'] * 50 + ['Supervisor'] * 25 + ['Technician'] * 25,
            'Department': ['Production'] * 400 + ['Management'] * 50 + ['Maintenance'] * 50,
            'Hire Date': ['2020-01-15'] * 500,
            'Email': [f'employee{i}@company.com' for i in range(1, 501)],
            'Phone': [f'555-{str(i).zfill(4)}' for i in range(1, 501)]
        }
        df = pd.DataFrame(large_data)
        df.to_excel(f"{self.test_files_dir}/test_large_dataset.xlsx", index=False, sheet_name='Employee Data')
        self.print_success("Created test_large_dataset.xlsx (500 employees)")
        
        # Test 4: Overtime data
        ot_data = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
            'Employee Name': ['John Doe', 'Jane Smith', 'Bob Johnson', 'Alice Williams', 'Charlie Brown']
        }
        # Add 13 weeks of OT data
        for week in range(1, 14):
            ot_data[f'Week {week}'] = [8, 4, 0, 12, 16] if week % 2 == 0 else [0, 8, 4, 8, 12]
        df = pd.DataFrame(ot_data)
        df.to_excel(f"{self.test_files_dir}/test_overtime_history.xlsx", index=False, sheet_name='Overtime Data')
        self.print_success("Created test_overtime_history.xlsx")
        
        # Test 5: Update existing employees
        update_data = {
            'Employee ID': ['EMP001', 'EMP002', 'EMP003', 'EMP004', 'EMP005'],
            'First Name': ['John', 'Jane', 'Robert', 'Alice', 'Charles'],  # Changed Bob to Robert, Charlie to Charles
            'Last Name': ['Doe', 'Smith-Johnson', 'Johnson', 'Williams', 'Brown'],  # Changed Jane's last name
            'Crew': ['B', 'B', 'C', 'D', 'A'],  # Changed John from A to B
            'Position': ['Lead Operator', 'Lead Operator', 'Supervisor', 'Supervisor', 'Technician'],  # Promotions
            'Department': ['Production', 'Production', 'Management', 'Management', 'Maintenance'],
            'Hire Date': ['2020-01-15', '2019-05-20', '2018-03-10', '2021-07-01', '2022-02-28'],
            'Email': ['john.doe@company.com', 'jane.sj@company.com', 'robert.j@company.com', 'alice.w@company.com', 'charles.b@company.com'],
            'Phone': ['555-0101', '555-0102', '555-0103', '555-0104', '555-0105']
        }
        df = pd.DataFrame(update_data)
        df.to_excel(f"{self.test_files_dir}/test_update_employees.xlsx", index=False, sheet_name='Employee Data')
        self.print_success("Created test_update_employees.xlsx")
        
        # Test 6: Empty file
        df_empty = pd.DataFrame()
        df_empty.to_excel(f"{self.test_files_dir}/test_empty.xlsx", index=False)
        self.print_success("Created test_empty.xlsx")
        
        # Test 7: Wrong sheet name
        df = pd.DataFrame(valid_data)
        df.to_excel(f"{self.test_files_dir}/test_wrong_sheet.xlsx", index=False, sheet_name='Wrong Name')
        self.print_success("Created test_wrong_sheet.xlsx")
        
    def login(self):
        """Login as supervisor"""
        self.print_test("Login Authentication")
        try:
            response = self.session.post(f"{self.base_url}/login", data={
                'username': self.username,
                'password': self.password
            })
            if response.status_code == 200:
                self.print_success(f"Logged in as {self.username}")
                return True
            else:
                self.print_failure(f"Login failed: {response.status_code}")
                return False
        except Exception as e:
            self.print_failure(f"Login error: {str(e)}")
            return False
            
    def test_upload_page_access(self):
        """Test access to upload pages"""
        self.print_test("Upload Page Access")
        
        pages = [
            "/upload-employees",
            "/upload-overtime", 
            "/upload-history"
        ]
        
        for page in pages:
            try:
                response = self.session.get(f"{self.base_url}{page}")
                if response.status_code == 200:
                    self.print_success(f"Accessed {page}")
                else:
                    self.print_failure(f"Cannot access {page}: {response.status_code}")
            except Exception as e:
                self.print_failure(f"Error accessing {page}: {str(e)}")
                
    def test_template_downloads(self):
        """Test template download functionality"""
        self.print_test("Template Downloads")
        
        templates = [
            ("/download-employee-template", "employee_template.xlsx"),
            ("/download-overtime-template", "overtime_template.xlsx")
        ]
        
        for endpoint, filename in templates:
            try:
                response = self.session.get(f"{self.base_url}{endpoint}")
                if response.status_code == 200:
                    # Save template
                    with open(f"{self.test_files_dir}/{filename}", 'wb') as f:
                        f.write(response.content)
                    self.print_success(f"Downloaded {filename}")
                    
                    # Verify it's a valid Excel file
                    try:
                        pd.read_excel(f"{self.test_files_dir}/{filename}")
                        self.print_success(f"Verified {filename} is valid Excel")
                    except:
                        self.print_failure(f"{filename} is not valid Excel")
                else:
                    self.print_failure(f"Cannot download {filename}: {response.status_code}")
            except Exception as e:
                self.print_failure(f"Error downloading {filename}: {str(e)}")
                
    def test_file_validation(self):
        """Test file validation endpoint"""
        self.print_test("File Validation")
        
        test_cases = [
            ("test_valid_employees.xlsx", True, "Valid employee data"),
            ("test_invalid_employees.xlsx", False, "Invalid employee data"),
            ("test_empty.xlsx", False, "Empty file"),
            ("test_wrong_sheet.xlsx", False, "Wrong sheet name")
        ]
        
        for filename, should_pass, description in test_cases:
            self.print_info(f"Testing: {description}")
            
            try:
                with open(f"{self.test_files_dir}/{filename}", 'rb') as f:
                    files = {'file': (filename, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                    data = {'type': 'employee'}
                    response = self.session.post(f"{self.base_url}/validate-upload", files=files, data=data)
                    
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success') == should_pass:
                        self.print_success(f"Validation result correct: {description}")
                        if not should_pass and 'errors' in result:
                            self.print_info(f"Errors detected: {len(result['errors'])}")
                    else:
                        self.print_failure(f"Unexpected validation result for {description}")
                else:
                    self.print_failure(f"Validation failed with status {response.status_code}")
            except Exception as e:
                self.print_failure(f"Error validating {filename}: {str(e)}")
                
    def test_employee_upload(self):
        """Test actual employee upload"""
        self.print_test("Employee Upload (Replace All)")
        
        try:
            with open(f"{self.test_files_dir}/test_valid_employees.xlsx", 'rb') as f:
                files = {'file': (f.name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                data = {
                    'upload_type': 'employee',
                    'replace_all': 'true'
                }
                response = self.session.post(f"{self.base_url}/upload-employees", files=files, data=data)
                
            if response.status_code == 200:
                self.print_success("Employee upload successful")
                
                # Verify employees were created
                response = self.session.get(f"{self.base_url}/api/employees")
                if response.status_code == 200:
                    employees = response.json()
                    if len(employees) >= 5:
                        self.print_success(f"Verified {len(employees)} employees in system")
                    else:
                        self.print_failure(f"Expected 5+ employees, found {len(employees)}")
            else:
                self.print_failure(f"Upload failed with status {response.status_code}")
        except Exception as e:
            self.print_failure(f"Error uploading employees: {str(e)}")
            
    def test_update_employees(self):
        """Test employee update functionality"""
        self.print_test("Employee Update (Merge)")
        
        try:
            # First, note current employee count
            response = self.session.get(f"{self.base_url}/api/employees")
            initial_count = len(response.json()) if response.status_code == 200 else 0
            
            with open(f"{self.test_files_dir}/test_update_employees.xlsx", 'rb') as f:
                files = {'file': (f.name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                data = {
                    'upload_type': 'employee',
                    'replace_all': 'false'  # Update mode
                }
                response = self.session.post(f"{self.base_url}/upload-employees", files=files, data=data)
                
            if response.status_code == 200:
                self.print_success("Employee update successful")
                
                # Verify employee count didn't change
                response = self.session.get(f"{self.base_url}/api/employees")
                final_count = len(response.json()) if response.status_code == 200 else 0
                
                if final_count == initial_count:
                    self.print_success(f"Employee count preserved: {final_count}")
                else:
                    self.print_failure(f"Employee count changed: {initial_count} → {final_count}")
                    
                # TODO: Verify specific updates (crew changes, name changes, etc.)
            else:
                self.print_failure(f"Update failed with status {response.status_code}")
        except Exception as e:
            self.print_failure(f"Error updating employees: {str(e)}")
            
    def test_overtime_upload(self):
        """Test overtime history upload"""
        self.print_test("Overtime History Upload")
        
        try:
            with open(f"{self.test_files_dir}/test_overtime_history.xlsx", 'rb') as f:
                files = {'file': (f.name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                data = {
                    'upload_type': 'overtime',
                    'replace_all': 'true'
                }
                response = self.session.post(f"{self.base_url}/upload-overtime", files=files, data=data)
                
            if response.status_code == 200:
                self.print_success("Overtime upload successful")
                # TODO: Verify overtime data in system
            else:
                self.print_failure(f"Overtime upload failed with status {response.status_code}")
        except Exception as e:
            self.print_failure(f"Error uploading overtime: {str(e)}")
            
    def test_upload_history(self):
        """Test upload history tracking"""
        self.print_test("Upload History")
        
        try:
            response = self.session.get(f"{self.base_url}/upload-history")
            if response.status_code == 200:
                self.print_success("Accessed upload history")
                
                # Check for API endpoint
                response = self.session.get(f"{self.base_url}/api/upload-history")
                if response.status_code == 200:
                    history = response.json()
                    if len(history) > 0:
                        self.print_success(f"Found {len(history)} upload records")
                        # Display recent uploads
                        for upload in history[:3]:
                            self.print_info(f"Upload: {upload.get('filename', 'Unknown')} - {upload.get('status', 'Unknown')}")
                    else:
                        self.print_failure("No upload history found")
            else:
                self.print_failure(f"Cannot access upload history: {response.status_code}")
        except Exception as e:
            self.print_failure(f"Error accessing upload history: {str(e)}")
            
    def test_large_file_performance(self):
        """Test performance with large files"""
        self.print_test("Large File Performance")
        
        try:
            start_time = time.time()
            
            with open(f"{self.test_files_dir}/test_large_dataset.xlsx", 'rb') as f:
                files = {'file': (f.name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
                data = {'type': 'employee'}
                response = self.session.post(f"{self.base_url}/validate-upload", files=files, data=data)
                
            validation_time = time.time() - start_time
            
            if response.status_code == 200:
                self.print_success(f"Large file validation completed in {validation_time:.2f} seconds")
                
                if validation_time < 10:
                    self.print_success("Performance: Excellent (< 10 seconds)")
                elif validation_time < 30:
                    self.print_success("Performance: Good (< 30 seconds)")
                else:
                    self.print_failure(f"Performance: Poor ({validation_time:.2f} seconds)")
            else:
                self.print_failure(f"Large file validation failed: {response.status_code}")
        except Exception as e:
            self.print_failure(f"Error testing large file: {str(e)}")
            
    def test_security(self):
        """Test security controls"""
        self.print_test("Security Controls")
        
        # Test 1: Non-supervisor access
        self.print_info("Testing non-supervisor access")
        self.session = requests.Session()  # New session
        
        try:
            # Try to access without login
            response = self.session.get(f"{self.base_url}/upload-employees")
            if response.status_code in [401, 403, 302]:  # Unauthorized, Forbidden, or Redirect
                self.print_success("Upload page protected from anonymous access")
            else:
                self.print_failure("Upload page accessible without login!")
                
            # Try with non-supervisor login (if available)
            # TODO: Add test for non-supervisor user if credentials available
            
        except Exception as e:
            self.print_failure(f"Security test error: {str(e)}")
            
        # Re-login as supervisor for remaining tests
        self.session = requests.Session()
        self.login()
        
    def test_error_handling(self):
        """Test error handling scenarios"""
        self.print_test("Error Handling")
        
        # Test 1: Non-Excel file
        self.print_info("Testing non-Excel file upload")
        try:
            # Create a text file
            with open(f"{self.test_files_dir}/test.txt", 'w') as f:
                f.write("This is not an Excel file")
                
            with open(f"{self.test_files_dir}/test.txt", 'rb') as f:
                files = {'file': ('test.txt', f, 'text/plain')}
                data = {'upload_type': 'employee'}
                response = self.session.post(f"{self.base_url}/upload-employees", files=files, data=data)
                
            if response.status_code in [400, 422]:  # Bad request or Unprocessable
                self.print_success("Non-Excel file rejected properly")
            else:
                self.print_failure(f"Non-Excel file not rejected: {response.status_code}")
        except Exception as e:
            self.print_failure(f"Error handling test failed: {str(e)}")
            
        # Test 2: Missing required fields
        self.print_info("Testing missing upload_type")
        try:
            with open(f"{self.test_files_dir}/test_valid_employees.xlsx", 'rb') as f:
                files = {'file': (f.name, f)}
                # Missing upload_type
                response = self.session.post(f"{self.base_url}/upload-employees", files=files)
                
            if response.status_code in [400, 422]:
                self.print_success("Missing required field handled properly")
            else:
                self.print_failure(f"Missing field not caught: {response.status_code}")
        except Exception as e:
            self.print_failure(f"Error handling test failed: {str(e)}")
            
    def generate_report(self):
        """Generate final test report"""
        self.print_header("Test Summary Report")
        
        passed = sum(1 for result, _ in self.test_results if result == "PASS")
        failed = sum(1 for result, _ in self.test_results if result == "FAIL")
        total = len(self.test_results)
        
        print(f"{Fore.CYAN}Total Tests:{Style.RESET_ALL} {total}")
        print(f"{Fore.GREEN}Passed:{Style.RESET_ALL} {passed}")
        print(f"{Fore.RED}Failed:{Style.RESET_ALL} {failed}")
        print(f"{Fore.YELLOW}Success Rate:{Style.RESET_ALL} {(passed/total*100):.1f}%")
        
        if failed > 0:
            print(f"\n{Fore.RED}Failed Tests:{Style.RESET_ALL}")
            for result, message in self.test_results:
                if result == "FAIL":
                    print(f"  - {message}")
                    
        # Save detailed report
        with open("test_report.txt", "w") as f:
            f.write(f"Excel Upload System Test Report\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"Summary:\n")
            f.write(f"  Total Tests: {total}\n")
            f.write(f"  Passed: {passed}\n")
            f.write(f"  Failed: {failed}\n")
            f.write(f"  Success Rate: {(passed/total*100):.1f}%\n\n")
            f.write(f"Detailed Results:\n")
            for result, message in self.test_results:
                f.write(f"  [{result}] {message}\n")
                
        print(f"\n{Fore.CYAN}Detailed report saved to test_report.txt{Style.RESET_ALL}")
        
        return failed == 0
        
    def run_all_tests(self):
        """Run complete test suite"""
        self.print_header("Excel Upload System Test Suite")
        print(f"Target: {self.base_url}")
        print(f"User: {self.username}")
        print(f"Time: {datetime.now()}\n")
        
        # Create test files
        self.create_test_files()
        
        # Login
        if not self.login():
            print(f"\n{Fore.RED}Cannot proceed without login!{Style.RESET_ALL}")
            return False
            
        # Run all tests
        self.test_upload_page_access()
        self.test_template_downloads()
        self.test_file_validation()
        self.test_employee_upload()
        self.test_update_employees()
        self.test_overtime_upload()
        self.test_upload_history()
        self.test_large_file_performance()
        self.test_security()
        self.test_error_handling()
        
        # Generate report
        return self.generate_report()


def main():
    """Main test runner"""
    # Parse command line arguments
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    username = sys.argv[2] if len(sys.argv) > 2 else "supervisor"
    password = sys.argv[3] if len(sys.argv) > 3 else "password"
    
    # Create and run tester
    tester = ExcelUploadTester(base_url, username, password)
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
