from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from models import db, Schedule, Employee, Position, TimeOffRequest, ShiftSwapRequest, ScheduleSuggestion, VacationCalendar, Skill, employee_skills, OvertimeHistory
from datetime import datetime, date, timedelta
from sqlalchemy import func, case, text
from functools import wraps
from werkzeug.security import generate_password_hash
import calendar
import io
import csv
import pandas as pd

supervisor_bp = Blueprint('supervisor', __name__)

# Decorator to require supervisor privileges
def supervisor_required(f):
    """Decorator to require supervisor privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_supervisor:
            flash('You must be a supervisor to access this page.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@supervisor_bp.route('/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display the vacation calendar view"""
    return render_template('vacation_calendar.html')

@supervisor_bp.route('/api/vacation-calendar')
@login_required
@supervisor_required
def api_vacation_calendar():
    """API endpoint to get vacation calendar data"""
    year = int(request.args.get('year', date.today().year))
    month = int(request.args.get('month', date.today().month))
    crew = request.args.get('crew', 'ALL')
    
    # Calculate date range for the month
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Query time off requests and vacation calendar entries
    query = db.session.query(
        VacationCalendar.employee_id,
        VacationCalendar.date,
        VacationCalendar.type,
        Employee.name.label('employee_name'),
        Employee.crew,
        TimeOffRequest.reason
    ).join(
        Employee, VacationCalendar.employee_id == Employee.id
    ).outerjoin(
        TimeOffRequest, VacationCalendar.request_id == TimeOffRequest.id
    ).filter(
        VacationCalendar.date >= start_date,
        VacationCalendar.date <= end_date
    )
    
    if crew != 'ALL':
        query = query.filter(Employee.crew == crew)
    
    # Group consecutive dates for the same employee and type
    calendar_entries = query.order_by(
        VacationCalendar.employee_id,
        VacationCalendar.date
    ).all()
    
    # Process results to group consecutive dates
    grouped_data = []
    current_group = None
    
    for entry in calendar_entries:
        if (current_group is None or 
            current_group['employee_id'] != entry.employee_id or
            current_group['type'] != entry.type or
            (entry.date - datetime.strptime(current_group['end_date'], '%Y-%m-%d').date()).days > 1):
            
            # Start new group
            if current_group:
                grouped_data.append(current_group)
            
            current_group = {
                'employee_id': entry.employee_id,
                'employee_name': entry.employee_name,
                'crew': entry.crew,
                'type': entry.type,
                'start_date': entry.date.strftime('%Y-%m-%d'),
                'end_date': entry.date.strftime('%Y-%m-%d'),
                'reason': entry.reason
            }
        else:
            # Extend current group
            current_group['end_date'] = entry.date.strftime('%Y-%m-%d')
    
    if current_group:
        grouped_data.append(current_group)
    
    return jsonify(grouped_data)

@supervisor_bp.route('/api/vacation-calendar/export')
@login_required
@supervisor_required
def export_vacation_calendar():
    """Export vacation calendar as CSV"""
    year = int(request.args.get('year', date.today().year))
    month = int(request.args.get('month', date.today().month))
    crew = request.args.get('crew', 'ALL')
    
    # Get calendar data
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    query = db.session.query(
        Employee.name,
        Employee.crew,
        VacationCalendar.date,
        VacationCalendar.type,
        TimeOffRequest.reason
    ).join(
        Employee, VacationCalendar.employee_id == Employee.id
    ).outerjoin(
        TimeOffRequest, VacationCalendar.request_id == TimeOffRequest.id
    ).filter(
        VacationCalendar.date >= start_date,
        VacationCalendar.date <= end_date
    ).order_by(
        Employee.name,
        VacationCalendar.date
    )
    
    if crew != 'ALL':
        query = query.filter(Employee.crew == crew)
    
    entries = query.all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Employee Name', 'Crew', 'Date', 'Type', 'Reason'])
    
    # Write data
    for entry in entries:
        writer.writerow([
            entry.name,
            entry.crew,
            entry.date.strftime('%Y-%m-%d'),
            entry.type.title(),
            entry.reason or 'N/A'
        ])
    
    # Create response
    output.seek(0)
    month_name = calendar.month_name[month]
    filename = f'vacation_calendar_{month_name}_{year}'
    if crew != 'ALL':
        filename += f'_crew_{crew}'
    filename += '.csv'
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    # Get filter parameters
    status_filter = request.args.get('status', 'pending')
    crew_filter = request.args.get('crew', 'all')
    date_filter = request.args.get('date_range', 'upcoming')
    
    # Base query
    query = TimeOffRequest.query
    
    # Apply status filter
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Apply crew filter - FIXED: Specify the join explicitly
    if crew_filter != 'all':
        query = query.join(Employee, Employee.id == TimeOffRequest.employee_id).filter(Employee.crew == crew_filter)
    else:
        query = query.join(Employee, Employee.id == TimeOffRequest.employee_id)
    
    # Apply date filter
    today = datetime.now().date()
    if date_filter == 'upcoming':
        query = query.filter(TimeOffRequest.start_date >= today)
    elif date_filter == 'past':
        query = query.filter(TimeOffRequest.end_date < today)
    elif date_filter == 'current':
        query = query.filter(
            TimeOffRequest.start_date <= today,
            TimeOffRequest.end_date >= today
        )
    
    # Order by start date (pending first, then by date)
    requests = query.order_by(
        case(
            (TimeOffRequest.status == 'pending', 0),
            (TimeOffRequest.status == 'approved', 1),
            (TimeOffRequest.status == 'denied', 2)
        ),
        TimeOffRequest.start_date
    ).all()
    
    # Get statistics
    stats = {
        'pending_count': TimeOffRequest.query.filter_by(status='pending').count(),
        'approved_this_week': TimeOffRequest.query.filter(
            TimeOffRequest.status == 'approved',
            TimeOffRequest.approved_date >= datetime.now() - timedelta(days=7)
        ).count(),
        'coverage_warnings': 0  # Will be calculated based on coverage needs
    }
    
    # Check for coverage warnings (requests that might cause coverage issues)
    for req in requests:
        if req.status == 'pending':
            # Check if approving this would cause coverage issues - FIXED: Use explicit join
            conflicting = TimeOffRequest.query.join(
                Employee, Employee.id == TimeOffRequest.employee_id
            ).filter(
                TimeOffRequest.status == 'approved',
                Employee.crew == req.employee.crew,
                TimeOffRequest.start_date <= req.end_date,
                TimeOffRequest.end_date >= req.start_date
            ).count()
            
            if conflicting >= 2:  # If 2 or more people are already off
                stats['coverage_warnings'] += 1
                req.has_coverage_warning = True
            else:
                req.has_coverage_warning = False
    
    return render_template('time_off_requests.html',
                         requests=requests,
                         stats=stats,
                         status_filter=status_filter,
                         crew_filter=crew_filter,
                         date_filter=date_filter)

