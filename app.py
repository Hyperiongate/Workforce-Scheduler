from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, date
import os
from sqlalchemy import inspect, case, and_, or_
from models import db, Employee, Position, Skill, Schedule, Availability, TimeOffRequest, VacationCalendar, CoverageRequest, CasualWorker, CasualAssignment, ShiftSwapRequest, ScheduleSuggestion, CircadianProfile, SleepLog, SleepRecommendation, ShiftTransitionPlan, CoverageNotification, OvertimeOpportunity
from circadian_advisor import CircadianAdvisor
import json
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///workforce.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls', 'csv'}

# Create upload folder if it doesn't exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return Employee.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and employee.check_password(password):
            login_user(employee)
            flash(f'Welcome back, {employee.name}!', 'success')
            
            # Redirect based on role
            if employee.is_supervisor:
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('index'))

# ==================== DASHBOARD ROUTES ====================

@app.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get selected crew from query params (default to supervisor's crew or 'ALL')
    selected_crew = request.args.get('crew', current_user.crew or 'ALL')
    
    # Build query filters based on selected crew
    crew_filter = None
    if selected_crew != 'ALL':
        crew_filter = Employee.crew == selected_crew
    
    # Get crew statistics
    crew_stats = {}
    
    # Total employees in crew
    query = Employee.query
    if crew_filter is not None:
        query = query.filter(crew_filter)
    crew_stats['total_employees'] = query.count()
    
    # On duty now (based on current time and schedules)
    now = datetime.now()
    on_duty_query = Schedule.query.filter(
        Schedule.date == date.today(),
        Schedule.start_time <= now.time(),
        Schedule.end_time >= now.time()
    )
    if crew_filter is not None:
        on_duty_query = on_duty_query.join(Employee).filter(crew_filter)
    crew_stats['on_duty'] = on_duty_query.count()
    
    # Current shift type
    current_hour = now.hour
    if 6 <= current_hour < 14:
        crew_stats['current_shift'] = 'Day Shift'
    elif 14 <= current_hour < 22:
        crew_stats['current_shift'] = 'Evening Shift'
    else:
        crew_stats['current_shift'] = 'Night Shift'
    
    # Pending requests
    pending_requests_query = TimeOffRequest.query.filter_by(status='pending')
    if crew_filter is not None:
        pending_requests_query = pending_requests_query.join(Employee).filter(crew_filter)
    crew_stats['pending_requests'] = pending_requests_query.count()
    
    # Coverage gaps in next 7 days
    coverage_gaps = get_coverage_gaps(selected_crew, days_ahead=7)
    crew_stats['coverage_gaps'] = len(coverage_gaps)
    
    # Get pending items
    pending_time_off_count = TimeOffRequest.query.filter_by(status='pending').count()
    pending_swaps_count = ShiftSwapRequest.query.filter_by(status='pending').count()
    
    # Get recent requests for display
    recent_time_off_requests = TimeOffRequest.query.filter_by(
        status='pending'
    ).order_by(TimeOffRequest.submitted_date.desc()).limit(3).all()
    
    recent_swap_requests = ShiftSwapRequest.query.filter_by(
        status='pending'
    ).order_by(ShiftSwapRequest.created_at.desc()).limit(3).all()
    
    # Get today's schedule
    todays_schedule = Schedule.query.filter(
        Schedule.date == date.today()
    )
    if crew_filter is not None:
        todays_schedule = todays_schedule.join(Employee).filter(crew_filter)
    todays_schedule = todays_schedule.order_by(Schedule.start_time).all()
    
    # Get coverage needs
    coverage_needs = CoverageRequest.query.filter_by(
        status='open'
    ).count()
    
    return render_template('dashboard.html',
                         selected_crew=selected_crew,
                         crew_stats=crew_stats,
                         pending_time_off_count=pending_time_off_count,
                         pending_swaps_count=pending_swaps_count,
                         recent_time_off_requests=recent_time_off_requests,
                         recent_swap_requests=recent_swap_requests,
                         todays_schedule=todays_schedule,
                         coverage_needs=coverage_needs,
                         coverage_gaps=coverage_gaps[:3])  # Show first 3 gaps

@app.route('/employee-dashboard')
@login_required
def employee_dashboard():
    """Employee dashboard with schedules, requests, and sleep health info"""
    employee = Employee.query.get(current_user.id)
    
    # Get upcoming schedules
    schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= date.today()
    ).order_by(Schedule.date, Schedule.start_time).limit(7).all()
    
    # Calculate this week's hours
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    week_schedules = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).all()
    
    weekly_hours = sum(s.hours or 8 for s in week_schedules if not s.is_overtime)
    overtime_hours = sum(s.hours or 0 for s in week_schedules if s.is_overtime)
    
    # Get pending requests
    swap_requests = ShiftSwapRequest.query.filter(
        or_(
            ShiftSwapRequest.requester_id == employee.id,
            ShiftSwapRequest.target_employee_id == employee.id
        ),
        ShiftSwapRequest.status == 'pending'
    ).all()
    
    time_off_requests = TimeOffRequest.query.filter_by(
        employee_id=employee.id,
        status='pending'
    ).all()
    
    # Get sleep profile
    sleep_profile = CircadianProfile.query.filter_by(employee_id=employee.id).first()
    
    # Check for coverage notifications
    unread_notifications = CoverageNotification.query.filter(
        CoverageNotification.sent_to_employee_id == employee.id,
        CoverageNotification.read_at.is_(None)
    ).count()
    
    return render_template('employee_dashboard.html',
                         employee=employee,
                         schedules=schedules,
                         weekly_hours=weekly_hours,
                         overtime_hours=overtime_hours,
                         swap_requests=swap_requests,
                         time_off_requests=time_off_requests,
                         sleep_profile=sleep_profile,
                         unread_notifications=unread_notifications)

