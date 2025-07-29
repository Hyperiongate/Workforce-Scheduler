import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from flask import current_app, flash
from werkzeug.utils import secure_filename
import os
import re
from typing import Dict, List, Tuple, Any

class ExcelUploadValidator:
    """Comprehensive validation for Excel uploads"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.processed_count = 0
        self.failed_count = 0
        
    def validate_employee_data(self, df: pd.DataFrame) -> Tuple[bool, List[Dict]]:
        """Validate employee import data"""
        self.errors = []
        self.warnings = []
        
        # Required columns
        required_cols = ['Employee ID', 'First Name', 'Last Name', 'Email', 'Crew', 'Position']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            self.errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            return False, []
        
        # Clean data
        df = df.fillna('')
        validated_data = []
        
        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel row number (header is row 1)
            row_errors = []
            
            # Validate Employee ID
            emp_id = str(row.get('Employee ID', '')).strip()
            if not emp_id:
                row_errors.append(f"Row {row_num}: Employee ID is required")
            elif len(emp_id) > 20:
                row_errors.append(f"Row {row_num}: Employee ID too long (max 20 chars)")
                
            # Validate Names
            first_name = str(row.get('First Name', '')).strip()
            last_name = str(row.get('Last Name', '')).strip()
            if not first_name:
                row_errors.append(f"Row {row_num}: First Name is required")
            if not last_name:
                row_errors.append(f"Row {row_num}: Last Name is required")
                
            # Validate Email
            email = str(row.get('Email', '')).strip().lower()
            if not email:
                row_errors.append(f"Row {row_num}: Email is required")
            elif not self._is_valid_email(email):
                row_errors.append(f"Row {row_num}: Invalid email format: {email}")
                
            # Validate Crew
            crew = str(row.get('Crew', '')).strip().upper()
            if not crew:
                row_errors.append(f"Row {row_num}: Crew is required")
            elif crew not in ['A', 'B', 'C', 'D']:
                row_errors.append(f"Row {row_num}: Invalid crew '{crew}' (must be A, B, C, or D)")
                
            # Validate Position
            position = str(row.get('Position', '')).strip()
            if not position:
                row_errors.append(f"Row {row_num}: Position is required")
                
            # Validate optional fields
            hire_date = None
            if 'Hire Date' in row and row['Hire Date']:
                try:
                    hire_date = pd.to_datetime(row['Hire Date']).date()
                    if hire_date > datetime.now().date():
                        self.warnings.append(f"Row {row_num}: Hire date is in the future")
                except:
                    row_errors.append(f"Row {row_num}: Invalid hire date format (use YYYY-MM-DD)")
                    
            # Parse skills
            skills = []
            if 'Skills' in row and row['Skills']:
                skills = [s.strip() for s in str(row['Skills']).split(',') if s.strip()]
                
            if row_errors:
                self.errors.extend(row_errors)
                self.failed_count += 1
            else:
                validated_data.append({
                    'employee_id': emp_id,
                    'first_name': first_name,
                    'last_name': last_name,
                    'name': f"{first_name} {last_name}",
                    'email': email,
                    'crew': crew,
                    'position': position,
                    'department': str(row.get('Department', '')).strip(),
                    'hire_date': hire_date,
                    'phone': str(row.get('Phone', '')).strip(),
                    'emergency_contact': str(row.get('Emergency Contact', '')).strip(),
                    'emergency_phone': str(row.get('Emergency Phone', '')).strip(),
                    'skills': skills
                })
                self.processed_count += 1
                
        # Check for duplicates
        self._check_duplicates(validated_data)
        
        # Check crew balance
        self._check_crew_balance(validated_data)
        
        return len(self.errors) == 0, validated_data
    
    def validate_overtime_data(self, df: pd.DataFrame) -> Tuple[bool, List[Dict]]:
        """Validate overtime history import data"""
        self.errors = []
        self.warnings = []
        
        # Required columns
        required_cols = ['Employee ID', 'Week Start Date', 'Regular Hours', 'Overtime Hours']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            self.errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            return False, []
            
        # Clean data
        df = df.fillna(0)
        validated_data = []
        employee_weeks = {}  # Track weeks per employee
        
        for idx, row in df.iterrows():
            row_num = idx + 2
            row_errors = []
            
            # Validate Employee ID
            emp_id = str(row.get('Employee ID', '')).strip()
            if not emp_id:
                row_errors.append(f"Row {row_num}: Employee ID is required")
                
            # Validate Week Start Date
            try:
                week_start = pd.to_datetime(row['Week Start Date']).date()
                # Check if it's a Monday
                if week_start.weekday() != 0:
                    row_errors.append(f"Row {row_num}: Week start date must be a Monday")
                    
                # Track weeks per employee
                if emp_id not in employee_weeks:
                    employee_weeks[emp_id] = set()
                if week_start in employee_weeks[emp_id]:
                    row_errors.append(f"Row {row_num}: Duplicate week for employee {emp_id}")
                employee_weeks[emp_id].add(week_start)
                
            except:
                row_errors.append(f"Row {row_num}: Invalid date format (use YYYY-MM-DD)")
                week_start = None
                
            # Validate hours
            try:
                regular_hours = float(row.get('Regular Hours', 0))
                overtime_hours = float(row.get('Overtime Hours', 0))
                total_hours = float(row.get('Total Hours', regular_hours + overtime_hours))
                
                if regular_hours < 0:
                    row_errors.append(f"Row {row_num}: Regular hours cannot be negative")
                if overtime_hours < 0:
                    row_errors.append(f"Row {row_num}: Overtime hours cannot be negative")
                if abs(total_hours - (regular_hours + overtime_hours)) > 0.01:
                    row_errors.append(f"Row {row_num}: Total hours doesn't match regular + overtime")
                    
                # Warnings for unusual values
                if regular_hours > 60:
                    self.warnings.append(f"Row {row_num}: Unusually high regular hours ({regular_hours})")
                if overtime_hours > 40:
                    self.warnings.append(f"Row {row_num}: Very high overtime hours ({overtime_hours})")
                    
            except ValueError:
                row_errors.append(f"Row {row_num}: Invalid number format for hours")
                
            if row_errors:
                self.errors.extend(row_errors)
                self.failed_count += 1
            else:
                validated_data.append({
                    'employee_id': emp_id,
                    'week_start_date': week_start,
                    'regular_hours': regular_hours,
                    'overtime_hours': overtime_hours,
                    'total_hours': total_hours,
                    'notes': str(row.get('Notes', '')).strip()
                })
                self.processed_count += 1
                
        # Validate 13-week requirement
        for emp_id, weeks in employee_weeks.items():
            if len(weeks) != 13:
                self.errors.append(f"Employee {emp_id} has {len(weeks)} weeks of data (should be 13)")
                
        return len(self.errors) == 0, validated_data
    
    def validate_bulk_update(self, df: pd.DataFrame, update_type: str) -> Tuple[bool, List[Dict]]:
        """Validate bulk update data"""
        self.errors = []
        self.warnings = []
        
        if 'Employee ID' not in df.columns or 'Action' not in df.columns:
            self.errors.append("Missing required columns: Employee ID and Action")
            return False, []
            
        validated_data = []
        valid_actions = ['UPDATE', 'DELETE', 'NEW', 'ADD']
        
        for idx, row in df.iterrows():
            row_num = idx + 2
            action = str(row.get('Action', '')).strip().upper()
            
            if action not in valid_actions:
                self.errors.append(f"Row {row_num}: Invalid action '{action}'")
                continue
                
            emp_id = str(row.get('Employee ID', '')).strip()
            if not emp_id and action != 'NEW':
                self.errors.append(f"Row {row_num}: Employee ID required for {action}")
                continue
                
            validated_row = {
                'action': action,
                'employee_id': emp_id,
                'row_data': row.to_dict()
            }
            
            # Validate based on update type and action
            if update_type == 'employee' and action in ['UPDATE', 'NEW']:
                # Validate employee fields
                if action == 'NEW':
                    # For new employees, validate required fields
                    required = ['First Name', 'Last Name', 'Email', 'Crew', 'Position']
                    missing = [f for f in required if not row.get(f)]
                    if missing:
                        self.errors.append(f"Row {row_num}: Missing required fields for NEW: {missing}")
                        continue
                        
            elif update_type == 'overtime' and action in ['UPDATE', 'ADD']:
                # Validate overtime fields
                if 'Week Start Date' not in row or not row['Week Start Date']:
                    self.errors.append(f"Row {row_num}: Week Start Date required for {action}")
                    continue
                    
            validated_data.append(validated_row)
            self.processed_count += 1
            
        return len(self.errors) == 0, validated_data
    
    def _is_valid_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _check_duplicates(self, data: List[Dict]):
        """Check for duplicate employee IDs and emails"""
        emp_ids = [d['employee_id'] for d in data]
        emails = [d['email'] for d in data]
        
        # Check for duplicate IDs
        id_counts = pd.Series(emp_ids).value_counts()
        duplicates = id_counts[id_counts > 1].index.tolist()
        if duplicates:
            self.errors.append(f"Duplicate Employee IDs found: {', '.join(duplicates)}")
            
        # Check for duplicate emails
        email_counts = pd.Series(emails).value_counts()
        dup_emails = email_counts[email_counts > 1].index.tolist()
        if dup_emails:
            self.errors.append(f"Duplicate emails found: {', '.join(dup_emails)}")
    
    def _check_crew_balance(self, data: List[Dict]):
        """Check if crews are reasonably balanced"""
        crew_counts = pd.Series([d['crew'] for d in data]).value_counts()
        total = len(data)
        
        for crew in ['A', 'B', 'C', 'D']:
            count = crew_counts.get(crew, 0)
            percentage = (count / total * 100) if total > 0 else 0
            
            if percentage < 15:
                self.warnings.append(f"Crew {crew} is understaffed ({count} employees, {percentage:.1f}%)")
            elif percentage > 35:
                self.warnings.append(f"Crew {crew} may be overstaffed ({count} employees, {percentage:.1f}%)")


class ExcelUploadProcessor:
    """Process validated Excel uploads"""
    
    def __init__(self, db, models):
        self.db = db
        self.Employee = models['Employee']
        self.OvertimeHistory = models['OvertimeHistory']
        self.FileUpload = models['FileUpload']
        self.Position = models['Position']
        self.Skill = models['Skill']
        self.EmployeeSkill = models['EmployeeSkill']
        
    def process_employee_upload(self, validated_data: List[Dict], file_info: Dict, 
                              replace_all: bool = True) -> Dict[str, Any]:
        """Process employee data upload"""
        try:
            # Record the upload
            file_upload = self.FileUpload(
                filename=file_info['filename'],
                file_type='employee_import',
                file_size=file_info.get('size', 0),
                uploaded_by_id=file_info['uploaded_by_id'],
                status='processing'
            )
            self.db.session.add(file_upload)
            self.db.session.flush()
            
            created_count = 0
            updated_count = 0
            errors = []
            
            # Get or create positions
            position_map = self._get_or_create_positions(validated_data)
            
            # Get or create skills
            skill_map = self._get_or_create_skills(validated_data)
            
            if replace_all:
                # Delete existing employees (except system/admin accounts)
                deleted = self.Employee.query.filter(
                    self.Employee.email != 'admin@workforce.com'
                ).delete()
                current_app.logger.info(f"Deleted {deleted} existing employees")
                
            # Process each employee
            for emp_data in validated_data:
                try:
                    # Check if employee exists
                    existing = self.Employee.query.filter_by(
                        employee_id=emp_data['employee_id']
                    ).first()
                    
                    if existing and not replace_all:
                        # Update existing
                        for key, value in emp_data.items():
                            if key not in ['skills', 'position'] and value:
                                setattr(existing, key, value)
                        
                        # Update position
                        if emp_data['position'] in position_map:
                            existing.position_id = position_map[emp_data['position']].id
                            
                        updated_count += 1
                        employee = existing
                    else:
                        # Create new
                        employee = self.Employee(
                            employee_id=emp_data['employee_id'],
                            name=emp_data['name'],
                            email=emp_data['email'],
                            crew=emp_data['crew'],
                            position_id=position_map[emp_data['position']].id if emp_data['position'] in position_map else None,
                            hire_date=emp_data.get('hire_date'),
                            phone=emp_data.get('phone'),
                            emergency_contact=emp_data.get('emergency_contact'),
                            emergency_phone=emp_data.get('emergency_phone'),
                            is_supervisor=False
                        )
                        
                        # Set default password
                        employee.set_password('password123')
                        
                        self.db.session.add(employee)
                        created_count += 1
                        
                    # Process skills
                    if emp_data.get('skills'):
                        self._update_employee_skills(employee, emp_data['skills'], skill_map)
                        
                except Exception as e:
                    errors.append(f"Error processing {emp_data['employee_id']}: {str(e)}")
                    
            # Commit changes
            self.db.session.commit()
            
            # Update file upload record
            file_upload.status = 'completed' if not errors else 'completed_with_errors'
            file_upload.records_processed = created_count + updated_count
            file_upload.records_failed = len(errors)
            file_upload.error_details = '\n'.join(errors) if errors else None
            self.db.session.commit()
            
            return {
                'success': True,
                'created': created_count,
                'updated': updated_count,
                'errors': errors,
                'file_upload_id': file_upload.id
            }
            
        except Exception as e:
            self.db.session.rollback()
            current_app.logger.error(f"Employee upload failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def process_overtime_upload(self, validated_data: List[Dict], file_info: Dict,
                              replace_all: bool = True) -> Dict[str, Any]:
        """Process overtime history upload"""
        try:
            # Record the upload
            file_upload = self.FileUpload(
                filename=file_info['filename'],
                file_type='overtime_import',
                file_size=file_info.get('size', 0),
                uploaded_by_id=file_info['uploaded_by_id'],
                status='processing'
            )
            self.db.session.add(file_upload)
            self.db.session.flush()
            
            created_count = 0
            updated_count = 0
            errors = []
            
            # Get employee ID mapping
            employees = {e.employee_id: e for e in self.Employee.query.all()}
            
            if replace_all:
                # Delete all existing overtime history
                deleted = self.OvertimeHistory.query.delete()
                current_app.logger.info(f"Deleted {deleted} existing overtime records")
                
            # Process each record
            for ot_data in validated_data:
                try:
                    emp_id = ot_data['employee_id']
                    if emp_id not in employees:
                        errors.append(f"Employee ID {emp_id} not found in system")
                        continue
                        
                    employee = employees[emp_id]
                    
                    # Check if record exists
                    existing = self.OvertimeHistory.query.filter_by(
                        employee_id=employee.id,
                        week_start_date=ot_data['week_start_date']
                    ).first()
                    
                    if existing and not replace_all:
                        # Update existing
                        existing.regular_hours = ot_data['regular_hours']
                        existing.overtime_hours = ot_data['overtime_hours']
                        existing.total_hours = ot_data['total_hours']
                        updated_count += 1
                    else:
                        # Create new
                        overtime = self.OvertimeHistory(
                            employee_id=employee.id,
                            week_start_date=ot_data['week_start_date'],
                            regular_hours=ot_data['regular_hours'],
                            overtime_hours=ot_data['overtime_hours'],
                            total_hours=ot_data['total_hours']
                        )
                        self.db.session.add(overtime)
                        created_count += 1
                        
                except Exception as e:
                    errors.append(f"Error processing {ot_data['employee_id']} week {ot_data['week_start_date']}: {str(e)}")
                    
            # Commit changes
            self.db.session.commit()
            
            # Update file upload record
            file_upload.status = 'completed' if not errors else 'completed_with_errors'
            file_upload.records_processed = created_count + updated_count
            file_upload.records_failed = len(errors)
            file_upload.error_details = '\n'.join(errors) if errors else None
            self.db.session.commit()
            
            return {
                'success': True,
                'created': created_count,
                'updated': updated_count,
                'errors': errors,
                'file_upload_id': file_upload.id
            }
            
        except Exception as e:
            self.db.session.rollback()
            current_app.logger.error(f"Overtime upload failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_or_create_positions(self, employee_data: List[Dict]) -> Dict[str, Any]:
        """Get or create positions from employee data"""
        position_names = set(d['position'] for d in employee_data if d['position'])
        position_map = {}
        
        for pos_name in position_names:
            position = self.Position.query.filter_by(name=pos_name).first()
            if not position:
                position = self.Position(name=pos_name)
                self.db.session.add(position)
                
            position_map[pos_name] = position
            
        self.db.session.flush()
        return position_map
    
    def _get_or_create_skills(self, employee_data: List[Dict]) -> Dict[str, Any]:
        """Get or create skills from employee data"""
        all_skills = set()
        for d in employee_data:
            if d.get('skills'):
                all_skills.update(d['skills'])
                
        skill_map = {}
        for skill_name in all_skills:
            skill = self.Skill.query.filter_by(name=skill_name).first()
            if not skill:
                skill = self.Skill(name=skill_name)
                self.db.session.add(skill)
                
            skill_map[skill_name] = skill
            
        self.db.session.flush()
        return skill_map
    
    def _update_employee_skills(self, employee, skills: List[str], skill_map: Dict[str, Any]):
        """Update employee's skills"""
        # Remove existing skills
        self.EmployeeSkill.query.filter_by(employee_id=employee.id).delete()
        
        # Add new skills
        for skill_name in skills:
            if skill_name in skill_map:
                emp_skill = self.EmployeeSkill(
                    employee_id=employee.id,
                    skill_id=skill_map[skill_name].id,
                    certified_date=datetime.now().date()
                )
                self.db.session.add(emp_skill)
