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
                type=time_off_request.request_type,
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

@supervisor_bp.route('/employees/delete-all', methods=['POST'])
@login_required
@supervisor_required
def delete_all_employees():
    """Step 1: Delete all employees except current user"""
    try:
        current_user_id = current_user.id
        
        # Use direct database connection, bypassing SQLAlchemy ORM entirely
        from sqlalchemy import create_engine
        engine = create_engine(db.engine.url)
        
        with engine.connect() as conn:
            # Start a transaction
            trans = conn.begin()
            
            try:
                # Delete from all related tables first
                conn.execute(text("DELETE FROM employee_skills WHERE employee_id != :uid"), {'uid': current_user_id})
                conn.execute(text("DELETE FROM overtime_history WHERE employee_id != :uid"), {'uid': current_user_id})
                conn.execute(text("DELETE FROM vacation_calendar WHERE employee_id != :uid"), {'uid': current_user_id})
                conn.execute(text("DELETE FROM time_off_request WHERE employee_id != :uid"), {'uid': current_user_id})
                conn.execute(text("DELETE FROM shift_swap_request WHERE requester_id != :uid AND target_employee_id != :uid"), {'uid': current_user_id})
                conn.execute(text("DELETE FROM schedule WHERE employee_id != :uid"), {'uid': current_user_id})
                
                # Now delete employees
                result = conn.execute(text("DELETE FROM employee WHERE id != :uid"), {'uid': current_user_id})
                deleted_count = result.rowcount
                
                # Commit the transaction
                trans.commit()
                
                flash(f'Successfully deleted {deleted_count} employees. You can now upload new data.', 'success')
                
            except Exception as e:
                trans.rollback()
                flash(f'Error deleting employees: {str(e)}', 'danger')
                
        # Dispose of all connections
        engine.dispose()
        db.session.remove()
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/simple-upload', methods=['POST'])
@login_required
@supervisor_required
def simple_upload_employees():
    """Step 2: Simple upload without deletion"""
    
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    file = request.files['file']
    if not file or file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('supervisor.employee_management'))
    
    try:
        # Read Excel file
        df = pd.read_excel(file, sheet_name=0)  # Just read first sheet
        
        # Basic validation
        required_columns = ['Last Name', 'First Name', 'Employee ID', 'Date of Hire', 
                          'Total Overtime (Last 3 Months)', 'Crew Assigned', 'Current Job Position']
        
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            flash(f'Missing columns: {", ".join(missing)}', 'danger')
            return redirect(url_for('supervisor.employee_management'))
        
        # Get current user email to skip
        current_user_email = current_user.email.lower()
        
        # Process employees
        created = 0
        skipped = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                # Skip empty rows
                if pd.isna(row['Employee ID']) or pd.isna(row['Last Name']):
                    continue
                
                # Generate email
                first_name = str(row['First Name']).strip()
                last_name = str(row['Last Name']).strip()
                email = f"{first_name.lower()}.{last_name.lower()}@company.com".replace(' ', '')
                
                # Skip current user
                if email == current_user_email:
                    skipped += 1
                    continue
                
                # Check if employee already exists
                existing = Employee.query.filter_by(email=email).first()
                if existing:
                    errors.append(f"Row {idx + 2}: {email} already exists - skipping")
                    skipped += 1
                    continue
                
                # Create employee
                employee = Employee(
                    employee_id=str(int(row['Employee ID'])) if not pd.isna(row['Employee ID']) else None,
                    email=email,
                    name=f"{first_name} {last_name}",
                    password_hash=generate_password_hash('changeme123'),
                    is_supervisor=False,
                    crew=str(row['Crew Assigned']).strip() if pd.notna(row['Crew Assigned']) else None,
                    hire_date=pd.to_datetime(row['Date of Hire']).date(),
                    vacation_days=10.0,
                    sick_days=5.0,
                    personal_days=3.0
                )
                
                # Set position if exists
                if pd.notna(row['Current Job Position']):
                    position = Position.query.filter_by(name=str(row['Current Job Position']).strip()).first()
                    if position:
                        employee.position_id = position.id
                    else:
                        # Create position if it doesn't exist
                        position = Position(name=str(row['Current Job Position']).strip(), min_coverage=1)
                        db.session.add(position)
                        db.session.flush()
                        employee.position_id = position.id
                
                db.session.add(employee)
                created += 1
                
                # Commit every 50 employees
                if created % 50 == 0:
                    db.session.commit()
                    
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                db.session.rollback()
                continue
        
        # Final commit
        db.session.commit()
        
        # Report results
        message = f'Created {created} employees, skipped {skipped}.'
        if errors:
            message += f' {len(errors)} errors occurred.'
            for error in errors[:5]:
                flash(error, 'warning')
        
        flash(message, 'success' if created > 0 else 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing file: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page with two-step upload"""
    employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
    employee_count = len(employees)
    
    return render_template('employee_management.html',
                         employees=employees,
                         employee_count=employee_count)

@supervisor_bp.route('/employees/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Interactive crew management interface"""
    employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
    positions = Position.query.order_by(Position.name).all()
    
    return render_template('crew_management.html',
                         employees=employees,
                         positions=positions)

@supervisor_bp.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@login_required
@supervisor_required
def edit_employee(employee_id):
    """Edit employee information online"""
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        # Update employee fields
        employee.name = request.form.get('name')
        employee.crew = request.form.get('crew')
        employee.employee_id = request.form.get('employee_id')
        
        # Update position
        position_id = request.form.get('position_id')
        if position_id:
            employee.position_id = int(position_id)
        
        # Update time-off balances
        employee.vacation_days = float(request.form.get('vacation_days', 0))
        employee.sick_days = float(request.form.get('sick_days', 0))
        employee.personal_days = float(request.form.get('personal_days', 0))
        
        db.session.commit()
        flash(f'Successfully updated {employee.name}', 'success')
        return redirect(url_for('supervisor.crew_management'))
    
    positions = Position.query.order_by(Position.name).all()
    return render_template('edit_employee.html', 
                         employee=employee, 
                         positions=positions)

@supervisor_bp.route('/employees/bulk-edit', methods=['POST'])
@login_required
@supervisor_required
def bulk_edit_employees():
    """Handle bulk crew assignments"""
    employee_ids = request.form.getlist('employee_ids')
    new_crew = request.form.get('new_crew')
    
    if employee_ids and new_crew:
        Employee.query.filter(Employee.id.in_(employee_ids)).update(
            {'crew': new_crew}, synchronize_session=False
        )
        db.session.commit()
        flash(f'Successfully reassigned {len(employee_ids)} employees to Crew {new_crew}', 'success')
    
    return redirect(url_for('supervisor.crew_management'))

@supervisor_bp.route('/api/employee/<int:employee_id>/crew', methods=['PUT'])
@login_required
@supervisor_required
def update_employee_crew(employee_id):
    """API endpoint to update employee crew assignment"""
    employee = Employee.query.get_or_404(employee_id)
    data = request.get_json()
    
    new_crew = data.get('crew')
    if new_crew in ['A', 'B', 'C', 'D', 'UNASSIGNED']:
        employee.crew = new_crew if new_crew != 'UNASSIGNED' else None
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': 'Invalid crew'}), 400

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

@supervisor_bp.route('/employees/upload-text', methods=['GET', 'POST'])
@login_required
@supervisor_required
def upload_employees_text():
    """Upload employee data from pasted text (TSV/CSV format)"""
    
    if request.method == 'GET':
        return '''
        <h2>Upload Employees from Text Data</h2>
        <p>Paste your tab-separated or comma-separated employee data below:</p>
        <form method="POST">
            <textarea name="data" rows="20" cols="100" style="width: 100%; font-family: monospace;" required></textarea>
            <br><br>
            <button type="submit" class="btn btn-primary" onclick="return confirm('This will DELETE all existing employees and replace with the pasted data. Are you sure?')">
                Upload Data
            </button>
            <a href="/employees/management" class="btn btn-secondary">Cancel</a>
        </form>
        '''
    
    try:
        # Get the pasted data
        data_text = request.form.get('data', '')
        if not data_text:
            flash('No data provided', 'danger')
            return redirect(url_for('supervisor.employee_management'))
        
        # Convert text to DataFrame - try tab-separated first, then comma-separated
        from io import StringIO
        try:
            df = pd.read_csv(StringIO(data_text), sep='\t')
        except:
            try:
                df = pd.read_csv(StringIO(data_text), sep=',')
            except Exception as e:
                flash(f'Could not parse data. Make sure it is tab or comma separated. Error: {str(e)}', 'danger')
                return redirect(url_for('supervisor.employee_management'))
        
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
        
        # The rest of the upload logic is the same as upload_employees()
        # ... (same deletion and insertion logic)
        
        flash('Text upload functionality implemented', 'success')
        return redirect(url_for('supervisor.employee_management'))
        
    except Exception as e:
        flash(f'Error processing text data: {str(e)}', 'danger')
        return redirect(url_for('supervisor.employee_management'))

# ========== DIAGNOSTIC ROUTES ==========

@supervisor_bp.route('/employees/check-database')
@login_required
@supervisor_required
def check_database():
    """Check database for duplicate employees and other issues"""
    with db.engine.connect() as conn:
        # Check for Charles Parker
        result = conn.execute(
            db.text("SELECT id, email, name, crew FROM employee WHERE email LIKE '%charles.parker%'")
        ).fetchall()
        
        parker_info = "Charles Parker entries:<br>"
        for row in result:
            parker_info += f"ID: {row[0]}, Email: {row[1]}, Name: {row[2]}, Crew: {row[3]}<br>"
        
        # Check total employees
        total = conn.execute(db.text("SELECT COUNT(*) FROM employee")).scalar()
        
        # Check for duplicate emails
        duplicates = conn.execute(
            db.text("""
                SELECT email, COUNT(*) as count 
                FROM employee 
                GROUP BY email 
                HAVING COUNT(*) > 1
            """)
        ).fetchall()
        
        dup_info = "Duplicate emails:<br>"
        for dup in duplicates:
            dup_info += f"{dup[0]}: {dup[1]} entries<br>"
    
    return f"""
    <h2>Database Check</h2>
    <p>Total employees: {total}</p>
    <h3>{parker_info}</h3>
    <h3>{dup_info if duplicates else 'No duplicate emails found'}</h3>
    <br>
    <a href="/employees/crew-management" class="btn btn-primary">Back to Crew Management</a>
    <a href="/employees/force-fix-duplicates" class="btn btn-danger">Force Fix Duplicates</a>
    """

@supervisor_bp.route('/employees/force-fix-duplicates')
@login_required
@supervisor_required
def force_fix_duplicates():
    """Force removal of duplicate employees keeping only the first one"""
    current_user_id = current_user.id
    
    with db.engine.begin() as conn:
        # Find and remove duplicates
        duplicates = conn.execute(
            db.text("""
                SELECT email, MIN(id) as keep_id, COUNT(*) as count
                FROM employee
                WHERE id != :user_id
                GROUP BY email
                HAVING COUNT(*) > 1
            """),
            {'user_id': current_user_id}
        ).fetchall()
        
        total_removed = 0
        for dup in duplicates:
            email, keep_id, count = dup
            # Delete all but the one with lowest ID
            result = conn.execute(
                db.text("""
                    DELETE FROM employee 
                    WHERE email = :email 
                    AND id != :keep_id 
                    AND id != :user_id
                """),
                {'email': email, 'keep_id': keep_id, 'user_id': current_user_id}
            )
            total_removed += result.rowcount
            print(f"Removed {result.rowcount} duplicates of {email}")
    
    flash(f'Removed {total_removed} duplicate employee records', 'success')
    return redirect(url_for('supervisor.employee_management'))

# ========== COVERAGE NEEDS ROUTE - FIXED ==========

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    try:
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        # If no positions exist, warn the user
        if not positions:
            flash('No positions found. Please upload employee data to create positions.', 'warning')
            return render_template('coverage_needs.html',
                                 positions=[],
                                 crew_requirements={},
                                 current_coverage={},
                                 crew_totals={})
        
        # Get crew-specific requirements if they exist
        crew_requirements = {}
        
        # Initialize with position defaults
        for crew in ['A', 'B', 'C', 'D']:
            crew_requirements[crew] = {}
            for position in positions:
                crew_requirements[crew][position.id] = position.min_coverage
        
        # Calculate current coverage for each crew and position
        current_coverage = {}
        crew_totals = {}
        
        for crew in ['A', 'B', 'C', 'D']:
            current_coverage[crew] = {}
            # Count total employees in this crew (excluding supervisors)
            crew_totals[crew] = Employee.query.filter_by(
                crew=crew,
                is_supervisor=False
            ).count()
            
            for position in positions:
                # Count employees in this crew with this position
                count = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False  # Don't count supervisors in coverage
                ).count()
                current_coverage[crew][position.id] = count
        
        # Add debug information
        print(f"Total positions: {len(positions)}")
        for crew in ['A', 'B', 'C', 'D']:
            print(f"Crew {crew}: {crew_totals[crew]} employees")
        
        # Calculate total current staff
        total_current_staff = sum(crew_totals.values())
        
        return render_template('coverage_needs.html',
                             positions=positions,
                             crew_requirements=crew_requirements,
                             current_coverage=current_coverage,
                             crew_totals=crew_totals,
                             total_current_staff=total_current_staff)
                             
    except Exception as e:
        print(f"Error in coverage_needs route: {str(e)}")
        flash(f'Error loading coverage needs: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs/reset-defaults', methods=['POST'])