# ==================== CREW MANAGEMENT ROUTES ====================

@app.route('/supervisor/coverage-needs')
@login_required
def coverage_needs():
    """View all coverage needs and gaps"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get open coverage requests
    open_requests = CoverageRequest.query.filter_by(status='open').all()
    
    # Get coverage gaps for next 14 days
    coverage_gaps = get_coverage_gaps(crew='ALL', days_ahead=14)
    
    # Get available casual workers
    casual_workers = CasualWorker.query.filter_by(is_active=True).all()
    
    return render_template('coverage_needs.html',
                         open_requests=open_requests,
                         coverage_gaps=coverage_gaps,
                         casual_workers=casual_workers)

@app.route('/coverage/push/<int:request_id>', methods=['POST'])
@login_required
def push_coverage(request_id):
    """Push coverage request to employees"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    coverage = CoverageRequest.query.get_or_404(request_id)
    
    push_to = request.form.get('push_to')
    message = request.form.get('message', '')
    
    notifications_sent = 0
    
    if push_to == 'my_crew':
        # Push to supervisor's crew only
        employees = Employee.query.filter_by(
            crew=current_user.crew,
            is_supervisor=False
        ).all()
    elif push_to == 'off_crews':
        # Find crews that are off during this shift
        schedule_date = coverage.schedule.date
        off_crews = get_off_duty_crews(schedule_date, coverage.schedule.shift_type)
        employees = Employee.query.filter(
            Employee.crew.in_(off_crews),
            Employee.is_supervisor == False
        ).all()
    elif push_to == 'specific_crew':
        crew = request.form.get('specific_crew')
        employees = Employee.query.filter_by(
            crew=crew,
            is_supervisor=False
        ).all()
    elif push_to == 'supervisors':
        # Push to other supervisors
        employees = Employee.query.filter(
            Employee.is_supervisor == True,
            Employee.id != current_user.id
        ).all()
    else:
        employees = []
    
    # Filter by required skills if specified
    if coverage.position_required:
        position = Position.query.get(coverage.position_required)
        required_skills = [s.id for s in position.required_skills]
        
        qualified_employees = []
        for emp in employees:
            emp_skills = [s.id for s in emp.skills]
            if all(skill in emp_skills for skill in required_skills):
                qualified_employees.append(emp)
        employees = qualified_employees
    
    # Send notifications
    for employee in employees:
        # Check if employee is already working that day
        existing_schedule = Schedule.query.filter_by(
            employee_id=employee.id,
            date=coverage.schedule.date
        ).first()
        
        if not existing_schedule:  # Only notify if not already scheduled
            notification = CoverageNotification(
                coverage_request_id=coverage.id,
                sent_to_type='individual',
                sent_to_employee_id=employee.id,
                sent_by_id=current_user.id,
                message=message or f"Coverage needed for {coverage.schedule.date} {coverage.schedule.shift_type} shift"
            )
            db.session.add(notification)
            notifications_sent += 1
    
    # Update coverage request
    coverage.pushed_to_crews = push_to
    coverage.push_message = message
    
    db.session.commit()
    
    flash(f'Coverage request sent to {notifications_sent} qualified employees!', 'success')
    return redirect(url_for('coverage_needs'))

