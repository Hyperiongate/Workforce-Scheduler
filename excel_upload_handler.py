# utils/excel_upload_handler.py
"""
Complete Excel Upload Handler for Workforce Scheduler
PRODUCTION-READY VERSION - Deploy this entire file

This module provides comprehensive Excel file processing capabilities:
- File validation and sanitization
- Data type conversion and cleaning
- Business rule validation
- Error reporting and logging
- Batch processing for large files
- Transaction management for database operations
"""

import pandas as pd
import numpy as np
import logging
import re
import hashlib
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from werkzeug.utils import secure_filename
import json
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

# Set up logging
logger = logging.getLogger(__name__)

class ExcelFileValidator:
    """Validate Excel files before processing"""
    
    def __init__(self, max_file_size_mb=16, allowed_extensions=None):
        self.max_file_size = max_file_size_mb * 1024 * 1024  # Convert to bytes
        self.allowed_extensions = allowed_extensions or ['.xlsx', '.xls']
        self.errors = []
        self.warnings = []
    
    def validate_file(self, file_path: str, filename: str) -> Dict[str, Any]:
        """
        Comprehensive file validation
        
        Args:
            file_path: Path to the uploaded file
            filename: Original filename
            
        Returns:
            Dict with validation results
        """
        self.errors.clear()
        self.warnings.clear()
        
        try:
            # Check file existence
            if not os.path.exists(file_path):
                self.errors.append("File not found or inaccessible")
                return self._validation_result()
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.max_file_size:
                self.errors.append(f"File size ({file_size / 1024 / 1024:.1f}MB) exceeds limit ({self.max_file_size / 1024 / 1024}MB)")
                return self._validation_result()
            
            # Check file extension
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext not in self.allowed_extensions:
                self.errors.append(f"Invalid file type. Allowed types: {', '.join(self.allowed_extensions)}")
                return self._validation_result()
            
            # Try to read the file
            try:
                df = pd.read_excel(file_path, nrows=1)  # Just read first row to test
                if df.empty:
                    self.errors.append("File appears to be empty")
                    return self._validation_result()
            except Exception as e:
                self.errors.append(f"Unable to read Excel file: {str(e)}")
                return self._validation_result()
            
            # Generate file hash for integrity
            file_hash = self._generate_file_hash(file_path)
            
            return {
                'valid': True,
                'file_size': file_size,
                'file_hash': file_hash,
                'errors': [],
                'warnings': self.warnings
            }
            
        except Exception as e:
            logger.error(f"Error validating file {filename}: {e}")
            self.errors.append(f"Unexpected validation error: {str(e)}")
            return self._validation_result()
    
    def _generate_file_hash(self, file_path: str) -> str:
        """Generate SHA-256 hash of file for integrity checking"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _validation_result(self) -> Dict[str, Any]:
        """Return formatted validation result"""
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'file_size': 0,
            'file_hash': None
        }


class ExcelDataValidator:
    """Validate Excel data content and structure"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.stats = {}
    
    def validate_employee_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Comprehensive validation for employee data
        
        Args:
            df: Pandas DataFrame containing employee data
            
        Returns:
            Dict with validation results and statistics
        """
        self.errors.clear()
        self.warnings.clear()
        self.stats.clear()
        
        logger.info(f"Validating employee data: {len(df)} rows")
        
        # Check if dataframe is empty
        if df.empty:
            self.errors.append("No data found in the uploaded file")
            return self._employee_validation_result(df)
        
        # Clean column names (remove extra spaces, standardize)
        df.columns = df.columns.str.strip()
        
        # Define required columns for employee data
        required_columns = [
            'Employee ID', 'First Name', 'Last Name', 
            'Crew Assigned', 'Current Job Position'
        ]
        
        optional_columns = [
            'Email', 'Phone', 'Hire Date', 'Department', 
            'Supervisor', 'Status', 'Notes'
        ]
        
        # Check for required columns
        missing_required = [col for col in required_columns if col not in df.columns]
        if missing_required:
            self.errors.append(
                f"Missing required columns: {', '.join(missing_required)}. "
                f"Available columns: {', '.join(df.columns)}"
            )
            return self._employee_validation_result(df)
        
        # Check for recommended columns
        missing_optional = [col for col in optional_columns if col not in df.columns]
        if missing_optional:
            self.warnings.append(
                f"Optional columns not found: {', '.join(missing_optional)}. "
                "These can be added later if needed."
            )
        
        # Validate each row
        valid_employees = 0
        employee_ids = set()
        emails = set()
        crews = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        positions = {}
        
        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel row number (1-indexed + header)
            row_valid = True
            
            # Employee ID validation
            emp_id = self._clean_string(row.get('Employee ID', ''))
            if not emp_id:
                self.errors.append(f"Row {row_num}: Missing Employee ID")
                row_valid = False
            elif emp_id in employee_ids:
                self.errors.append(f"Row {row_num}: Duplicate Employee ID '{emp_id}'")
                row_valid = False
            else:
                employee_ids.add(emp_id)
                
            # Validate ID format (if you have specific requirements)
            if emp_id and not re.match(r'^[A-Za-z0-9]{3,20}$', emp_id):
                self.warnings.append(f"Row {row_num}: Employee ID '{emp_id}' should be 3-20 alphanumeric characters")
            
            # Name validation
            first_name = self._clean_string(row.get('First Name', ''))
            last_name = self._clean_string(row.get('Last Name', ''))
            
            if not first_name:
                self.errors.append(f"Row {row_num}: Missing First Name")
                row_valid = False
            elif len(first_name) < 2:
                self.warnings.append(f"Row {row_num}: First name seems too short: '{first_name}'")
                
            if not last_name:
                self.errors.append(f"Row {row_num}: Missing Last Name")
                row_valid = False
            elif len(last_name) < 2:
                self.warnings.append(f"Row {row_num}: Last name seems too short: '{last_name}'")
            
            # Crew validation
            crew = self._clean_string(row.get('Crew Assigned', '')).upper()
            if not crew:
                self.errors.append(f"Row {row_num}: Missing Crew Assignment")
                row_valid = False
            elif crew not in ['A', 'B', 'C', 'D']:
                self.errors.append(f"Row {row_num}: Invalid crew '{crew}'. Must be A, B, C, or D")
                row_valid = False
            else:
                crews[crew] += 1
            
            # Position validation
            position = self._clean_string(row.get('Current Job Position', ''))
            if not position:
                self.errors.append(f"Row {row_num}: Missing Current Job Position")
                row_valid = False
            else:
                positions[position] = positions.get(position, 0) + 1
            
            # Email validation (if provided)
            email = self._clean_string(row.get('Email', ''))
            if email:
                if not self._validate_email(email):
                    self.errors.append(f"Row {row_num}: Invalid email format '{email}'")
                    row_valid = False
                elif email in emails:
                    self.errors.append(f"Row {row_num}: Duplicate email '{email}'")
                    row_valid = False
                else:
                    emails.add(email)
            
            # Phone validation (if provided)
            phone = self._clean_string(row.get('Phone', ''))
            if phone and not self._validate_phone(phone):
                self.warnings.append(f"Row {row_num}: Phone number format may be invalid: '{phone}'")
            
            # Hire date validation (if provided)
            if 'Hire Date' in df.columns:
                hire_date = row.get('Hire Date')
                if pd.notna(hire_date) and not self._validate_date(hire_date):
                    self.warnings.append(f"Row {row_num}: Invalid or suspicious hire date: '{hire_date}'")
            
            if row_valid:
                valid_employees += 1
            
            # Stop if too many errors
            if len(self.errors) > 100:
                self.errors.append(f"Too many errors found (100+). Please fix the major issues and try again.")
                break
        
        # Business rule validations
        self._validate_crew_balance(crews, len(df))
        self._validate_position_distribution(positions, len(df))
        
        # Store statistics
        self.stats = {
            'total_rows': len(df),
            'valid_employees': valid_employees,
            'invalid_employees': len(df) - valid_employees,
            'unique_employee_ids': len(employee_ids),
            'unique_emails': len(emails),
            'crew_distribution': crews,
            'position_distribution': positions,
            'columns_found': list(df.columns),
            'required_columns_missing': [],
            'optional_columns_missing': missing_optional
        }
        
        return self._employee_validation_result(df)
    
    def validate_overtime_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Validate overtime data
        
        Args:
            df: Pandas DataFrame containing overtime data
            
        Returns:
            Dict with validation results
        """
        self.errors.clear()
        self.warnings.clear()
        self.stats.clear()
        
        logger.info(f"Validating overtime data: {len(df)} rows")
        
        if df.empty:
            self.errors.append("No overtime data found in the uploaded file")
            return self._overtime_validation_result(df)
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Required columns for overtime
        required_columns = [
            'Employee ID', 'Week Start Date', 'Regular Hours', 
            'Overtime Hours', 'Total Hours'
        ]
        
        missing_required = [col for col in required_columns if col not in df.columns]
        if missing_required:
            self.errors.append(f"Missing required columns: {', '.join(missing_required)}")
            return self._overtime_validation_result(df)
        
        valid_records = 0
        employee_ids = set()
        total_ot_hours = 0
        high_ot_employees = []
        week_dates = set()
        
        for idx, row in df.iterrows():
            row_num = idx + 2
            row_valid = True
            
            # Employee ID
            emp_id = self._clean_string(row.get('Employee ID', ''))
            if not emp_id:
                self.errors.append(f"Row {row_num}: Missing Employee ID")
                row_valid = False
            else:
                employee_ids.add(emp_id)
            
            # Week Start Date validation
            week_start = row.get('Week Start Date')
            try:
                if pd.isna(week_start):
                    self.errors.append(f"Row {row_num}: Missing Week Start Date")
                    row_valid = False
                else:
                    week_date = pd.to_datetime(week_start)
                    # Check if it's a Monday
                    if week_date.weekday() != 0:
                        self.warnings.append(f"Row {row_num}: Week start date ({week_date.strftime('%Y-%m-%d')}) is not a Monday")
                    week_dates.add(week_date.date())
            except:
                self.errors.append(f"Row {row_num}: Invalid Week Start Date format")
                row_valid = False
            
            # Hours validation
            try:
                regular_hours = float(row.get('Regular Hours', 0))
                overtime_hours = float(row.get('Overtime Hours', 0))
                total_hours = float(row.get('Total Hours', 0))
                
                # Validation rules for hours
                if regular_hours < 0:
                    self.errors.append(f"Row {row_num}: Regular hours cannot be negative ({regular_hours})")
                    row_valid = False
                
                if overtime_hours < 0:
                    self.errors.append(f"Row {row_num}: Overtime hours cannot be negative ({overtime_hours})")
                    row_valid = False
                
                if total_hours < 0:
                    self.errors.append(f"Row {row_num}: Total hours cannot be negative ({total_hours})")
                    row_valid = False
                
                # Check if total equals regular + overtime
                expected_total = regular_hours + overtime_hours
                if abs(total_hours - expected_total) > 0.01:  # Allow for small rounding differences
                    self.errors.append(
                        f"Row {row_num}: Total hours ({total_hours}) doesn't match "
                        f"Regular + Overtime ({expected_total})"
                    )
                    row_valid = False
                
                # Business rule checks
                if total_hours > 80:
                    self.warnings.append(f"Row {row_num}: Very high total hours ({total_hours}) for employee {emp_id}")
                    high_ot_employees.append(emp_id)
                
                if overtime_hours > 40:
                    self.warnings.append(f"Row {row_num}: Very high overtime hours ({overtime_hours}) for employee {emp_id}")
                
                if regular_hours > 60:
                    self.warnings.append(f"Row {row_num}: Very high regular hours ({regular_hours}) for employee {emp_id}")
                
                if row_valid:
                    total_ot_hours += overtime_hours
                
            except (ValueError, TypeError):
                self.errors.append(f"Row {row_num}: Invalid hour values - must be numbers")
                row_valid = False
            
            if row_valid:
                valid_records += 1
            
            # Stop if too many errors
            if len(self.errors) > 100:
                self.errors.append("Too many errors found. Please fix the major issues and try again.")
                break
        
        # Calculate statistics
        self.stats = {
            'total_rows': len(df),
            'valid_records': valid_records,
            'invalid_records': len(df) - valid_records,
            'unique_employees': len(employee_ids),
            'total_ot_hours': total_ot_hours,
            'avg_ot_per_employee': total_ot_hours / len(employee_ids) if employee_ids else 0,
            'high_ot_employees': list(set(high_ot_employees)),
            'date_range': {
                'start': min(week_dates) if week_dates else None,
                'end': max(week_dates) if week_dates else None,
                'weeks_covered': len(week_dates)
            }
        }
        
        return self._overtime_validation_result(df)
    
    def _clean_string(self, value) -> str:
        """Clean and normalize string values"""
        if pd.isna(value):
            return ''
        return str(value).strip()
    
    def _validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_phone(self, phone: str) -> bool:
        """Validate phone number format (flexible)"""
        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)
        # Check if it's a reasonable length (7-15 digits)
        return 7 <= len(digits) <= 15
    
    def _validate_date(self, date_value) -> bool:
        """Validate date value"""
        try:
            if pd.isna(date_value):
                return True  # Optional field
            
            parsed_date = pd.to_datetime(date_value)
            
            # Check if date is reasonable (not too far in the past or future)
            today = datetime.now()
            min_date = today - timedelta(days=365 * 50)  # 50 years ago
            max_date = today + timedelta(days=365 * 2)   # 2 years in the future
            
            return min_date <= parsed_date <= max_date
        except:
            return False
    
    def _validate_crew_balance(self, crews: Dict[str, int], total_employees: int):
        """Check if crew distribution is reasonable"""
        if total_employees == 0:
            return
        
        for crew, count in crews.items():
            percentage = (count / total_employees) * 100
            
            if percentage < 10:
                self.warnings.append(
                    f"Crew {crew} appears understaffed ({count} employees, {percentage:.1f}%)"
                )
            elif percentage > 40:
                self.warnings.append(
                    f"Crew {crew} appears overstaffed ({count} employees, {percentage:.1f}%)"
                )
    
    def _validate_position_distribution(self, positions: Dict[str, int], total_employees: int):
        """Check position distribution for potential issues"""
        if total_employees == 0:
            return
        
        # Check for too many supervisors
        supervisor_count = 0
        for position, count in positions.items():
            if 'supervisor' in position.lower() or 'manager' in position.lower():
                supervisor_count += count
        
        supervisor_percentage = (supervisor_count / total_employees) * 100
        if supervisor_percentage > 20:
            self.warnings.append(
                f"High number of supervisors/managers ({supervisor_count}, {supervisor_percentage:.1f}%). "
                "Please verify this is correct."
            )
    
    def _employee_validation_result(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Format employee validation result"""
        return {
            'success': len(self.errors) == 0,
            'error': f"Found {len(self.errors)} validation errors" if self.errors else None,
            'errors': self.errors,
            'warnings': self.warnings,
            'employee_count': self.stats.get('valid_employees', 0),
            'total_rows': len(df),
            'stats': self.stats
        }
    
    def _overtime_validation_result(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Format overtime validation result"""
        return {
            'success': len(self.errors) == 0,
            'error': f"Found {len(self.errors)} validation errors" if self.errors else None,
            'errors': self.errors,
            'warnings': self.warnings,
            'employee_count': self.stats.get('unique_employees', 0),
            'total_rows': len(df),
            'avg_ot': self.stats.get('avg_ot_per_employee', 0),
            'stats': self.stats
        }


class ExcelUploadProcessor:
    """Process validated Excel uploads and handle database operations"""
    
    def __init__(self, db, models):
        """
        Initialize processor with database and model references
        
        Args:
            db: SQLAlchemy database instance
            models: Dict containing model classes (Employee, OvertimeHistory, etc.)
        """
        self.db = db
        self.Employee = models['Employee']
        self.OvertimeHistory = models.get('OvertimeHistory')
        self.FileUpload = models.get('FileUpload')
        self.Position = models.get('Position')
        self.logger = logger
    
    def process_employee_upload(self, validated_data: List[Dict], file_info: Dict, 
                              replace_all: bool = True, current_user_id: str = None) -> Dict[str, Any]:
        """
        Process validated employee data and update database
        
        Args:
            validated_data: List of validated employee records
            file_info: Information about the uploaded file
            replace_all: Whether to replace all existing data or append/update
            current_user_id: ID of the user performing the upload
            
        Returns:
            Dict with processing results
        """
        try:
            self.logger.info(f"Processing employee upload: {len(validated_data)} records")
            
            records_processed = 0
            records_updated = 0
            records_created = 0
            errors = []
            
            # Create file upload record for tracking
            file_upload = None
            if self.FileUpload:
                file_upload = self.FileUpload(
                    filename=file_info.get('filename'),
                    upload_type='employee',
                    uploaded_by=current_user_id,
                    status='processing',
                    records_processed=0,
                    file_size=file_info.get('file_size'),
                    file_hash=file_info.get('file_hash')
                )
                self.db.session.add(file_upload)
                self.db.session.flush()
            
            # Begin transaction
            try:
                # If replace_all, deactivate existing employees
                if replace_all:
                    self.logger.info("Deactivating existing employees (replace mode)")
                    updated_count = self.Employee.query.update({'is_active': False})
                    self.logger.info(f"Deactivated {updated_count} existing employees")
                    self.db.session.flush()
                
                # Process each employee record
                for record in validated_data:
                    try:
                        employee = self._process_single_employee(record, replace_all)
                        
                        if employee:
                            if hasattr(employee, '_was_created') and employee._was_created:
                                records_created += 1
                            else:
                                records_updated += 1
                            records_processed += 1
                        
                    except Exception as e:
                        error_msg = f"Error processing employee {record.get('Employee ID', 'Unknown')}: {str(e)}"
                        self.logger.error(error_msg)
                        errors.append(error_msg)
                
                # Update file upload record
                if file_upload:
                    file_upload.records_processed = records_processed
                    file_upload.status = 'completed' if not errors else 'partial'
                    file_upload.error_log = json.dumps(errors) if errors else None
                    file_upload.completed_at = datetime.utcnow()
                
                # Commit transaction
                self.db.session.commit()
                
                self.logger.info(f"Employee upload completed: {records_processed} processed, {records_created} created, {records_updated} updated")
                
                return {
                    'success': True,
                    'records_processed': records_processed,
                    'records_created': records_created,
                    'records_updated': records_updated,
                    'errors': errors,
                    'upload_id': file_upload.id if file_upload else None
                }
                
            except Exception as e:
                self.db.session.rollback()
                self.logger.error(f"Transaction failed during employee upload: {e}")
                
                if file_upload:
                    file_upload.status = 'failed'
                    file_upload.error_log = json.dumps([str(e)])
                    self.db.session.commit()
                
                return {
                    'success': False,
                    'error': str(e),
                    'records_processed': records_processed,
                    'records_created': records_created,
                    'records_updated': records_updated,
                    'errors': errors + [str(e)]
                }
                
        except Exception as e:
            self.logger.error(f"Critical error in process_employee_upload: {e}")
            return {
                'success': False,
                'error': f"Critical processing error: {str(e)}",
                'records_processed': 0
            }
    
    def _process_single_employee(self, record: Dict, replace_all: bool = True):
        """Process a single employee record"""
        emp_id = record.get('Employee ID', '').strip()
        
        # Check if employee exists
        employee = self.Employee.query.filter_by(employee_id=emp_id).first()
        
        if employee:
            # Update existing employee
            employee.name = f"{record.get('First Name', '')} {record.get('Last Name', '')}"
            employee.first_name = record.get('First Name', '').strip()
            employee.last_name = record.get('Last Name', '').strip()
            employee.crew = record.get('Crew Assigned', '').strip().upper()
            employee.is_active = True
            
            if record.get('Email'):
                employee.email = record.get('Email').strip()
            
            if record.get('Phone'):
                employee.phone = record.get('Phone').strip()
            
            # Handle position
            position_name = record.get('Current Job Position', '').strip()
            if position_name and self.Position:
                position = self._get_or_create_position(position_name)
                employee.position_id = position.id
            
            # Handle hire date
            if record.get('Hire Date'):
                try:
                    employee.hire_date = pd.to_datetime(record['Hire Date']).date()
                except:
                    pass  # Skip invalid dates
            
            employee._was_created = False
            return employee
            
        else:
            # Create new employee
            employee = self.Employee(
                employee_id=emp_id,
                name=f"{record.get('First Name', '')} {record.get('Last Name', '')}",
                first_name=record.get('First Name', '').strip(),
                last_name=record.get('Last Name', '').strip(),
                crew=record.get('Crew Assigned', '').strip().upper(),
                is_active=True,
                password_hash='$2b$12$default.hash.to.be.changed',  # Default password hash
                must_change_password=True
            )
            
            if record.get('Email'):
                employee.email = record.get('Email').strip()
            
            if record.get('Phone'):
                employee.phone = record.get('Phone').strip()
            
            # Handle position
            position_name = record.get('Current Job Position', '').strip()
            if position_name and self.Position:
                position = self._get_or_create_position(position_name)
                employee.position_id = position.id
            
            # Handle hire date
            if record.get('Hire Date'):
                try:
                    employee.hire_date = pd.to_datetime(record['Hire Date']).date()
                except:
                    pass  # Skip invalid dates
            
            self.db.session.add(employee)
            employee._was_created = True
            return employee
    
    def _get_or_create_position(self, position_name: str):
        """Get existing position or create new one"""
        position = self.Position.query.filter_by(name=position_name).first()
        if not position:
            position = self.Position(name=position_name)
            self.db.session.add(position)
            self.db.session.flush()
        return position
    
    def process_overtime_upload(self, validated_data: List[Dict], file_info: Dict, 
                              replace_existing: bool = False, current_user_id: str = None) -> Dict[str, Any]:
        """
        Process validated overtime data
        
        Args:
            validated_data: List of validated overtime records
            file_info: Information about the uploaded file
            replace_existing: Whether to replace existing overtime data
            current_user_id: ID of the user performing the upload
            
        Returns:
            Dict with processing results
        """
        if not self.OvertimeHistory:
            return {
                'success': False,
                'error': 'Overtime history model not available',
                'records_processed': 0
            }
        
        try:
            self.logger.info(f"Processing overtime upload: {len(validated_data)} records")
            
            records_processed = 0
            records_updated = 0
            records_created = 0
            errors = []
            
            # Create file upload record
            file_upload = None
            if self.FileUpload:
                file_upload = self.FileUpload(
                    filename=file_info.get('filename'),
                    upload_type='overtime',
                    uploaded_by=current_user_id,
                    status='processing',
                    records_processed=0,
                    file_size=file_info.get('file_size'),
                    file_hash=file_info.get('file_hash')
                )
                self.db.session.add(file_upload)
                self.db.session.flush()
            
            try:
                # Process each overtime record
                for record in validated_data:
                    try:
                        processed = self._process_single_overtime_record(record, replace_existing)
                        
                        if processed:
                            if processed.get('created'):
                                records_created += 1
                            else:
                                records_updated += 1
                            records_processed += 1
                        
                    except Exception as e:
                        error_msg = f"Error processing overtime for employee {record.get('Employee ID', 'Unknown')}: {str(e)}"
                        self.logger.error(error_msg)
                        errors.append(error_msg)
                
                # Update file upload record
                if file_upload:
                    file_upload.records_processed = records_processed
                    file_upload.status = 'completed' if not errors else 'partial'
                    file_upload.error_log = json.dumps(errors) if errors else None
                    file_upload.completed_at = datetime.utcnow()
                
                # Commit transaction
                self.db.session.commit()
                
                self.logger.info(f"Overtime upload completed: {records_processed} processed")
                
                return {
                    'success': True,
                    'records_processed': records_processed,
                    'records_created': records_created,
                    'records_updated': records_updated,
                    'errors': errors,
                    'upload_id': file_upload.id if file_upload else None
                }
                
            except Exception as e:
                self.db.session.rollback()
                self.logger.error(f"Transaction failed during overtime upload: {e}")
                
                if file_upload:
                    file_upload.status = 'failed'
                    file_upload.error_log = json.dumps([str(e)])
                    self.db.session.commit()
                
                return {
                    'success': False,
                    'error': str(e),
                    'records_processed': records_processed,
                    'errors': errors + [str(e)]
                }
                
        except Exception as e:
            self.logger.error(f"Critical error in process_overtime_upload: {e}")
            return {
                'success': False,
                'error': f"Critical processing error: {str(e)}",
                'records_processed': 0
            }
    
    def _process_single_overtime_record(self, record: Dict, replace_existing: bool = False) -> Dict[str, Any]:
        """Process a single overtime record"""
        emp_id = record.get('Employee ID', '').strip()
        week_start = pd.to_datetime(record.get('Week Start Date')).date()
        
        # Find employee
        employee = self.Employee.query.filter_by(employee_id=emp_id).first()
        if not employee:
            raise ValueError(f"Employee {emp_id} not found in system")
        
        # Check if record already exists
        existing_record = self.OvertimeHistory.query.filter_by(
            employee_id=employee.id,
            week_start_date=week_start
        ).first()
        
        if existing_record:
            if replace_existing:
                # Update existing record
                existing_record.regular_hours = float(record.get('Regular Hours', 0))
                existing_record.overtime_hours = float(record.get('Overtime Hours', 0))
                existing_record.total_hours = float(record.get('Total Hours', 0))
                if record.get('Notes'):
                    existing_record.notes = record.get('Notes')
                return {'created': False}
            else:
                # Skip existing record
                return None
        else:
            # Create new record
            ot_record = self.OvertimeHistory(
                employee_id=employee.id,
                week_start_date=week_start,
                regular_hours=float(record.get('Regular Hours', 0)),
                overtime_hours=float(record.get('Overtime Hours', 0)),
                total_hours=float(record.get('Total Hours', 0))
            )
            
            if record.get('Notes'):
                ot_record.notes = record.get('Notes')
            
            self.db.session.add(ot_record)
            return {'created': True}


# Convenience function for easy import
def process_excel_upload(file_path: str, upload_type: str, db, models, 
                        current_user_id: str = None, **options) -> Dict[str, Any]:
    """
    Main entry point for Excel upload processing
    
    Args:
        file_path: Path to uploaded Excel file
        upload_type: Type of upload ('employee', 'overtime', etc.)
        db: Database instance
        models: Dict of model classes
        current_user_id: ID of user performing upload
        **options: Additional processing options
        
    Returns:
        Dict with processing results
    """
    try:
        # Step 1: Validate file
        validator = ExcelFileValidator()
        file_validation = validator.validate_file(file_path, os.path.basename(file_path))
        
        if not file_validation['valid']:
            return {
                'success': False,
                'error': 'File validation failed',
                'errors': file_validation['errors'],
                'stage': 'file_validation'
            }
        
        # Step 2: Read and validate data
        df = pd.read_excel(file_path)
        data_validator = ExcelDataValidator()
        
        if upload_type == 'employee':
            validation_result = data_validator.validate_employee_data(df)
        elif upload_type == 'overtime':
            validation_result = data_validator.validate_overtime_data(df)
        else:
            return {
                'success': False,
                'error': f'Unsupported upload type: {upload_type}',
                'stage': 'data_validation'
            }
        
        if not validation_result['success']:
            return {
                'success': False,
                'error': 'Data validation failed',
                'errors': validation_result['errors'],
                'warnings': validation_result.get('warnings', []),
                'stage': 'data_validation'
            }
        
        # Step 3: Process data
        processor = ExcelUploadProcessor(db, models)
        
        # Convert DataFrame to list of dicts
        validated_data = df.to_dict('records')
        
        file_info = {
            'filename': os.path.basename(file_path),
            'file_size': file_validation['file_size'],
            'file_hash': file_validation['file_hash']
        }
        
        if upload_type == 'employee':
            result = processor.process_employee_upload(
                validated_data, 
                file_info, 
                replace_all=options.get('replace_all', True),
                current_user_id=current_user_id
            )
        elif upload_type == 'overtime':
            result = processor.process_overtime_upload(
                validated_data,
                file_info,
                replace_existing=options.get('replace_existing', False),
                current_user_id=current_user_id
            )
        
        # Add validation warnings to result
        if validation_result.get('warnings'):
            result['warnings'] = validation_result['warnings']
        
        return result
        
    except Exception as e:
        logger.error(f"Critical error in process_excel_upload: {e}")
        return {
            'success': False,
            'error': f'Critical processing error: {str(e)}',
            'stage': 'processing'
        }


# Template generation functions for completeness
def generate_employee_template():
    """Generate employee import template"""
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'First Name': ['John', 'Jane', 'Bob'],
        'Last Name': ['Smith', 'Johnson', 'Wilson'],
        'Crew Assigned': ['A', 'B', 'C'],
        'Current Job Position': ['Operator', 'Maintenance Tech', 'Supervisor'],
        'Email': ['john.smith@company.com', 'jane.johnson@company.com', 'bob.wilson@company.com'],
        'Phone': ['555-0001', '555-0002', '555-0003'],
        'Hire Date': ['2023-01-15', '2023-02-20', '2023-03-10']
    }
    
    return pd.DataFrame(template_data)


def generate_overtime_template():
    """Generate overtime import template"""
    template_data = {
        'Employee ID': ['EMP001', 'EMP001', 'EMP002', 'EMP002'],
        'Week Start Date': ['2024-01-08', '2024-01-15', '2024-01-08', '2024-01-15'],
        'Regular Hours': [40.0, 40.0, 35.0, 40.0],
        'Overtime Hours': [8.0, 12.0, 5.0, 0.0],
        'Total Hours': [48.0, 52.0, 40.0, 40.0],
        'Notes': ['Standard week', 'Extra coverage needed', 'Partial week', 'Regular week']
    }
    
    return pd.DataFrame(template_data)
