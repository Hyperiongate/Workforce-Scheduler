# utils/account_generator.py
"""
Automatic account generation for employees
Handles username creation, password generation, and duplicate handling
"""

import random
import string
from datetime import datetime
from werkzeug.security import generate_password_hash
from flask import session

class AccountGenerator:
    """Generate user accounts for employees"""
    
    def __init__(self, db):
        self.db = db
        
    def generate_username(self, first_name, last_name, existing_usernames=None):
        """
        Generate username from first initial + last name
        Handle duplicates by adding numbers
        """
        # Clean names - handle full name field
        if not last_name and first_name:
            # If only one name field is used (full name in first_name)
            name_parts = first_name.strip().split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
            else:
                first_name = name_parts[0] if name_parts else 'user'
                last_name = 'user'
        
        first_name = first_name.strip().lower()
        last_name = last_name.strip().lower()
        
        # Remove special characters
        first_name = ''.join(c for c in first_name if c.isalnum())
        last_name = ''.join(c for c in last_name if c.isalnum())
        
        # Base username: first initial + last name
        base_username = f"{first_name[0]}{last_name}" if first_name and last_name else None
        
        if not base_username:
            # Fallback for edge cases
            base_username = f"user{random.randint(1000, 9999)}"
            
        # Get existing usernames if not provided
        if existing_usernames is None:
            from models import Employee
            existing_usernames = {emp.username for emp in Employee.query.all() if emp.username}
            
        # Handle duplicates
        username = base_username
        counter = 2
        
        while username in existing_usernames:
            username = f"{base_username}{counter}"
            counter += 1
            
        return username
        
    def generate_password(self):
        """Generate a secure temporary password"""
        # Default pattern: TempPass + 3 digits + special char
        digits = ''.join(random.choices(string.digits, k=3))
        special = random.choice('!@#$%')
        return f"TempPass{digits}{special}"
        
    def create_account_for_employee(self, employee):
        """Create account for a single employee"""
        if employee.username:
            # Already has account
            return None
            
        # Generate username - use name field
        username = self.generate_username(employee.name, '')
        
        # Generate password
        temp_password = self.generate_password()
        
        # Update employee record
        employee.username = username
        employee.set_password(temp_password)  # Use the set_password method
        employee.must_change_password = True
        employee.first_login = True
        employee.account_created_date = datetime.utcnow()
        
        # Save to database
        self.db.session.commit()
        
        return {
            'employee_id': employee.employee_id,
            'name': employee.name,
            'username': username,
            'temp_password': temp_password,
            'created': datetime.utcnow()
        }
        
    def create_accounts_bulk(self, employees):
        """Create accounts for multiple employees"""
        results = {
            'created': [],
            'skipped': [],
            'errors': []
        }
        
        # Get all existing usernames for efficiency
        from models import Employee
        existing_usernames = {emp.username for emp in Employee.query.all() if emp.username}
        
        for employee in employees:
            try:
                if employee.username:
                    results['skipped'].append({
                        'employee_id': employee.employee_id,
                        'name': employee.name,
                        'reason': 'Already has account'
                    })
                    continue
                    
                # Generate unique username
                username = self.generate_username(employee.name, '', existing_usernames)
                existing_usernames.add(username)  # Add to set for next iterations
                
                # Generate password
                temp_password = self.generate_password()
                
                # Update employee
                employee.username = username
                employee.set_password(temp_password)  # Use the set_password method
                employee.must_change_password = True
                employee.first_login = True
                employee.account_created_date = datetime.utcnow()
                
                results['created'].append({
                    'employee_id': employee.employee_id,
                    'name': employee.name,
                    'username': username,
                    'temp_password': temp_password
                })
                
            except Exception as e:
                results['errors'].append({
                    'employee_id': employee.employee_id,
                    'name': employee.name,
                    'error': str(e)
                })
                
        # Commit all changes
        if results['created']:
            self.db.session.commit()
            
        return results
        
    def generate_credentials_report(self, account_list):
        """Generate a formatted report of credentials"""
        report = []
        report.append("=" * 70)
        report.append("EMPLOYEE ACCOUNT CREDENTIALS")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 70)
        report.append("")
        report.append("IMPORTANT: These are temporary passwords. Users must change them on first login.")
        report.append("")
        report.append("-" * 70)
        report.append(f"{'Employee ID':<12} {'Name':<25} {'Username':<15} {'Temp Password':<15}")
        report.append("-" * 70)
        
        for account in account_list:
            report.append(
                f"{account['employee_id']:<12} "
                f"{account['name'][:24]:<25} "
                f"{account['username']:<15} "
                f"{account['temp_password']:<15}"
            )
            
        report.append("-" * 70)
        report.append(f"Total accounts created: {len(account_list)}")
        report.append("")
        report.append("Instructions for users:")
        report.append("1. Go to the login page")
        report.append("2. Enter your username and temporary password")
        report.append("3. You will be prompted to create a new password")
        report.append("4. Password must be at least 8 characters with mixed case and numbers")
        report.append("")
        
        return '\n'.join(report)
        
    def export_credentials_excel(self, account_list, filename='credentials.xlsx'):
        """Export credentials to Excel file"""
        import pandas as pd
        
        df = pd.DataFrame(account_list)
        df = df[['employee_id', 'name', 'username', 'temp_password']]
        df.columns = ['Employee ID', 'Name', 'Username', 'Temporary Password']
        
        # Create Excel writer with formatting
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Credentials', index=False)
            
            # Get the worksheet
            worksheet = writer.sheets['Credentials']
            
            # Adjust column widths
            worksheet.column_dimensions['A'].width = 15
            worksheet.column_dimensions['B'].width = 30
            worksheet.column_dimensions['C'].width = 20
            worksheet.column_dimensions['D'].width = 20
            
            # Add instructions sheet
            instructions_data = {
                'Instructions': [
                    'Employee Account Access Instructions',
                    '',
                    '1. Go to the system login page',
                    '2. Enter your username and temporary password',
                    '3. You will be required to change your password on first login',
                    '4. Your new password must be at least 8 characters',
                    '5. Include uppercase, lowercase, and numbers for security',
                    '',
                    'IMPORTANT: Keep your login credentials secure!',
                    'Do not share your password with anyone.',
                    '',
                    'If you have issues logging in, contact your supervisor.'
                ]
            }
            
            df_instructions = pd.DataFrame(instructions_data)
            df_instructions.to_excel(writer, sheet_name='Instructions', index=False, header=False)
            
        return filename


# Integration with employee import
def create_accounts_after_import(employees, db):
    """Helper function to create accounts after employee import"""
    generator = AccountGenerator(db)
    results = generator.create_accounts_bulk(employees)
    
    # Generate reports
    if results['created']:
        # Text report
        text_report = generator.generate_credentials_report(results['created'])
        
        # Save to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f'credentials_{timestamp}.txt'
        
        # Use app config for upload folder
        from flask import current_app
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        
        # Ensure upload folder exists
        import os
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            
        text_path = os.path.join(upload_folder, report_filename)
        with open(text_path, 'w') as f:
            f.write(text_report)
            
        # Excel report
        excel_filename = f'credentials_{timestamp}.xlsx'
        excel_path = os.path.join(upload_folder, excel_filename)
        generator.export_credentials_excel(results['created'], excel_path)
        
        return {
            'success': True,
            'created_count': len(results['created']),
            'skipped_count': len(results['skipped']),
            'error_count': len(results['errors']),
            'text_report': report_filename,
            'excel_report': excel_filename,
            'results': results
        }
    else:
        return {
            'success': False,
            'message': 'No accounts created',
            'results': results
        }