@app.route('/api/coverage-notifications')
@login_required
def get_coverage_notifications():
    """Get coverage notifications for current user"""
    notifications = CoverageNotification.query.filter_by(
        sent_to_employee_id=current_user.id,
        read_at=None
    ).order_by(CoverageNotification.sent_at.desc()).all()
    
    return jsonify({
        'notifications': [{
            'id': n.id,
            'message': n.message,
            'sent_at': n.sent_at.strftime('%Y-%m-%d %H:%M'),
            'coverage_id': n.coverage_request_id
        } for n in notifications]
    })

@app.route('/coverage/respond/<int:notification_id>', methods=['POST'])
@login_required
def respond_to_coverage(notification_id):
    """Respond to a coverage notification"""
    notification = CoverageNotification.query.get_or_404(notification_id)
    
    if notification.sent_to_employee_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    response = request.form.get('response')  # 'accept' or 'decline'
    
    notification.read_at = datetime.now()
    notification.responded_at = datetime.now()
    notification.response = response
    
    if response == 'accept':
        # Assign the coverage
        coverage = notification.coverage_request
        coverage.filled_by_id = current_user.id
        coverage.filled_at = datetime.now()
        coverage.status = 'filled'
        
        # Create schedule entry
        original_schedule = coverage.schedule
        new_schedule = Schedule(
            employee_id=current_user.id,
            date=original_schedule.date,
            shift_type=original_schedule.shift_type,
            start_time=original_schedule.start_time,
            end_time=original_schedule.end_time,
            position_id=original_schedule.position_id,
            hours=original_schedule.hours,
            is_overtime=True,  # Coverage is usually overtime
            crew=current_user.crew
        )
        db.session.add(new_schedule)
        
        flash('You have accepted the coverage shift!', 'success')
    else:
        flash('You have declined the coverage request.', 'info')
    
    db.session.commit()
    return redirect(url_for('employee_dashboard'))

# ==================== EXCEL IMPORT ROUTES ====================

@app.route('/import-employees', methods=['GET', 'POST'])
@login_required
def import_employees():
    """Import employees from Excel file"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            try:
                # Read Excel file
                df = pd.read_excel(file)
                
                # Expected columns: Name, Email, Phone, Hire Date, Crew, Position, Skills
                required_columns = ['Name', 'Email', 'Phone']
                
                if not all(col in df.columns for col in required_columns):
                    flash(f'Excel file must contain columns: {", ".join(required_columns)}', 'danger')
                    return redirect(request.url)
                
                imported_count = 0
                errors = []
                
                for idx, row in df.iterrows():
                    try:
                        # Check if employee already exists
                        existing = Employee.query.filter_by(email=row['Email']).first()
                        if existing:
                            errors.append(f"Row {idx+2}: Employee {row['Email']} already exists")
                            continue
                        
                        # Create new employee
                        employee = Employee(
                            name=row['Name'],
                            email=row['Email'],
                            phone=str(row.get('Phone', '')),
                            hire_date=pd.to_datetime(row.get('Hire Date', date.today())).date() if pd.notna(row.get('Hire Date')) else date.today(),
                            crew=str(row.get('Crew', 'A'))[:1],  # Ensure single character
                            is_supervisor=False,
                            vacation_days=10,
                            sick_days=5,
                            personal_days=3
                        )
                        
                        # Set default password
                        employee.set_password('password123')
                        
                        # Handle position
                        if 'Position' in row and pd.notna(row['Position']):
                            position = Position.query.filter_by(name=row['Position']).first()
                            if position:
                                employee.position_id = position.id
                        
                        # Handle skills (comma-separated)
                        if 'Skills' in row and pd.notna(row['Skills']):
                            skill_names = [s.strip() for s in str(row['Skills']).split(',')]
                            for skill_name in skill_names:
                                skill = Skill.query.filter_by(name=skill_name).first()
                                if not skill:
                                    # Create new skill if it doesn't exist
                                    skill = Skill(name=skill_name, category='General')
                                    db.session.add(skill)
                                employee.skills.append(skill)
                        
                        db.session.add(employee)
                        imported_count += 1
                        
                    except Exception as e:
                        errors.append(f"Row {idx+2}: {str(e)}")
                
                db.session.commit()
                
                flash(f'Successfully imported {imported_count} employees!', 'success')
                if errors:
                    flash(f'Errors encountered: {"; ".join(errors[:5])}{"..." if len(errors) > 5 else ""}', 'warning')
                
                return redirect(url_for('dashboard'))
                
            except Exception as e:
                flash(f'Error reading file: {str(e)}', 'danger')
                return redirect(request.url)
    
    # GET request - show upload form
    return render_template('import_employees.html')

@app.route('/export-template')
@login_required
def export_template():
    """Download Excel template for employee import"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Create template DataFrame
    template_data = {
        'Name': ['John Doe', 'Jane Smith'],
        'Email': ['john.doe@example.com', 'jane.smith@example.com'],
        'Phone': ['555-0123', '555-0124'],
        'Hire Date': [date.today(), date.today()],
        'Crew': ['A', 'B'],
        'Position': ['Nurse', 'Security Officer'],
        'Skills': ['CPR Certified, Emergency Response', 'Security, First Aid']
    }
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Employees', index=False)
        
        # Add instructions sheet
        instructions = pd.DataFrame({
            'Instructions': [
                'Fill in employee data in the Employees sheet',
                'Required fields: Name, Email, Phone',
                'Optional fields: Hire Date, Crew (A/B/C/D), Position, Skills',
                'Skills should be comma-separated',
                'All employees will be created with password: password123',
                'Employees will need to change their password on first login'
            ]
        })
        instructions.to_excel(writer, sheet_name='Instructions', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='employee_import_template.xlsx'
    )