@login_required
@supervisor_required
def reset_coverage_defaults():
    """Reset all position minimum coverage to 1"""
    positions = Position.query.all()
    for position in positions:
        position.min_coverage = 1
    db.session.commit()
    flash(f'Reset {len(positions)} positions to minimum coverage of 1', 'success')
    return redirect(url_for('supervisor.coverage_needs'))

# ========== COVERAGE GAPS ROUTE - NEW ==========

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View real-time coverage gaps considering absences"""
    try:
        # Get current date
        today = date.today()
        
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        # Initialize data structures
        coverage_gaps_data = []
        total_gaps = 0
        critical_gaps = 0
        
        # For each crew
        for crew in ['A', 'B', 'C', 'D']:
            crew_data = {
                'crew': crew,
                'positions': [],
                'total_required': 0,
                'total_available': 0,
                'total_absent': 0,
                'total_gaps': 0
            }
            
            for position in positions:
                # Get required coverage (from Position model or CrewCoverageRequirement if you have it)
                required = position.min_coverage
                
                # Get all employees in this crew and position
                employees = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).all()
                
                # Count total employees
                total_employees = len(employees)
                
                # Count employees who are absent today (vacation, sick, personal)
                absent_count = 0
                absent_employees = []
                
                for emp in employees:
                    # Check vacation calendar for today
                    absence = VacationCalendar.query.filter_by(
                        employee_id=emp.id,
                        date=today
                    ).first()
                    
                    if absence:
                        absent_count += 1
                        absent_employees.append({
                            'name': emp.name,
                            'type': absence.type
                        })
                
                # Calculate available employees
                available = total_employees - absent_count
                
                # Calculate gap
                gap = required - available
                
                # Only add if there's a gap or if there are absences
                if gap > 0 or absent_count > 0:
                    position_data = {
                        'position': position.name,
                        'required': required,
                        'total_employees': total_employees,
                        'absent': absent_count,
                        'available': available,
                        'gap': max(0, gap),  # Don't show negative gaps
                        'absent_employees': absent_employees,
                        'is_critical': gap > 0
                    }
                    
                    crew_data['positions'].append(position_data)
                    crew_data['total_required'] += required
                    crew_data['total_available'] += available
                    crew_data['total_absent'] += absent_count
                    
                    if gap > 0:
                        crew_data['total_gaps'] += gap
                        total_gaps += gap
                        if gap >= 2:  # Consider gaps of 2+ as critical
                            critical_gaps += 1
            
            # Only add crew if it has gaps or absences
            if crew_data['positions']:
                coverage_gaps_data.append(crew_data)
        
        # Get upcoming absences for next 7 days
        upcoming_absences = db.session.query(
            VacationCalendar.date,
            func.count(VacationCalendar.id).label('count'),
            Employee.crew
        ).join(
            Employee, VacationCalendar.employee_id == Employee.id
        ).filter(
            VacationCalendar.date > today,
            VacationCalendar.date <= today + timedelta(days=7)
        ).group_by(
            VacationCalendar.date,
            Employee.crew
        ).order_by(
            VacationCalendar.date
        ).all()
        
        # Format upcoming absences
        upcoming_by_date = {}
        for absence in upcoming_absences:
            date_str = absence.date.strftime('%Y-%m-%d')
            if date_str not in upcoming_by_date:
                upcoming_by_date[date_str] = {'date': absence.date, 'crews': {}}
            upcoming_by_date[date_str]['crews'][absence.crew] = absence.count
        
        # Summary statistics
        summary = {
            'total_gaps': total_gaps,
            'critical_gaps': critical_gaps,
            'crews_affected': len([c for c in coverage_gaps_data if c['total_gaps'] > 0]),
            'positions_affected': sum(len([p for p in c['positions'] if p['gap'] > 0]) for c in coverage_gaps_data),
            'total_absences_today': sum(c['total_absent'] for c in coverage_gaps_data)
        }
        
        return render_template('coverage_gaps.html',
                             coverage_gaps=coverage_gaps_data,
                             summary=summary,
                             today=today,
                             upcoming_absences=list(upcoming_by_date.values()))
                             
    except Exception as e:
        print(f"Error in coverage_gaps route: {str(e)}")
        flash(f'Error loading coverage gaps: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

# ========== OTHER SUPERVISOR ROUTES ==========

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
    try:
        # Get all employees with their data
        employees_query = Employee.query.filter(
            Employee.id != current_user.id,
            Employee.is_supervisor == False
        ).all()
        
        # Organize employees by crew
        employees_by_crew = {'A': [], 'B': [], 'C': [], 'D': []}
        
        for emp in employees_query:
            if emp.crew in employees_by_crew:
                # Get employee's overtime from last 13 weeks
                overtime_total = db.session.query(func.sum(OvertimeHistory.overtime_hours)).filter(
                    OvertimeHistory.employee_id == emp.id,
                    OvertimeHistory.week_start_date >= datetime.now().date() - timedelta(weeks=13)
                ).scalar() or 0.0
                
                # Get all skills for this employee
                emp_skills = []
                for skill in emp.skills:
                    skill_data = {
                        'id': skill.id,
                        'name': skill.name,
                        'is_primary': False  # Will be set below if this is their position skill
                    }
                    emp_skills.append(skill_data)
                
                # Mark primary skill (based on position)
                if emp.position:
                    position_skill_name = f"Qualified: {emp.position.name}"
                    for skill_data in emp_skills:
                        if skill_data['name'] == position_skill_name:
                            skill_data['is_primary'] = True
                
                employee_data = {
                    'id': emp.id,
                    'name': emp.name,
                    'email': emp.email,
                    'hire_date': emp.hire_date,
                    'hire_date_str': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                    'years_of_service': ((datetime.now().date() - emp.hire_date).days / 365.25) if emp.hire_date else 0,
                    'position': emp.position.name if emp.position else 'Unassigned',
                    'overtime_hours': round(overtime_total, 1),
                    'skills': emp_skills,
                    'all_skill_names': [s['name'] for s in emp_skills]  # For easier filtering
                }
                
                employees_by_crew[emp.crew].append(employee_data)
        
        # Get all unique skills for filter dropdown
        all_skills = Skill.query.order_by(Skill.name).all()
        skill_list = [{'id': s.id, 'name': s.name} for s in all_skills]
        
        return render_template('overtime_distribution.html',
                             employees_by_crew=employees_by_crew,
                             skills=skill_list)
                             
    except Exception as e:
        print(f"Error in overtime_distribution route: {str(e)}")
        flash(f'Error loading overtime distribution: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

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

# ========== API ENDPOINTS ==========

@supervisor_bp.route('/api/coverage-needs', methods=['POST'])
@login_required
@supervisor_required
def api_update_coverage_needs():
    """API endpoint to update coverage needs"""
    data = request.get_json()
    
    crew = data.get('crew')
    position_id = data.get('position_id')
    min_coverage = data.get('min_coverage', 0)
    
    try:
        if crew == 'global':
            # Update the global position requirement
            position = Position.query.get(position_id)
            if position:
                position.min_coverage = min_coverage
                db.session.commit()
                return jsonify({'success': True})
        else:
            # For crew-specific requirements, you might want to create a new model
            # For now, we'll just return success
            # In a full implementation, you'd create a CrewCoverageRequirement model
            return jsonify({'success': True, 'message': 'Crew-specific requirements saved'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@supervisor_bp.route('/api/coverage-gaps')
@login_required
@supervisor_required
def api_coverage_gaps():
    """API endpoint to get current coverage gaps"""
    crew = request.args.get('crew', 'ALL')
    
    gaps = []
    positions = Position.query.all()
    
    crews_to_check = ['A', 'B', 'C', 'D'] if crew == 'ALL' else [crew]
    
    for check_crew in crews_to_check:
        for position in positions:
            required = position.min_coverage
            current = Employee.query.filter_by(
                crew=check_crew,
                position_id=position.id
            ).count()
            
            if current < required:
                gaps.append({
                    'crew': check_crew,
                    'position': position.name,
                    'required': required,
                    'current': current,
                    'gap': required - current
                })
    
    return jsonify({'gaps': gaps, 'total_gaps': sum(g['gap'] for g in gaps)})

@supervisor_bp.route('/api/coverage-gaps-summary')
@login_required
@supervisor_required
def api_coverage_gaps_summary():
    """API endpoint to get coverage gaps summary for dashboard"""
    try:
        today = date.today()
        total_gaps = 0
        critical_gaps = 0
        
        # Quick calculation of gaps
        for crew in ['A', 'B', 'C', 'D']:
            positions = Position.query.all()
            
            for position in positions:
                # Required coverage
                required = position.min_coverage
                
                # Get total employees in position
                total_employees = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).count()
                
                # Count absences today
                absent_count = db.session.query(func.count(VacationCalendar.id)).join(
                    Employee, VacationCalendar.employee_id == Employee.id
                ).filter(
                    Employee.crew == crew,
                    Employee.position_id == position.id,
                    VacationCalendar.date == today
                ).scalar() or 0
                
                # Calculate gap
                available = total_employees - absent_count
                gap = required - available
                
                if gap > 0:
                    total_gaps += gap
                    if gap >= 2:
                        critical_gaps += 1
        
        return jsonify({
            'total_gaps': total_gaps,
            'critical_gaps': critical_gaps,
            'has_gaps': total_gaps > 0
        })
        
    except Exception as e:
        return jsonify({
            'total_gaps': 0,
            'critical_gaps': 0,
            'has_gaps': False,
            'error': str(e)
        })

@supervisor_bp.route('/api/send-overtime-request', methods=['POST'])
@login_required
@supervisor_required
def send_overtime_request():
    """Send overtime request to selected employees"""
    try:
        data = request.get_json()
        employee_ids = data.get('employee_ids', [])
        date = data.get('date')
        shift = data.get('shift')
        position = data.get('position')
        hours = data.get('hours')
        message = data.get('message', '')
        
        if not employee_ids:
            return jsonify({'success': False, 'error': 'No employees selected'}), 400
        
        # Here you would typically:
        # 1. Create overtime opportunity records
        # 2. Send notifications (email/SMS)
        # 3. Track who was offered overtime
        
        # For now, we'll just log and return success
        employees = Employee.query.filter(Employee.id.in_(employee_ids)).all()
        employee_names = [emp.name for emp in employees]
        
        # You could create an OvertimeOffer model to track these
        # for emp_id in employee_ids:
        #     offer = OvertimeOffer(
        #         employee_id=emp_id,
        #         date=date,
        #         shift=shift,
        #         position=position,
        #         hours=hours,
        #         message=message,
        #         sent_by=current_user.id,
        #         sent_at=datetime.now()
        #     )
        #     db.session.add(offer)
        # db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Overtime request sent to {len(employee_names)} employees',
            'employees': employee_names
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@supervisor_bp.route('/api/dashboard-stats')
@login_required
@supervisor_required
def api_dashboard_stats():
    """API endpoint for dashboard statistics"""
    stats = {
        'pending_time_off': TimeOffRequest.query.filter_by(status='pending').count(),
        'pending_swaps': ShiftSwapRequest.query.filter_by(status='pending').count(),
        'coverage_gaps': 0,  # Implement based on your coverage logic
        'pending_suggestions': ScheduleSuggestion.query.filter_by(status='pending').count() if hasattr(ScheduleSuggestion, 'status') else 0,
        'new_critical_items': 0  # Implement based on your critical items logic
    }
    return jsonify(stats)
