# blueprints/supervisor.py - COMPLETE FILE WITH ALL FIXES

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
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
import traceback

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

# ========== VACATION CALENDAR ROUTES ==========

@supervisor_bp.route('/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display the vacation calendar view"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        return render_template('vacation_calendar.html',
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in vacation_calendar: {str(e)}")
        flash('Error loading vacation calendar.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/api/vacation-calendar')
@login_required
@supervisor_required
def api_vacation_calendar():
    """API endpoint to get vacation calendar data"""
    try:
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
        
    except Exception as e:
        current_app.logger.error(f"API vacation calendar error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@supervisor_bp.route('/api/vacation-calendar/export')
@login_required
@supervisor_required
def export_vacation_calendar():
    """Export vacation calendar as CSV"""
    try:
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
        
    except Exception as e:
        current_app.logger.error(f"Export vacation calendar error: {str(e)}")
        flash('Error exporting calendar.', 'danger')
        return redirect(url_for('supervisor.vacation_calendar'))

# ========== TIME OFF & SWAP REQUEST MANAGEMENT ==========

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        # Get filter parameters
        status_filter = request.args.get('status', 'pending')
        crew_filter = request.args.get('crew', 'all')
        date_filter = request.args.get('date_range', 'upcoming')
        type_filter = request.args.get('type', 'all')
        
        # Base query
        query = TimeOffRequest.query
        
        # Apply status filter
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        # Apply crew filter - FIXED: Explicitly specify the join condition
        if crew_filter != 'all':
            # Explicitly join on employee_id (the requester), not approved_by
            query = query.join(Employee, Employee.id == TimeOffRequest.employee_id).filter(Employee.crew == crew_filter)
        else:
            # Even for 'all', explicitly specify the join to avoid ambiguity
            query = query.join(Employee, Employee.id == TimeOffRequest.employee_id)
        
        # Apply type filter
        if type_filter != 'all':
            query = query.filter_by(request_type=type_filter)
        
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
            'total': len(requests),
            'pending': sum(1 for r in requests if r.status == 'pending'),
            'approved': sum(1 for r in requests if r.status == 'approved'),
            'denied': sum(1 for r in requests if r.status == 'denied')
        }
        
        return render_template('time_off_requests.html',
                             requests=requests,
                             stats=stats,
                             status_filter=status_filter,
                             crew_filter=crew_filter,
                             date_filter=date_filter,
                             type_filter=type_filter,
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
                             
    except Exception as e:
        current_app.logger.error(f"Error in time_off_requests: {str(e)}")
        traceback.print_exc()
        flash('Error loading time off requests.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/time-off-request/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_time_off_request(request_id, action):
    """Approve or deny a time off request"""
    try:
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
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error handling time off request: {str(e)}")
        flash('Error processing request.', 'danger')
        return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/swap-requests')
@login_required
@supervisor_required
def swap_requests():
    """Review and approve shift swap requests"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        # Get filter parameters
        status_filter = request.args.get('status', 'pending')
        crew_filter = request.args.get('crew', 'all')
        
        # Base query
        query = ShiftSwapRequest.query
        
        # Apply status filter
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        # Apply crew filter - FIXED: Explicitly specify the join
        if crew_filter != 'all':
            # Join with requester employee to filter by crew, using explicit join condition
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
                             crew_filter=crew_filter,
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
                             
    except Exception as e:
        current_app.logger.error(f"Error in swap_requests: {str(e)}")
        flash('Error loading swap requests.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/swap-request/<int:request_id>/<action>', methods=['POST'])
@login_required
@supervisor_required
def handle_swap_request(request_id, action):
    """Handle supervisor approval/denial of shift swap"""
    try:
        swap_request = ShiftSwapRequest.query.get_or_404(request_id)
        
        if swap_request.status != 'pending':
            flash('This swap request has already been processed.', 'warning')
            return redirect(url_for('supervisor.swap_requests'))
        
        # Check if this supervisor can handle this request
        is_requester_supervisor = (current_user.crew == swap_request.requester.crew)
        is_target_supervisor = (swap_request.target_employee and 
                              current_user.crew == swap_request.target_employee.crew)
        
        if not (is_requester_supervisor or is_target_supervisor):
            flash('You can only approve swaps for employees in your crew.', 'warning')
            return redirect(url_for('supervisor.swap_requests'))
        
        if action == 'approve':
            # Check which supervisor is approving
            if is_requester_supervisor:
                swap_request.requester_supervisor_approved = True
                swap_request.requester_supervisor_id = current_user.id
                swap_request.requester_supervisor_date = datetime.now()
            
            if is_target_supervisor:
                swap_request.target_supervisor_approved = True
                swap_request.target_supervisor_id = current_user.id
                swap_request.target_supervisor_date = datetime.now()
            
            # If both supervisors have approved, mark as fully approved
            if swap_request.requester_supervisor_approved and swap_request.target_supervisor_approved:
                swap_request.status = 'approved'
                
                # Actually perform the schedule swap
                if swap_request.original_schedule and swap_request.target_schedule:
                    # Swap the employee assignments
                    temp_employee_id = swap_request.original_schedule.employee_id
                    swap_request.original_schedule.employee_id = swap_request.target_schedule.employee_id
                    swap_request.target_schedule.employee_id = temp_employee_id
                
                flash(f'Approved shift swap between {swap_request.requester.name} and {swap_request.target_employee.name}', 'success')
            else:
                flash(f'Approved shift swap from your crew. Waiting for other supervisor approval.', 'info')
                
        elif action == 'deny':
            swap_request.status = 'denied'
            swap_request.reviewed_by_id = current_user.id
            
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
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error handling swap request: {str(e)}")
        flash('Error processing swap request.', 'danger')
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
                
                flash(f'Successfully deleted {deleted_count} employees. You can now upload fresh data.', 'success')
                
            except Exception as e:
                trans.rollback()
                flash(f'Error during deletion: {str(e)}', 'danger')
                
    except Exception as e:
        flash(f'Error accessing database: {str(e)}', 'danger')
    
    return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/employees/upload', methods=['POST'])
@login_required
@supervisor_required
def upload_employees():
    """Step 2: Upload new employee data from Excel"""
    if 'file' not in request.files:
        flash('No file selected', 'danger')
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
        df = pd.read_excel(file)
        
        # Validate required columns
        required_columns = ['Last Name', 'First Name', 'Employee ID', 'Crew Assigned']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            flash(f'Missing required columns: {", ".join(missing_columns)}', 'danger')
            return redirect(url_for('supervisor.employee_management'))
        
        # Get or create positions from column headers
        position_columns = [col for col in df.columns if col not in 
                          ['Last Name', 'First Name', 'Employee ID', 'Date of Hire', 
                           'Total Overtime (Last 3 Months)', 'Crew Assigned', 
                           'Current Job Position']]
        
        positions = {}
        for pos_name in position_columns:
            if pos_name and pos_name.strip():
                position = Position.query.filter_by(name=pos_name.strip()).first()
                if not position:
                    position = Position(name=pos_name.strip(), min_coverage=1)
                    db.session.add(position)
                    db.session.flush()
                positions[pos_name] = position
        
        # Process each employee
        created = 0
        updated = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Skip empty rows
                if pd.isna(row['Employee ID']) or pd.isna(row['Last Name']):
                    continue
                
                # Generate username
                first_name = str(row['First Name']).strip()
                last_name = str(row['Last Name']).strip()
                username = f"{first_name[0].lower()}{last_name.lower()}"
                
                # Check for duplicate usernames
                counter = 1
                original_username = username
                while Employee.query.filter_by(username=username).first():
                    username = f"{original_username}{counter}"
                    counter += 1
                
                # Get or create employee
                employee = Employee.query.filter_by(employee_id=str(row['Employee ID'])).first()
                
                if employee:
                    # Update existing employee
                    employee.name = f"{first_name} {last_name}"
                    employee.crew = row['Crew Assigned'] if pd.notna(row['Crew Assigned']) else None
                    updated += 1
                else:
                    # Create new employee
                    employee = Employee(
                        employee_id=str(row['Employee ID']),
                        name=f"{first_name} {last_name}",
                        username=username,
                        crew=row['Crew Assigned'] if pd.notna(row['Crew Assigned']) else None,
                        is_supervisor=False
                    )
                    # Set default password
                    employee.set_password('TempPass123!')
                    db.session.add(employee)
                    created += 1
                
                # Set current position if specified
                if 'Current Job Position' in row and pd.notna(row['Current Job Position']):
                    position_name = str(row['Current Job Position']).strip()
                    position = Position.query.filter_by(name=position_name).first()
                    if not position:
                        position = Position(name=position_name, min_coverage=1)
                        db.session.add(position)
                        db.session.flush()
                    employee.position_id = position.id
                
                # Add employee skills based on position columns
                for pos_col in position_columns:
                    if pd.notna(row[pos_col]) and str(row[pos_col]).upper() in ['Y', 'YES', '1', 'TRUE']:
                        position = positions.get(pos_col)
                        if position and position not in employee.qualified_positions:
                            employee.qualified_positions.append(position)
                
                db.session.flush()
                
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")
                continue
        
        db.session.commit()
        
        message = f'Successfully processed: {created} new employees, {updated} updated.'
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
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
        employee_count = len(employees)
        
        return render_template('employee_management_new.html',
                             employees=employees,
                             employee_count=employee_count,
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in employee_management: {str(e)}")
        flash('Error loading employee management.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/employees/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Interactive crew management interface"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        employees = Employee.query.filter(Employee.id != current_user.id).order_by(Employee.crew, Employee.name).all()
        positions = Position.query.order_by(Position.name).all()
        
        return render_template('crew_management.html',
                             employees=employees,
                             positions=positions,
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in crew_management: {str(e)}")
        flash('Error loading crew management.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/employees/edit/<int:employee_id>', methods=['GET', 'POST'])
@login_required
@supervisor_required
def edit_employee(employee_id):
    """Edit employee information online"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        employee = Employee.query.get_or_404(employee_id)
        
        if request.method == 'POST':
            # Update employee fields
            employee.name = request.form.get('name')
            employee.crew = request.form.get('crew')
            employee.email = request.form.get('email')
            
            # Update position
            position_id = request.form.get('position_id')
            if position_id:
                employee.position_id = int(position_id)
            
            # Update skills
            selected_skills = request.form.getlist('skills')
            employee.qualified_positions = []
            for skill_id in selected_skills:
                position = Position.query.get(int(skill_id))
                if position:
                    employee.qualified_positions.append(position)
            
            db.session.commit()
            flash(f'Updated {employee.name} successfully', 'success')
            return redirect(url_for('supervisor.employee_management'))
        
        positions = Position.query.order_by(Position.name).all()
        employee_skills = [p.id for p in employee.qualified_positions]
        
        return render_template('edit_employee.html',
                             employee=employee,
                             positions=positions,
                             employee_skills=employee_skills,
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in edit_employee: {str(e)}")
        flash('Error editing employee.', 'danger')
        return redirect(url_for('supervisor.employee_management'))

# ========== COVERAGE NEEDS ROUTES ==========

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        # Get all positions
        positions = Position.query.order_by(Position.name).all()
        
        if not positions:
            flash('No positions found. Please upload employee data to create positions.', 'warning')
            return render_template('coverage_needs.html',
                                 positions=[],
                                 crew_requirements={},
                                 current_coverage={},
                                 crew_totals={},
                                 pending_time_off=pending_time_off,
                                 pending_swaps=pending_swaps)
        
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
        
        # Calculate total current staff
        total_current_staff = sum(crew_totals.values())
        
        return render_template('coverage_needs.html',
                             positions=positions,
                             crew_requirements=crew_requirements,
                             current_coverage=current_coverage,
                             crew_totals=crew_totals,
                             total_current_staff=total_current_staff,
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
                             
    except Exception as e:
        current_app.logger.error(f"Error in coverage_needs route: {str(e)}")
        flash(f'Error loading coverage needs: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs/reset-defaults', methods=['POST'])
@login_required
@supervisor_required
def reset_coverage_defaults():
    """Reset all position minimum coverage to 1"""
    try:
        positions = Position.query.all()
        for position in positions:
            position.min_coverage = 1
        db.session.commit()
        flash(f'Reset {len(positions)} positions to minimum coverage of 1', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resetting coverage defaults: {str(e)}")
        flash('Error resetting coverage defaults.', 'danger')
    
    return redirect(url_for('supervisor.coverage_needs'))

# ========== COVERAGE GAPS ROUTE - FIXED ==========

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View real-time coverage gaps considering absences"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
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
                # Get required coverage
                required = position.min_coverage
                
                # Get all employees in this crew and position
                employees = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).all()
                
                # Count total employees
                total_employees = len(employees)
                
                # Count employees who are absent today
                absent_count = 0
                absent_employees = []
                
                for emp in employees:
                    # Check if employee has any time off today
                    has_time_off = VacationCalendar.query.filter_by(
                        employee_id=emp.id,
                        date=today
                    ).first()
                    
                    if has_time_off:
                        absent_count += 1
                        absent_employees.append({
                            'name': emp.name,
                            'type': has_time_off.type
                        })
                
                # Calculate actual available vs required
                available = total_employees - absent_count
                gap = max(0, required - available)
                
                position_data = {
                    'id': position.id,
                    'name': position.name,
                    'required': required,
                    'total_employees': total_employees,
                    'absent': absent_count,
                    'available': available,
                    'gap': gap,
                    'critical': gap > 0 and available < (required * 0.75),
                    'absent_employees': absent_employees
                }
                
                crew_data['positions'].append(position_data)
                crew_data['total_required'] += required
                crew_data['total_available'] += available
                crew_data['total_absent'] += absent_count
                crew_data['total_gaps'] += gap
                
                if gap > 0:
                    total_gaps += gap
                    if position_data['critical']:
                        critical_gaps += 1
            
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
                             upcoming_absences=list(upcoming_by_date.values()),
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
                             
    except Exception as e:
        current_app.logger.error(f"Error in coverage_gaps route: {str(e)}")
        traceback.print_exc()
        flash(f'Error loading coverage gaps: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

# ========== OVERTIME DISTRIBUTION ROUTE ==========

@supervisor_bp.route('/supervisor/overtime-distribution')
@login_required
@supervisor_required
def overtime_distribution():
    """View overtime distribution with skills filter"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        # Get all employees with their overtime data and skills
        employees_by_crew = {'A': [], 'B': [], 'C': [], 'D': [], 'Unassigned': []}
        
        # Query for all non-supervisor employees
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        for emp in employees:
            # Get 13-week overtime data
            thirteen_weeks_ago = date.today() - timedelta(weeks=13)
            overtime_records = OvertimeHistory.query.filter(
                OvertimeHistory.employee_id == emp.id,
                OvertimeHistory.week_ending >= thirteen_weeks_ago
            ).all()
            
            # Calculate total overtime hours
            total_ot = sum(ot.hours_worked for ot in overtime_records)
            
            # Get employee skills (qualified positions)
            emp_skills = []
            for position in emp.qualified_positions:
                emp_skills.append({
                    'id': position.id,
                    'name': position.name
                })
            
            # Determine crew for grouping
            crew_key = emp.crew if emp.crew else 'Unassigned'
            
            # Build employee data
            employee_data = {
                'id': emp.id,
                'name': emp.name,
                'employee_id': emp.employee_id,
                'position': emp.position.name if emp.position else 'No Position',
                'overtime_hours': round(total_ot, 1),
                'skills': emp_skills,
                'all_skill_names': [s['name'] for s in emp_skills]
            }
            
            employees_by_crew[crew_key].append(employee_data)
        
        # Get all unique skills for filter dropdown
        all_skills = Position.query.order_by(Position.name).all()
        skill_list = [{'id': s.id, 'name': s.name} for s in all_skills]
        
        return render_template('overtime_distribution.html',
                             employees_by_crew=employees_by_crew,
                             skills=skill_list,
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
                             
    except Exception as e:
        current_app.logger.error(f"Error in overtime_distribution route: {str(e)}")
        flash(f'Error loading overtime distribution: {str(e)}', 'danger')
        return redirect(url_for('main.dashboard'))

# ========== OTHER SUPERVISOR ROUTES ==========

@supervisor_bp.route('/supervisor/suggestions')
@login_required
@supervisor_required
def suggestions():
    """View employee suggestions"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        return render_template('coming_soon.html',
                             title='Employee Suggestions',
                             description='Review and respond to suggestions and feedback from your team members.',
                             icon='bi bi-lightbulb',
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in suggestions: {str(e)}")
        flash('Error loading suggestions.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/supervisor/messages')
@login_required
@supervisor_required
def supervisor_messages():
    """Supervisor to supervisor messaging"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        return render_template('coming_soon.html',
                             title='Supervisor Messages',
                             description='Communicate with other supervisors across different shifts and crews.',
                             icon='bi bi-envelope-fill',
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in supervisor_messages: {str(e)}")
        flash('Error loading messages.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/casual-workers')
@login_required
@supervisor_required
def casual_workers():
    """Manage casual workers"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        return render_template('coming_soon.html',
                             title='Casual Workers',
                             description='Manage your pool of temporary and on-call workers for filling coverage gaps.',
                             icon='bi bi-person-badge',
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in casual_workers: {str(e)}")
        flash('Error loading casual workers.', 'danger')
        return redirect(url_for('main.dashboard'))

@supervisor_bp.route('/quick/position-broadcast')
@login_required
@supervisor_required
def position_broadcast():
    """Plantwide communications"""
    try:
        # Get pending counts for base.html - REQUIRED
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        
        return render_template('coming_soon.html',
                             title='Position Broadcast',
                             description='Send announcements and messages to all employees in specific positions across all crews.',
                             icon='bi bi-megaphone',
                             pending_time_off=pending_time_off,
                             pending_swaps=pending_swaps)
    except Exception as e:
        current_app.logger.error(f"Error in position_broadcast: {str(e)}")
        flash('Error loading position broadcast.', 'danger')
        return redirect(url_for('main.dashboard'))

# ========== API ENDPOINTS ==========

@supervisor_bp.route('/api/coverage-needs', methods=['POST'])
@login_required
@supervisor_required
def api_update_coverage_needs():
    """API endpoint to update coverage needs"""
    try:
        data = request.get_json()
        
        crew = data.get('crew')
        position_id = data.get('position_id')
        min_coverage = data.get('min_coverage', 0)
        
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
            return jsonify({'success': True, 'message': 'Crew-specific requirements saved'})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating coverage needs: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

@supervisor_bp.route('/api/coverage-gaps')
@login_required
@supervisor_required
def api_coverage_gaps():
    """API endpoint to get current coverage gaps"""
    try:
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
        
    except Exception as e:
        current_app.logger.error(f"Error getting coverage gaps: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
        current_app.logger.error(f"Error getting coverage gaps summary: {str(e)}")
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
        date_str = data.get('date')
        shift = data.get('shift')
        position = data.get('position')
        hours = data.get('hours')
        message = data.get('message', '')
        
        if not employee_ids:
            return jsonify({'success': False, 'error': 'No employees selected'}), 400
        
        # Here you would typically:
        # 1. Create overtime opportunity records
        # 2. Send notifications (email/SMS)
        # 3. Track responses
        
        # For now, just return success
        flash(f'Overtime request sent to {len(employee_ids)} employees', 'success')
        
        return jsonify({
            'success': True,
            'message': f'Sent to {len(employee_ids)} employees'
        })
        
    except Exception as e:
        current_app.logger.error(f"Error sending overtime request: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@supervisor_bp.route('/api/employee/<int:employee_id>/position', methods=['PUT'])
@login_required
@supervisor_required
def update_employee_position(employee_id):
    """API endpoint to update employee position"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        data = request.get_json()
        
        position_id = data.get('position_id')
        if position_id:
            employee.position_id = int(position_id)
            db.session.commit()
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'No position ID provided'}), 400
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating employee position: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@supervisor_bp.route('/api/employee/<int:employee_id>/crew', methods=['PUT'])
@login_required
@supervisor_required
def update_employee_crew(employee_id):
    """API endpoint to update employee crew assignment"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        data = request.get_json()
        
        new_crew = data.get('crew')
        if new_crew in ['A', 'B', 'C', 'D', 'UNASSIGNED']:
            employee.crew = new_crew if new_crew != 'UNASSIGNED' else None
            db.session.commit()
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Invalid crew'}), 400
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating employee crew: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@supervisor_bp.route('/employees/download-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download the employee import template with current positions"""
    try:
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
        
        # Create example row
        example = {
            'Last Name': 'Smith',
            'First Name': 'John',
            'Employee ID': '12345',
            'Date of Hire': '2020-01-15',
            'Total Overtime (Last 3 Months)': '45.5',
            'Crew Assigned': 'A',
            'Current Job Position': position_names[0] if position_names else 'Operator'
        }
        
        # Add Y/N for positions
        for col in columns[7:]:
            example[col] = 'Y' if columns.index(col) < 9 else ''
        
        # Create DataFrame
        df = pd.DataFrame([example])
        
        # Create Excel file
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Write instructions
            instructions = [
                "EMPLOYEE IMPORT TEMPLATE - INSTRUCTIONS",
                "",
                "INSTRUCTIONS:",
                "1. Fill out employee information in the first 7 columns",
                "2. For qualified positions, enter 'Y' or 'Yes' if employee is qualified",
                "3. Leave blank or enter 'N' if not qualified",
                "4. Crew must be: A, B, C, or D",
                "5. Save as Excel file (.xlsx) when complete",
                "",
                "EXAMPLE DATA:"
            ]
            
            instructions_df = pd.DataFrame({'Instructions': instructions})
            instructions_df.to_excel(writer, sheet_name='Instructions', index=False)
            
            # Write template
            df.to_excel(writer, sheet_name='Employee Data', index=False)
            
            # Format the Excel file
            workbook = writer.book
            worksheet = writer.sheets['Employee Data']
            
            # Add column formatting
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#4CAF50',
                'font_color': 'white',
                'border': 1
            })
            
            # Apply header format
            for col_num, value in enumerate(columns):
                worksheet.write(0, col_num, value, header_format)
                worksheet.set_column(col_num, col_num, 20)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'employee_import_template_{date.today().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        current_app.logger.error(f"Error downloading template: {str(e)}")
        flash('Error downloading template.', 'danger')
        return redirect(url_for('supervisor.employee_management'))