# ==================== OVERTIME DISTRIBUTION ROUTES ====================

@app.route('/supervisor/overtime-distribution')
@login_required
def overtime_distribution():
    """Smart overtime distribution interface"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get upcoming overtime opportunities
    overtime_opportunities = get_overtime_opportunities()
    
    # Get eligible employees for overtime
    eligible_employees = get_overtime_eligible_employees()
    
    return render_template('overtime_distribution.html',
                         opportunities=overtime_opportunities,
                         eligible_employees=eligible_employees)

@app.route('/overtime/assign', methods=['POST'])
@login_required
def assign_overtime():
    """Assign overtime to qualified employees"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    opportunity_id = request.form.get('opportunity_id')
    employee_ids = request.form.getlist('employee_ids')
    
    opportunity = OvertimeOpportunity.query.get_or_404(opportunity_id)
    
    assignments_made = 0
    
    for emp_id in employee_ids:
        employee = Employee.query.get(emp_id)
        
        # Verify employee is eligible
        if not is_eligible_for_overtime(employee, opportunity):
            continue
        
        # Create overtime schedule
        schedule = Schedule(
            employee_id=employee.id,
            date=opportunity.date,
            shift_type=opportunity.shift_type,
            start_time=opportunity.start_time,
            end_time=opportunity.end_time,
            position_id=opportunity.position_id,
            hours=opportunity.hours,
            is_overtime=True,
            crew=employee.crew
        )
        db.session.add(schedule)
        assignments_made += 1
    
    opportunity.status = 'assigned'
    db.session.commit()
    
    flash(f'Overtime assigned to {assignments_made} employees!', 'success')
    return redirect(url_for('overtime_distribution'))

# ==================== ENHANCED SHIFT SWAP ROUTES ====================