@supervisor_bp.route('/supervisor/time-off-requests/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_time_off_request(request_id, action):
    """Approve or deny a time off request"""
    time_off_request = TimeOffRequest.query.get_or_404(request_id)
    
    if time_off_request.status != 'pending':
        flash('This request has already been processed.', 'warning')
        return redirect(url_for('supervisor.time_off_requests'))
    
    if action == 'approve':
        time_off_request.status = 'approved'
        time_off_request.approved_by = current_user.id
        time_off_request.approved_date = datetime.now()
        
        # CREATE VACATION CALENDAR ENTRIES FOR EACH DAY
        current_date = time_off_request.start_date
        while current_date <= time_off_request.end_date:
            vacation_entry = VacationCalendar(
                employee_id=time_off_request.employee_id,
                date=current_date,
                type=time_off_request.type,
                request_id=time_off_request.id
            )
            db.session.add(vacation_entry)
            current_date += timedelta(days=1)
        
        # Send notification to employee (you can implement this later)
        flash(f'Approved {time_off_request.employee.name}\'s time off request for {time_off_request.start_date.strftime("%b %d")} - {time_off_request.end_date.strftime("%b %d")}', 'success')
        
    elif action == 'deny':
        time_off_request.status = 'denied'
        time_off_request.approved_by = current_user.id
        time_off_request.approved_date = datetime.now()
        
        # Get denial reason if provided
        denial_reason = request.form.get('denial_reason', '')
        if denial_reason:
            time_off_request.notes = f"Denial reason: {denial_reason}"
        
        # If previously approved, remove vacation calendar entries
        if time_off_request.status == 'approved':
            VacationCalendar.query.filter_by(request_id=time_off_request.id).delete()
        
        flash(f'Denied {time_off_request.employee.name}\'s time off request', 'info')
    
    db.session.commit()
    return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/swap-requests')
@login_required
@supervisor_required
def swap_requests():
    """Review and approve shift swap requests"""
    # Get filter parameters
    status_filter = request.args.get('status', 'pending')
    crew_filter = request.args.get('crew', 'all')
    
    # Base query
    query = ShiftSwapRequest.query
    
    # Apply status filter
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    # Apply crew filter
    if crew_filter != 'all':
        # Join with requester employee to filter by crew
        query = query.join(Employee, Employee.id == ShiftSwapRequest.requester_id).filter(
            Employee.crew == crew_filter
        )
    
    # Order by creation date (newest first for pending)
    if status_filter == 'pending':
        swap_requests = query.order_by(ShiftSwapRequest.created_at.desc()).all()
    else:
        swap_requests = query.order_by(ShiftSwapRequest.created_at.desc()).all()
    
    # Get statistics
    stats = {
        'pending_count': ShiftSwapRequest.query.filter_by(status='pending').count(),
        'approved_this_week': ShiftSwapRequest.query.filter(
            ShiftSwapRequest.status == 'approved',
            ShiftSwapRequest.created_at >= datetime.now() - timedelta(days=7)
        ).count(),
        'needs_dual_approval': 0
    }
    
    # Check for swaps needing dual approval
    for swap in swap_requests:
        if swap.status == 'pending':
            # Check if this needs approval from both supervisors
            if swap.requester and swap.target_employee:
                if swap.requester.crew != swap.target_employee.crew:
                    stats['needs_dual_approval'] += 1
                    swap.needs_dual_approval = True
                else:
                    swap.needs_dual_approval = False
    
    return render_template('swap_requests.html',
                         requests=swap_requests,
                         stats=stats,
                         status_filter=status_filter,
                         crew_filter=crew_filter)

@supervisor_bp.route('/supervisor/swap-requests/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_swap_request(request_id, action):
    """Approve or deny a swap request"""
    swap_request = ShiftSwapRequest.query.get_or_404(request_id)
    
    if swap_request.status != 'pending':
        flash('This swap request has already been processed.', 'warning')
        return redirect(url_for('supervisor.swap_requests'))
    
    # Determine which supervisor is approving
    is_requester_supervisor = current_user.crew == swap_request.requester.crew
    is_target_supervisor = swap_request.target_employee and current_user.crew == swap_request.target_employee.crew
    
    if action == 'approve':
        # Handle approval based on supervisor's crew
        if is_requester_supervisor:
            swap_request.requester_supervisor_approved = True
            swap_request.requester_supervisor_id = current_user.id
            swap_request.requester_supervisor_date = datetime.now()
        
        if is_target_supervisor:
            swap_request.target_supervisor_approved = True
            swap_request.target_supervisor_id = current_user.id
            swap_request.target_supervisor_date = datetime.now()
        
        # Check if both approvals are complete (or if only one is needed)
        needs_both = swap_request.requester.crew != swap_request.target_employee.crew if swap_request.target_employee else False
        
        if not needs_both or (swap_request.requester_supervisor_approved and swap_request.target_supervisor_approved):
            swap_request.status = 'approved'
            
            # TODO: Actually swap the schedules in the database
            # This would involve swapping the employee_id fields in the Schedule records
            
            flash(f'Approved shift swap between {swap_request.requester.name} and {swap_request.target_employee.name if swap_request.target_employee else "TBD"}', 'success')
        else:
            flash('Swap request partially approved. Waiting for other supervisor approval.', 'info')
            
    elif action == 'deny':
        swap_request.status = 'denied'
        
        # Set the appropriate supervisor fields
        if is_requester_supervisor:
            swap_request.requester_supervisor_approved = False
            swap_request.requester_supervisor_id = current_user.id
            swap_request.requester_supervisor_date = datetime.now()
        
        if is_target_supervisor:
            swap_request.target_supervisor_approved = False
            swap_request.target_supervisor_id = current_user.id
            swap_request.target_supervisor_date = datetime.now()
        
        flash(f'Denied shift swap request from {swap_request.requester.name}', 'info')
    
    db.session.commit()
    return redirect(url_for('supervisor.swap_requests'))

# ========== EMPLOYEE MANAGEMENT ROUTES ==========

@supervisor_bp.route('/employees/download-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download the employee import template with current positions"""
    
    # Get all positions from database
    positions = Position.query.order_by(Position.name).all()
    
    # Create the template structure
    columns = [
        'Last Name',
        'First Name', 
        'Employee ID',
        'Date of Hire',
        'Total Overtime (Last 3 Months)',
        'Crew Assigned',
        'Current Job Position'
    ]
    
    # Add position columns (up to 10)
    position_names = [pos.name for pos in positions[:10]]
    columns.extend(position_names)
    
    # Add padding if less than 10 positions
    while len(columns) < 17:  # 7 base columns + 10 position columns
        columns.append(f'Qualified Position {len(columns) - 6}')
    
    # Create DataFrame with instructions
    instructions = [
        "EMPLOYEE IMPORT TEMPLATE - INSTRUCTIONS",
        "",
        "INSTRUCTIONS:",
        "1. Fill out employee information in the first 7 columns",
        "2. For position qualifications:",
        "   - Write 'current' under their current position",
        "   - Write 'yes' for other qualified positions",
        "   - Leave blank if not qualified",
        "",
        "NOTES:",
        "- Employee emails will be auto-generated as: firstname.lastname@company.com",
        "- Default passwords will be set (users must change on first login)",
        "- This upload will REPLACE all existing employee data"
    ]
    
    # Create the Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Write instructions
        df_instructions = pd.DataFrame(instructions, columns=['Instructions'])
        df_instructions.to_excel(writer, sheet_name='Instructions', index=False)
        
        # Write the template
        df_template = pd.DataFrame(columns=columns)
        df_template.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Format the template sheet
        workbook = writer.book
        worksheet = writer.sheets['Employee Data']
        
        # Set column widths
        worksheet.set_column('A:B', 15)  # Names
        worksheet.set_column('C:C', 12)  # Employee ID
        worksheet.set_column('D:D', 12)  # Date of Hire
        worksheet.set_column('E:E', 20)  # Overtime
        worksheet.set_column('F:F', 12)  # Crew
        worksheet.set_column('G:G', 20)  # Current Position
        worksheet.set_column('H:Q', 18)  # Position columns
        
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'employee_import_template_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@supervisor_bp.route('/employees/upload', methods=['POST'])
@login_required
@supervisor_required
def upload_employees():
    """Upload employee data from Excel file - REPLACES all existing data"""
    
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Please upload an Excel file (.xlsx or .xls)', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    try:
        # Read the Excel file first
        df = pd.read_excel(file, sheet_name='Employee Data')
        
        # Validate required columns
        required_columns = ['Last Name', 'First Name', 'Employee ID', 'Date of Hire', 
                          'Total Overtime (Last 3 Months)', 'Crew Assigned', 'Current Job Position']
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'Missing required columns: {", ".join(missing_columns)}', 'danger')
            return redirect(url_for('supervisor.employee_management'))
        
        # Get position columns (all columns after the first 7)
        position_columns = df.columns[7:].tolist()
        
        # Store current user ID before any database operations
        current_user_id = current_user.id
        
        # STEP 1: Close current session and create a new one for deletions
        db.session.close()
        
        # Use raw SQL with a new connection for all deletions
        with db.engine.connect() as conn:
            trans = conn.begin()
            try:
                # Delete in correct order to respect foreign key constraints
                conn.execute(db.text("DELETE FROM employee_skills WHERE employee_id != :user_id"), {'user_id': current_user_id})
                conn.execute(db.text("DELETE FROM overtime_history WHERE employee_id != :user_id"), {'user_id': current_user_id})
                conn.execute(db.text("DELETE FROM vacation_calendar WHERE employee_id != :user_id"), {'user_id': current_user_id})
                conn.execute(db.text("DELETE FROM time_off_request WHERE employee_id != :user_id"), {'user_id': current_user_id})
                conn.execute(db.text("DELETE FROM shift_swap_request WHERE requester_id != :user_id AND target_employee_id != :user_id"), {'user_id': current_user_id})
                conn.execute(db.text("DELETE FROM schedule WHERE employee_id != :user_id"), {'user_id': current_user_id})
                conn.execute(db.text("DELETE FROM employee WHERE id != :user_id"), {'user_id': current_user_id})
                trans.commit()
                print(f"Successfully deleted all employees except user {current_user_id}")
            except Exception as e:
                trans.rollback()
                flash(f'Error deleting existing data: {str(e)}', 'danger')
                return redirect(url_for('supervisor.employee_management'))
        
        # STEP 2: Create new session for insertions
        db.session.remove()  # Remove the old session
        db.session.begin()   # Start fresh
        
        # Ensure all positions exist in database
        for pos_name in position_columns:
            if pos_name and 'Qualified Position' not in pos_name:
                position = Position.query.filter_by(name=pos_name).first()
                if not position:
                    position = Position(name=pos_name, min_coverage=1)
                    db.session.add(position)
        
        db.session.commit()
        
        # STEP 3: Process and insert new employees
        employees_created = 0
        errors = []
        emails_processed = set()  # Track emails to avoid duplicates within the file
        
        for idx, row in df.iterrows():
            try:
                # Skip empty rows
                if pd.isna(row['Employee ID']) or pd.isna(row['Last Name']):
                    continue
                
                # Generate email
                first_name = str(row['First Name']).strip()
                last_name = str(row['Last Name']).strip()
                email = f"{first_name.lower()}.{last_name.lower()}@company.com"
                email = email.replace(' ', '')
                
                # Check for duplicates within this upload
                if email in emails_processed:
                    errors.append(f"Row {idx + 2}: Duplicate email {email} in file - skipping")
                    continue
                
                emails_processed.add(email)
                
                # Parse hire date
                hire_date = pd.to_datetime(row['Date of Hire']).date()
                
                # Get overtime hours (default to 0 if not provided)
                overtime_hours = float(row['Total Overtime (Last 3 Months)']) if pd.notna(row['Total Overtime (Last 3 Months)']) else 0.0
                
                # Create employee
                employee = Employee(
                    employee_id=str(int(row['Employee ID'])) if not pd.isna(row['Employee ID']) else None,
                    email=email,
                    name=f"{first_name} {last_name}",
                    password_hash=generate_password_hash('changeme123'),
                    is_supervisor=False,
                    crew=str(row['Crew Assigned']).strip(),
                    hire_date=hire_date,
                    vacation_days=10.0,
                    sick_days=5.0,
                    personal_days=3.0
                )
                
                # Set current position
                if pd.notna(row['Current Job Position']):
                    current_pos = Position.query.filter_by(name=str(row['Current Job Position']).strip()).first()
                    if current_pos:
                        employee.position_id = current_pos.id
                
                db.session.add(employee)
                db.session.flush()  # Flush to get the employee ID
                
                # Add overtime history if provided
                if overtime_hours > 0:
                    # Create overtime history for the last 13 weeks
                    for week_offset in range(13):
                        week_date = datetime.now().date() - timedelta(weeks=week_offset)
                        overtime_entry = OvertimeHistory(
                            employee_id=employee.id,
                            week_start_date=week_date - timedelta(days=week_date.weekday()),
                            overtime_hours=overtime_hours / 13  # Changed from 'hours' to 'overtime_hours'
                        )
                        db.session.add(overtime_entry)
                
                # Add skills/qualifications
                for pos_name in position_columns:
                    if pos_name and 'Qualified Position' not in pos_name and pd.notna(row[pos_name]):
                        cell_value = str(row[pos_name]).lower().strip()
                        
                        if cell_value in ['current', 'yes']:
                            position = Position.query.filter_by(name=pos_name).first()
                            if position:
                                # Create skill record
                                skill = Skill.query.filter_by(name=f"Qualified: {pos_name}").first()
                                if not skill:
                                    skill = Skill(
                                        name=f"Qualified: {pos_name}",
                                        description=f"Qualified to work as {pos_name}",
                                        category='position'
                                    )
                                    db.session.add(skill)
                                    db.session.flush()
                                
                                # Link employee to skill using the association table
                                db.session.execute(
                                    employee_skills.insert().values(
                                        employee_id=employee.id,
                                        skill_id=skill.id,
                                        certification_date=datetime.now().date(),
                                        is_primary=(cell_value == 'current')
                                    )
                                )
                
                employees_created += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                continue
        
        # Commit all the new employees
        db.session.commit()
        
        # Report results
        if errors:
            flash(f'Upload completed with {len(errors)} errors. {employees_created} employees created.', 'warning')
            for error in errors[:5]:  # Show first 5 errors
                flash(error, 'danger')
        else:
            flash(f'Successfully replaced all employee data. {employees_created} employees created.', 'success')
        
        return redirect(url_for('supervisor.employee_management'))
        
    except Exception as e:
        db.session.rollback()
        import traceback
        error_details = traceback.format_exc()
        print(f"Upload error details: {error_details}")  # Log to console for debugging
        flash(f'Error processing file: {str(e)}', 'danger')
        return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/download-current')
@login_required
@supervisor_required
def download_current_employees():
    """Download current employee data in the upload template format"""
    
    # Get all employees with their positions and skills
    employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
    
    # Get all positions
    positions = Position.query.order_by(Position.name).limit(10).all()
    
    # Build the data structure
    data = []
    for emp in employees:
        # Parse name into first and last
        name_parts = emp.name.split(' ', 1)
        first_name = name_parts[0] if name_parts else emp.name
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Calculate overtime (from overtime history)
        overtime_total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
            OvertimeHistory.employee_id == emp.id,
            OvertimeHistory.week_start_date >= datetime.now().date() - timedelta(weeks=13)
        ).scalar() or 0.0
        
        row = {
            'Last Name': last_name,
            'First Name': first_name,
            'Employee ID': emp.employee_id,
            'Date of Hire': emp.hire_date.strftime('%m/%d/%Y') if emp.hire_date else '',
            'Total Overtime (Last 3 Months)': round(overtime_total, 1),
            'Crew Assigned': emp.crew,
            'Current Job Position': emp.position.name if emp.position else ''
        }
        
        # Add position qualifications
        for pos in positions:
            # Check if employee has skill for this position
            skill_name = f"Qualified: {pos.name}"
            
            # Query the association table to check if employee has this skill
            has_skill = db.session.execute(
                db.select(employee_skills).where(
                    employee_skills.c.employee_id == emp.id
                ).join(
                    Skill, Skill.id == employee_skills.c.skill_id
                ).where(
                    Skill.name == skill_name
                )
            ).first() is not None
            
            if emp.position and emp.position.name == pos.name:
                row[pos.name] = 'current'
            elif has_skill:
                row[pos.name] = 'yes'
            else:
                row[pos.name] = ''
        
        data.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Employee Data', index=False)
        
        # Format the sheet
        workbook = writer.book
        worksheet = writer.sheets['Employee Data']
        
        # Set column widths
        worksheet.set_column('A:B', 15)  # Names
        worksheet.set_column('C:C', 12)  # Employee ID
        worksheet.set_column('D:D', 12)  # Date of Hire
        worksheet.set_column('E:E', 20)  # Overtime
        worksheet.set_column('F:F', 12)  # Crew
        worksheet.set_column('G:G', 20)  # Current Position
        worksheet.set_column('H:Q', 18)  # Position columns
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'current_employees_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

@supervisor_bp.route('/employees/management')
@login_required
@supervisor_required
def employee_management():
    """Employee management dashboard"""
    employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
    positions = Position.query.order_by(Position.name).all()
    
    return render_template('employee_management.html',
                         employees=employees,
                         positions=positions)

# ========== DEBUG ROUTES (REMOVE IN PRODUCTION) ==========

@supervisor_bp.route('/debug/vacation-calendar')
@login_required
@supervisor_required
def debug_vacation_calendar():
    """Debug route to check VacationCalendar data"""
    # Get all VacationCalendar entries
    vacation_entries = VacationCalendar.query.all()
    
    # Get all approved TimeOffRequests
    approved_requests = TimeOffRequest.query.filter_by(status='approved').all()
    
    # Check for missing entries
    missing_entries = []
    for request in approved_requests:
        # Check if this request has vacation calendar entries
        calendar_count = VacationCalendar.query.filter_by(request_id=request.id).count()
        expected_days = (request.end_date - request.start_date).days + 1
        
        if calendar_count != expected_days:
            missing_entries.append({
                'request_id': request.id,
                'employee': request.employee.name,
                'start_date': request.start_date.strftime('%Y-%m-%d'),
                'end_date': request.end_date.strftime('%Y-%m-%d'),
                'expected_days': expected_days,
                'actual_entries': calendar_count
            })
    
    return f"""
    <h2>Vacation Calendar Debug Info</h2>
    <h3>Summary</h3>
    <ul>
        <li>Total VacationCalendar entries: {len(vacation_entries)}</li>
        <li>Total approved TimeOffRequests: {len(approved_requests)}</li>
        <li>Requests with missing entries: {len(missing_entries)}</li>
    </ul>
    
    <h3>Missing Entries</h3>
    <pre>{missing_entries}</pre>
    
    <h3>All VacationCalendar Entries</h3>
    <table border="1">
        <tr>
            <th>ID</th>
            <th>Employee</th>
            <th>Date</th>
            <th>Type</th>
            <th>Request ID</th>
        </tr>
        {''.join(f'''
        <tr>
            <td>{v.id}</td>
            <td>{v.employee.name if v.employee else 'No employee'}</td>
            <td>{v.date.strftime('%Y-%m-%d') if v.date else 'No date'}</td>
            <td>{v.type}</td>
            <td>{v.request_id}</td>
        </tr>
        ''' for v in vacation_entries)}
    </table>
    
    <br><a href="/supervisor/time-off-requests">Back to Time Off Requests</a>
    <br><a href="/fix/populate-vacation-calendar">Fix Missing Entries</a>
    """

@supervisor_bp.route('/fix/populate-vacation-calendar')
@login_required
@supervisor_required
def fix_populate_vacation_calendar():
    """One-time fix to populate VacationCalendar for existing approved requests"""
    # Get all approved requests that don't have calendar entries
    approved_requests = TimeOffRequest.query.filter_by(status='approved').all()
    
    fixed_count = 0
    for request in approved_requests:
        # Check if this request already has calendar entries
        existing_count = VacationCalendar.query.filter_by(request_id=request.id).count()
        expected_days = (request.end_date - request.start_date).days + 1
        
        if existing_count < expected_days:
            # Create missing entries
            current_date = request.start_date
            while current_date <= request.end_date:
                # Check if entry already exists for this date
                existing = VacationCalendar.query.filter_by(
                    employee_id=request.employee_id,
                    date=current_date
                ).first()
                
                if not existing:
                    vacation_entry = VacationCalendar(
                        employee_id=request.employee_id,
                        date=current_date,
                        type=request.type,
                        request_id=request.id
                    )
                    db.session.add(vacation_entry)
                
                current_date += timedelta(days=1)
            
            fixed_count += 1
    
    db.session.commit()
    
    flash(f'Fixed {fixed_count} approved requests by adding vacation calendar entries.', 'success')
    return redirect(url_for('supervisor.vacation_calendar'))

# ========== OTHER SUPERVISOR ROUTES ==========

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    return render_template('coming_soon.html',
                         title='Coverage Needs',
                         description='View and manage staffing gaps and coverage requirements across all shifts and crews.',
                         icon='bi bi-shield-exclamation')

@supervisor_bp.route('/supervisor/suggestions')
@login_required
@supervisor_required
def suggestions():
    """View employee suggestions"""
    return render_template('coming_soon.html',
                         title='Employee Suggestions',
                         description='Review and respond to suggestions and feedback from your team members.',
                         icon='bi bi-lightbulb')

@supervisor_bp.route('/supervisor/overtime-distribution')
@login_required
@supervisor_required
def overtime_distribution():
    """Manage overtime distribution"""
    return render_template('coming_soon.html',
                         title='Overtime Distribution',
                         description='Track and fairly distribute overtime opportunities across all employees.',
                         icon='bi bi-clock-history')

@supervisor_bp.route('/supervisor/messages')
@login_required
@supervisor_required
def supervisor_messages():
    """Supervisor to supervisor messaging"""
    return render_template('coming_soon.html',
                         title='Supervisor Messages',
                         description='Communicate with other supervisors across different shifts and crews.',
                         icon='bi bi-envelope-fill')

@supervisor_bp.route('/casual-workers')
@login_required
@supervisor_required
def casual_workers():
    """Manage casual workers"""
    return render_template('coming_soon.html',
                         title='Casual Workers',
                         description='Manage your pool of temporary and on-call workers for filling coverage gaps.',
                         icon='bi bi-person-badge')

@supervisor_bp.route('/quick/position-broadcast')
@login_required
@supervisor_required
def position_broadcast():
    """Plantwide communications"""
    return render_template('coming_soon.html',
                         title='Position Broadcast',
                         description='Send announcements and messages to all employees in specific positions across all crews.',
                         icon='bi bi-megaphone')

# ========== DIAGNOSTIC AND IMPROVED UPLOAD ROUTES ==========

@supervisor_bp.route('/test-route')
@login_required
def test_route():
    """Simple test route to verify blueprint is working"""
    return "Supervisor blueprint is working!"

@supervisor_bp.route('/employees/check-duplicates')
@login_required
@supervisor_required
def check_duplicates():
    """Diagnostic route to check for duplicate emails"""
    # Check for Charles Parker specifically
    with db.engine.connect() as conn:
        result = conn.execute(
            db.text("SELECT id, employee_id, email, name FROM employee WHERE email = 'charles.parker@company.com'")
        ).fetchall()
        
        all_employees = conn.execute(
            db.text("SELECT id, employee_id, email, name FROM employee ORDER BY email")
        ).fetchall()
    
    output = "<h2>Charles Parker Check:</h2>"
    if result:
        for row in result:
            output += f"<p>ID: {row[0]}, Employee ID: {row[1]}, Email: {row[2]}, Name: {row[3]}</p>"
    else:
        output += "<p>No Charles Parker found</p>"
    
    output += f"<h2>Total Employees: {len(all_employees)}</h2>"
    output += "<h3>All Employees:</h3><ul>"
    for emp in all_employees:
        output += f"<li>ID: {emp[0]}, Employee ID: {emp[1]}, Email: {emp[2]}, Name: {emp[3]}</li>"
    output += "</ul>"
    
    output += '<p><a href="/employees/management">Back to Employee Management</a></p>'
    return output

@supervisor_bp.route('/employees/force-cleanup')
@login_required
@supervisor_required
def force_cleanup():
    """Force cleanup of all employees except current user"""
    current_user_id = current_user.id
    
    with db.engine.connect() as conn:
        trans = conn.begin()
        try:
            # Get count before deletion
            before_count = conn.execute(db.text("SELECT COUNT(*) FROM employee")).scalar()
            
            # Delete all related data in the correct order
            # First, tables that reference other tables
            conn.execute(db.text("DELETE FROM position_message_read WHERE reader_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM maintenance_update WHERE author_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM shift_trade_proposal WHERE proposer_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM shift_trade WHERE employee1_id != :user_id AND employee2_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM coverage_notification WHERE sent_to_employee_id != :user_id AND sent_by_id != :user_id"), {'user_id': current_user_id})
            
            # Then, direct employee references
            conn.execute(db.text("DELETE FROM employee_skills WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM overtime_history WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM vacation_calendar WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM time_off_request WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM shift_swap_request WHERE requester_id != :user_id AND target_employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM schedule WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM availability WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM coverage_request WHERE requester_id != :user_id AND filled_by_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM schedule_suggestion WHERE employee_id != :user_id AND reviewed_by_id != :user_id"), {'user_id': current_user_id})
            
            # Sleep/health related tables
            conn.execute(db.text("DELETE FROM circadian_profile WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM sleep_log WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM sleep_recommendation WHERE employee_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM shift_transition_plan WHERE employee_id != :user_id"), {'user_id': current_user_id})
            
            # Communication tables
            conn.execute(db.text("DELETE FROM supervisor_message WHERE sender_id != :user_id AND recipient_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM position_message WHERE sender_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM maintenance_issue WHERE reporter_id != :user_id AND assigned_to_id != :user_id"), {'user_id': current_user_id})
            
            # Shift trade marketplace
            conn.execute(db.text("DELETE FROM shift_trade_post WHERE poster_id != :user_id"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM trade_match_preference WHERE employee_id != :user_id"), {'user_id': current_user_id})
            
            # Casual worker assignments
            conn.execute(db.text("DELETE FROM casual_assignment"), {})
            
            # Maintenance manager role
            conn.execute(db.text("DELETE FROM maintenance_manager WHERE employee_id != :user_id"), {'user_id': current_user_id})
            
            # File uploads
            conn.execute(db.text("DELETE FROM file_upload WHERE uploaded_by_id != :user_id"), {'user_id': current_user_id})
            
            # Finally delete employees
            deleted = conn.execute(db.text("DELETE FROM employee WHERE id != :user_id"), {'user_id': current_user_id})
            
            trans.commit()
            
            # Get count after deletion
            after_count = conn.execute(db.text("SELECT COUNT(*) FROM employee")).scalar()
            
            flash(f'Cleanup complete. Before: {before_count} employees, After: {after_count} employees', 'success')
            
        except Exception as e:
            trans.rollback()
            flash(f'Cleanup failed: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/upload-v2', methods=['POST'])
@login_required
@supervisor_required
def upload_employees_v2():
    """Alternative upload method with better error handling"""
    
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        flash('Please upload an Excel file (.xlsx or .xls)', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    try:
        # Read the Excel file
        df = pd.read_excel(file, sheet_name='Employee Data')
        
        # Validate required columns
        required_columns = ['Last Name', 'First Name', 'Employee ID', 'Date of Hire', 
                          'Total Overtime (Last 3 Months)', 'Crew Assigned', 'Current Job Position']
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'Missing required columns: {", ".join(missing_columns)}', 'danger')
            return redirect(url_for('supervisor.employee_management'))
        
        # Get position columns
        position_columns = df.columns[7:].tolist()
        
        # Store current user ID
        current_user_id = current_user.id
        
        # STEP 1: Force clean all existing data using raw SQL
        with db.engine.begin() as conn:  # This automatically commits or rolls back
            # Delete all related data first
            conn.execute(db.text("DELETE FROM employee_skills WHERE employee_id IN (SELECT id FROM employee WHERE id != :user_id)"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM overtime_history WHERE employee_id IN (SELECT id FROM employee WHERE id != :user_id)"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM vacation_calendar WHERE employee_id IN (SELECT id FROM employee WHERE id != :user_id)"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM time_off_request WHERE employee_id IN (SELECT id FROM employee WHERE id != :user_id)"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM shift_swap_request WHERE requester_id IN (SELECT id FROM employee WHERE id != :user_id) OR target_employee_id IN (SELECT id FROM employee WHERE id != :user_id)"), {'user_id': current_user_id})
            conn.execute(db.text("DELETE FROM schedule WHERE employee_id IN (SELECT id FROM employee WHERE id != :user_id)"), {'user_id': current_user_id})
            
            # Finally delete employees
            conn.execute(db.text("DELETE FROM employee WHERE id != :user_id"), {'user_id': current_user_id})
        
        # STEP 2: Clear the SQLAlchemy session completely
        db.session.remove()
        db.session.close_all()
        
        # STEP 3: Process the upload with a fresh session
        employees_created = 0
        errors = []
        emails_in_file = {}  # Track emails to handle duplicates in file
        
        # First pass - collect all emails and check for duplicates in the file
        for idx, row in df.iterrows():
            if pd.isna(row['Employee ID']) or pd.isna(row['Last Name']):
                continue
                
            first_name = str(row['First Name']).strip()
            last_name = str(row['Last Name']).strip()
            email = f"{first_name.lower()}.{last_name.lower()}@company.com".replace(' ', '')
            
            if email in emails_in_file:
                errors.append(f"Row {idx + 2}: Duplicate email {email} (also in row {emails_in_file[email]})")
            else:
                emails_in_file[email] = idx + 2
        
        # Create positions first
        for pos_name in position_columns:
            if pos_name and 'Qualified Position' not in pos_name:
                position = Position.query.filter_by(name=pos_name).first()
                if not position:
                    position = Position(name=pos_name, min_coverage=1)
                    db.session.add(position)
        
        db.session.commit()
        
        # Second pass - create employees
        for idx, row in df.iterrows():
            if pd.isna(row['Employee ID']) or pd.isna(row['Last Name']):
                continue
            
            first_name = str(row['First Name']).strip()
            last_name = str(row['Last Name']).strip()
            email = f"{first_name.lower()}.{last_name.lower()}@company.com".replace(' ', '')
            
            # Skip if this was a duplicate
            if emails_in_file.get(email) != idx + 2:
                continue
            
            try:
                # Create employee
                employee = Employee(
                    employee_id=str(int(row['Employee ID'])),
                    email=email,
                    name=f"{first_name} {last_name}",
                    password_hash=generate_password_hash('changeme123'),
                    is_supervisor=False,
                    crew=str(row['Crew Assigned']).strip(),
                    hire_date=pd.to_datetime(row['Date of Hire']).date(),
                    vacation_days=10.0,
                    sick_days=5.0,
                    personal_days=3.0
                )
                
                # Set position
                if pd.notna(row['Current Job Position']):
                    position = Position.query.filter_by(name=str(row['Current Job Position']).strip()).first()
                    if position:
                        employee.position_id = position.id
                
                db.session.add(employee)
                db.session.flush()
                
                # Add overtime history
                overtime_hours = float(row['Total Overtime (Last 3 Months)']) if pd.notna(row['Total Overtime (Last 3 Months)']) else 0.0
                if overtime_hours > 0:
                    for week_offset in range(13):
                        week_date = datetime.now().date() - timedelta(weeks=week_offset)
                        week_start = week_date - timedelta(days=week_date.weekday())
                        
                        overtime_entry = OvertimeHistory(
                            employee_id=employee.id,
                            week_start_date=week_start,
                            overtime_hours=overtime_hours / 13,
                            regular_hours=40,
                            total_hours=40 + (overtime_hours / 13)
                        )
                        db.session.add(overtime_entry)
                
                # Add skills
                for pos_name in position_columns:
                    if pos_name and 'Qualified Position' not in pos_name and pd.notna(row[pos_name]):
                        cell_value = str(row[pos_name]).lower().strip()
                        
                        if cell_value in ['current', 'yes']:
                            skill_name = f"Qualified: {pos_name}"
                            skill = Skill.query.filter_by(name=skill_name).first()
                            if not skill:
                                skill = Skill(
                                    name=skill_name,
                                    description=f"Qualified to work as {pos_name}",
                                    category='position'
                                )
                                db.session.add(skill)
                                db.session.flush()
                            
                            # Add skill to employee
                            stmt = employee_skills.insert().values(
                                employee_id=employee.id,
                                skill_id=skill.id,
                                certification_date=datetime.now().date(),
                                is_primary=(cell_value == 'current')
                            )
                            db.session.execute(stmt)
                
                employees_created += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                db.session.rollback()
                # Start fresh for next employee
                db.session.begin()
        
        # Final commit
        db.session.commit()
        
        # Report results
        if errors:
            flash(f'Upload completed with {len(errors)} errors. {employees_created} employees created.', 'warning')
            for error in errors[:10]:
                flash(error, 'danger')
        else:
            flash(f'Successfully imported {employees_created} employees.', 'success')
        
        return redirect(url_for('supervisor.employee_management'))
        
    except Exception as e:
        db.session.rollback()
        import traceback
        flash(f'Error: {str(e)}', 'danger')
        print(traceback.format_exc())
        return redirect(url_for('supervisor.employee_management'))