@app.route('/employee/swap-request', methods=['POST'])
@login_required
def create_swap_request():
    """Create a shift swap request"""
    schedule_id = request.form.get('schedule_id')
    reason = request.form.get('reason', '')
    
    schedule = Schedule.query.get_or_404(schedule_id)
    
    if schedule.employee_id != current_user.id:
        flash('You can only request swaps for your own shifts.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Create swap request
    swap_request = ShiftSwapRequest(
        requester_id=current_user.id,
        original_schedule_id=schedule_id,
        reason=reason,
        status='pending'
    )
    
    db.session.add(swap_request)
    db.session.commit()
    
    flash('Shift swap request submitted! Both supervisors will need to approve.', 'success')
    return redirect(url_for('employee_dashboard'))

@app.route('/supervisor/swap-requests')
@login_required
def swap_requests():
    """View and manage shift swap requests"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    # Get pending swap requests that need this supervisor's approval
    pending_swaps = ShiftSwapRequest.query.filter(
        ShiftSwapRequest.status == 'pending',
        or_(
            # Swaps where this supervisor oversees the requester
            and_(
                ShiftSwapRequest.requester_supervisor_approved.is_(None),
                Employee.query.filter_by(id=ShiftSwapRequest.requester_id).first().crew == current_user.crew
            ),
            # Swaps where this supervisor oversees the target
            and_(
                ShiftSwapRequest.target_supervisor_approved.is_(None),
                ShiftSwapRequest.target_employee_id.isnot(None),
                Employee.query.filter_by(id=ShiftSwapRequest.target_employee_id).first().crew == current_user.crew
            )
        )
    ).all()
    
    recent_swaps = ShiftSwapRequest.query.filter(
        ShiftSwapRequest.status.in_(['approved', 'denied'])
    ).order_by(ShiftSwapRequest.requester_supervisor_date.desc()).limit(10).all()
    
    return render_template('swap_requests.html',
                         pending_swaps=pending_swaps,
                         recent_swaps=recent_swaps)

@app.route('/swap-request/<int:swap_id>/<action>', methods=['POST'])
@login_required
def handle_swap_request(swap_id, action):
    """Handle swap request with dual supervisor approval"""
    if not current_user.is_supervisor:
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    swap = ShiftSwapRequest.query.get_or_404(swap_id)
    
    # Determine which approval this supervisor is giving
    requester = Employee.query.get(swap.requester_id)
    target = Employee.query.get(swap.target_employee_id) if swap.target_employee_id else None
    
    is_requester_supervisor = requester.crew == current_user.crew
    is_target_supervisor = target and target.crew == current_user.crew
    
    if action == 'approve':
        if is_requester_supervisor and not swap.requester_supervisor_approved:
            swap.requester_supervisor_approved = True
            swap.requester_supervisor_id = current_user.id
            swap.requester_supervisor_date = datetime.now()
            flash('Approved for requester!', 'success')
        
        if is_target_supervisor and not swap.target_supervisor_approved:
            swap.target_supervisor_approved = True
            swap.target_supervisor_id = current_user.id
            swap.target_supervisor_date = datetime.now()
            flash('Approved for target employee!', 'success')
        
        # Check if both supervisors have approved
        if swap.requester_supervisor_approved and (not target or swap.target_supervisor_approved):
            # Execute the swap
            original_schedule = Schedule.query.get(swap.original_schedule_id)
            
            if swap.target_schedule_id:
                target_schedule = Schedule.query.get(swap.target_schedule_id)
                # Swap employee assignments
                original_employee_id = original_schedule.employee_id
                original_schedule.employee_id = target_schedule.employee_id
                target_schedule.employee_id = original_employee_id
            
            swap.status = 'approved'
            flash('Shift swap fully approved and executed!', 'success')
    
    elif action == 'deny':
        swap.status = 'denied'
        if is_requester_supervisor:
            swap.requester_supervisor_approved = False
            swap.requester_supervisor_id = current_user.id
            swap.requester_supervisor_date = datetime.now()
        if is_target_supervisor:
            swap.target_supervisor_approved = False
            swap.target_supervisor_id = current_user.id
            swap.target_supervisor_date = datetime.now()
        
        flash('Shift swap denied.', 'info')
    
    db.session.commit()
    return redirect(url_for('swap_requests'))

# ==================== SCHEDULE MANAGEMENT ROUTES ====================

@app.route('/schedule/create', methods=['GET', 'POST'])
@login_required
def create_schedule():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        schedule_type = request.form.get('schedule_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
        
        if schedule_type == '4_crew_rotation':
            rotation_pattern = request.form.get('rotation_pattern')
            return create_4_crew_schedule(start_date, end_date, rotation_pattern)
        else:
            # Standard schedule creation
            shift_pattern = request.form.get('shift_pattern')
            return create_standard_schedule(start_date, end_date, shift_pattern)
    
    employees = Employee.query.filter_by(is_supervisor=False).all()
    positions = Position.query.all()
    
    # Group employees by crew for display
    employees_by_crew = {}
    for emp in employees:
        crew = emp.crew or 'Unassigned'
        if crew not in employees_by_crew:
            employees_by_crew[crew] = []
        employees_by_crew[crew].append(emp)
    
    return render_template('schedule_input.html', 
                         employees=employees,
                         positions=positions,
                         employees_by_crew=employees_by_crew)

def create_4_crew_schedule(start_date, end_date, rotation_pattern):
    """Create schedules for 4-crew rotation patterns"""
    crews = {'A': [], 'B': [], 'C': [], 'D': []}
    
    # Get employees by crew
    for crew in crews:
        crews[crew] = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
    
    # Check if we have employees in all crews
    empty_crews = [crew for crew, employees in crews.items() if not employees]
    if empty_crews:
        flash(f'No employees assigned to crew(s): {", ".join(empty_crews)}. Please assign employees to crews first.', 'danger')
        return redirect(url_for('create_schedule'))
    
    # Define rotation patterns
    if rotation_pattern == '2-2-3':
        # 2-2-3 (Pitman) schedule
        cycle_days = 14
        pattern = {
            'A': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Day shifts
            'B': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Day shifts (opposite A)
            'C': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Night shifts
            'D': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Night shifts (opposite C)
        }
        shift_times = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    elif rotation_pattern == '4-4':
        # 4 on, 4 off pattern
        cycle_days = 16
        pattern = {
            'A': [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0],
            'B': [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1],
            'C': [1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0],
            'D': [0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1],
        }
        shift_times = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    else:  # DuPont
        # DuPont schedule
        cycle_days = 28
        # This is a simplified version - actual DuPont is more complex
        pattern = {
            'A': [1,1,1,1,0,0,0,1,1,1,0,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0],
            'B': [0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0],
            'C': [1,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0,0,1,1,1,1,0,0,0,1,1],
            'D': [1,1,0,0,0,0,1,1,1,1,0,0,0,1,1,1,0,0,0,0,1,1,1,1,0,0,0,1],
        }
        shift_times = {
            'A': ('day', 7, 19), 'B': ('day', 7, 19),
            'C': ('night', 19, 7), 'D': ('night', 19, 7)
        }
    
    # Create schedules
    current_date = start_date
    schedules_created = 0
    
    while current_date <= end_date:
        day_in_cycle = (current_date - start_date).days % cycle_days
        
        for crew_name, crew_employees in crews.items():
            if pattern[crew_name][day_in_cycle] == 1:  # Working day
                shift_type, start_hour, end_hour = shift_times[crew_name]
                
                for employee in crew_employees:
                    # Check for time off
                    has_time_off = VacationCalendar.query.filter_by(
                        employee_id=employee.id,
                        date=current_date.date()
                    ).first()
                    
                    if not has_time_off:
                        start_time = current_date.replace(hour=start_hour, minute=0, second=0)
                        end_time = current_date.replace(hour=end_hour, minute=0, second=0)
                        
                        # Handle overnight shifts
                        if end_hour < start_hour:
                            end_time += timedelta(days=1)
                        
                        # Calculate hours
                        hours = (end_time - start_time).total_seconds() / 3600
                        
                        schedule = Schedule(
                            employee_id=employee.id,
                            date=current_date.date(),
                            shift_type=shift_type,
                            start_time=start_time.time(),
                            end_time=end_time.time(),
                            position_id=employee.position_id,
                            hours=hours,
                            crew=crew_name
                        )
                        db.session.add(schedule)
                        schedules_created += 1
                        
                        # Update circadian profile
                        update_circadian_profile_on_schedule_change(employee.id, shift_type)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules using {rotation_pattern} pattern!', 'success')
    return redirect(url_for('view_schedules'))

def create_standard_schedule(start_date, end_date, shift_pattern):
    """Create standard schedules"""
    employees = Employee.query.filter_by(is_supervisor=False).all()
    schedules_created = 0
    
    # Define shift times based on pattern
    shift_times = {
        'standard': [('day', 9, 17)],
        'retail': [('day', 10, 18), ('evening', 14, 22)],
        '2_shift': [('day', 7, 15), ('evening', 15, 23)],
        '3_shift': [('day', 7, 15), ('evening', 15, 23), ('night', 23, 7)]
    }
    
    shifts = shift_times.get(shift_pattern, [('day', 9, 17)])
    
    current_date = start_date
    while current_date <= end_date:
        # Skip weekends for standard pattern
        if shift_pattern == 'standard' and current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        
        # Assign employees to shifts
        for i, employee in enumerate(employees):
            # Check for time off
            has_time_off = VacationCalendar.query.filter_by(
                employee_id=employee.id,
                date=current_date.date()
            ).first()
            
            if not has_time_off:
                # Rotate through available shifts
                shift_type, start_hour, end_hour = shifts[i % len(shifts)]
                
                start_time = current_date.replace(hour=start_hour, minute=0, second=0)
                end_time = current_date.replace(hour=end_hour, minute=0, second=0)
                
                # Handle overnight shifts
                if end_hour < start_hour:
                    end_time += timedelta(days=1)
                
                # Calculate hours
                hours = (end_time - start_time).total_seconds() / 3600
                
                schedule = Schedule(
                    employee_id=employee.id,
                    date=current_date.date(),
                    shift_type=shift_type,
                    start_time=start_time.time(),
                    end_time=end_time.time(),
                    position_id=employee.position_id,
                    hours=hours,
                    crew=employee.crew
                )
                db.session.add(schedule)
                schedules_created += 1
                
                # Update circadian profile
                update_circadian_profile_on_schedule_change(employee.id, shift_type)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    flash(f'Successfully created {schedules_created} schedules!', 'success')
    return redirect(url_for('view_schedules'))

@app.route('/schedule/view')
@login_required
def view_schedules():
    """View schedules with crew filtering"""
    # Get crew filter
    crew = request.args.get('crew', 'ALL')
    
    # Get date range
    start_date = request.args.get('start_date', date.today())
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    end_date = request.args.get('end_date', start_date + timedelta(days=13))
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Build query
    query = Schedule.query.filter(
        Schedule.date >= start_date,
        Schedule.date <= end_date
    )
    
    if crew != 'ALL':
        query = query.filter(Schedule.crew == crew)
    
    schedules = query.order_by(Schedule.date, Schedule.shift_type, Schedule.start_time).all()
    
    # Group schedules by date and shift
    schedule_grid = {}
    for schedule in schedules:
        date_key = schedule.date
        if date_key not in schedule_grid:
            schedule_grid[date_key] = {'day': [], 'evening': [], 'night': []}
        
        shift_type = schedule.shift_type or 'day'
        schedule_grid[date_key][shift_type].append(schedule)
    
    return render_template('crew_schedule.html',
                         schedule_grid=schedule_grid,
                         start_date=start_date,
                         end_date=end_date,
                         selected_crew=crew)

# ==================== HELPER FUNCTIONS ====================

def get_coverage_gaps(crew='ALL', days_ahead=7):
    """Identify coverage gaps in the schedule"""
    gaps = []
    
    # Check each day in the range
    for day_offset in range(days_ahead):
        check_date = date.today() + timedelta(days=day_offset)
        
        # Get minimum coverage requirements by position
        positions = Position.query.all()
        
        for position in positions:
            for shift_type in ['day', 'evening', 'night']:
                # Count scheduled employees
                query = Schedule.query.filter(
                    Schedule.date == check_date,
                    Schedule.shift_type == shift_type,
                    Schedule.position_id == position.id
                )
                
                if crew != 'ALL':
                    query = query.filter(Schedule.crew == crew)
                
                scheduled_count = query.count()
                
                # Check if we meet minimum coverage
                if scheduled_count < position.min_coverage:
                    gap = {
                        'id': len(gaps) + 1,
                        'date': check_date,
                        'shift': shift_type,
                        'position': position.name,
                        'required': position.min_coverage,
                        'scheduled': scheduled_count,
                        'gap': position.min_coverage - scheduled_count,
                        'reason': 'Understaffed'
                    }
                    gaps.append(gap)
    
    return gaps

def get_off_duty_crews(schedule_date, shift_type):
    """Determine which crews are off duty for a given date/shift"""
    # This is simplified - in reality, you'd check the actual rotation pattern
    # For now, assume A&C work days, B&D work nights
    if shift_type == 'day':
        return ['B', 'D']  # Night crews are off during day shifts
    elif shift_type == 'night':
        return ['A', 'C']  # Day crews are off during night shifts
    else:
        return ['A', 'B', 'C', 'D']  # All crews for coverage

def get_overtime_opportunities():
    """Get upcoming shifts that need overtime coverage"""
    opportunities = []
    
    # Look for gaps in next 14 days
    gaps = get_coverage_gaps(crew='ALL', days_ahead=14)
    
    for gap in gaps:
        opportunity = OvertimeOpportunity(
            id=gap['id'],
            date=gap['date'],
            shift_type=gap['shift'],
            position_id=Position.query.filter_by(name=gap['position']).first().id,
            hours=8,  # Standard shift
            positions_needed=gap['gap'],
            status='open'
        )
        opportunities.append(opportunity)
    
    return opportunities

def get_overtime_eligible_employees():
    """Get employees eligible for overtime"""
    # Get all non-supervisor employees
    employees = Employee.query.filter_by(is_supervisor=False).all()
    
    eligible = []
    
    for employee in employees:
        # Calculate current week hours
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_schedules = Schedule.query.filter(
            Schedule.employee_id == employee.id,
            Schedule.date >= week_start,
            Schedule.date < week_start + timedelta(days=7)
        ).all()
        
        weekly_hours = sum(s.hours or 8 for s in week_schedules)
        
        # Eligible if under 60 hours
        if weekly_hours < 60:
            employee.current_weekly_hours = weekly_hours
            employee.available_ot_hours = 60 - weekly_hours
            eligible.append(employee)
    
    # Sort by least hours first (fairness)
    eligible.sort(key=lambda e: e.current_weekly_hours)
    
    return eligible

def is_eligible_for_overtime(employee, opportunity):
    """Check if employee is eligible for specific overtime opportunity"""
    # Check skills match
    if opportunity.position_id:
        position = Position.query.get(opportunity.position_id)
        if not employee.can_work_position(position):
            return False
    
    # Check not already scheduled
    existing = Schedule.query.filter_by(
        employee_id=employee.id,
        date=opportunity.date
    ).first()
    if existing:
        return False
    
    # Check 24-hour rule (no back-to-back shifts)
    day_before = opportunity.date - timedelta(days=1)
    prev_shift = Schedule.query.filter(
        Schedule.employee_id == employee.id,
        Schedule.date == day_before,
        Schedule.shift_type == 'night'
    ).first()
    
    if prev_shift and opportunity.shift_type == 'day':
        return False  # Would violate 24-hour rule
    
    return True

def update_circadian_profile_on_schedule_change(employee_id, new_shift_type):
    """Helper function to update circadian profile when schedule changes"""
    profile = CircadianProfile.query.filter_by(employee_id=employee_id).first()
    if profile:
        if profile.current_shift_type != new_shift_type:
            profile.last_shift_change = datetime.now()
            profile.current_shift_type = new_shift_type
            profile.days_on_current_pattern = 0
            profile.circadian_adaptation_score = 0.0
        else:
            profile.days_on_current_pattern += 1
            # Update adaptation score
            advisor = CircadianAdvisor(Employee.query.get(employee_id), profile)
            phase_info = advisor.calculate_circadian_phase()
            profile.circadian_adaptation_score = phase_info['adaptation']
        
        profile.updated_at = datetime.now()
        db.session.commit()

# ==================== API ROUTES ====================

@app.route('/api/available-swaps/<int:schedule_id>')
@login_required
def get_available_swaps(schedule_id):
    """Get available shifts for swapping"""
    my_schedule = Schedule.query.get_or_404(schedule_id)
    
    # Find compatible shifts (same position, different employee, within 7 days)
    available_shifts = Schedule.query.filter(
        Schedule.employee_id != current_user.id,
        Schedule.position_id == my_schedule.position_id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=14)
    ).all()
    
    shifts_data = []
    for shift in available_shifts:
        # Check if employees have matching skills
        my_skills = set(s.id for s in current_user.skills)
        their_skills = set(s.id for s in shift.employee.skills)
        skills_match = my_skills == their_skills
        
        shifts_data.append({
            'id': shift.id,
            'employee_name': shift.employee.name,
            'date': shift.date.strftime('%a, %b %d'),
            'time': f"{shift.start_time.strftime('%I:%M %p')} - {shift.end_time.strftime('%I:%M %p')}",
            'position': shift.position.name if shift.position else 'TBD',
            'skills_match': skills_match
        })
    
    return jsonify({'shifts': shifts_data})

@app.route('/api/absence/report', methods=['POST'])
@login_required
def report_absence():
    """Report an employee absence and create coverage request"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    employee_name = data.get('employee')
    
    # Find today's schedule for this employee
    employee = Employee.query.filter_by(name=employee_name).first()
    if not employee:
        return jsonify({'success': False, 'message': 'Employee not found'})
    
    today_schedule = Schedule.query.filter_by(
        employee_id=employee.id,
        date=date.today()
    ).first()
    
    if not today_schedule:
        return jsonify({'success': False, 'message': 'No schedule found for today'})
    
    # Update schedule status
    today_schedule.status = 'absent'
    
    # Create coverage request
    coverage = CoverageRequest(
        schedule_id=today_schedule.id,
        requester_id=current_user.id,
        reason='Employee absence',
        status='open',
        position_required=today_schedule.position_id
    )
    
    db.session.add(coverage)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Absence reported for {employee_name}. Coverage request created.'
    })

# Continue with remaining routes...
