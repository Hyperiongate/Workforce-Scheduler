# blueprints/supervisor.py
"""
Supervisor blueprint with all required routes and fixed session handling
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file, render_template_string
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory, PositionCoverage, VacationCalendar
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_, inspect
from sqlalchemy.orm import joinedload, selectinload
from functools import wraps
import traceback
import pandas as pd
import os

supervisor_bp = Blueprint('supervisor', __name__)

def supervisor_required(f):
    """Decorator to require supervisor access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('main.employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Supervisor dashboard with proper session handling"""
    try:
        # Get current user ID before any session operations
        try:
            # Access ID in a safe way
            user_id = current_user.get_id()
            if not user_id:
                flash('Session error. Please log in again.', 'danger')
                return redirect(url_for('auth.login'))
        except:
            flash('Session error. Please log in again.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Initialize context with safe defaults
        context = {
            'pending_time_off': 0,
            'pending_swaps': 0,
            'total_employees': 0,
            'coverage_gaps': 0,
            'employees_missing_ot': 0,
            'high_ot_employees': [],
            'recent_time_off': [],
            'employees_on_leave_today': 0,
            'today': date.today(),
            'now': datetime.now()
        }
        
        # Get user info safely
        try:
            user = db.session.query(Employee).filter_by(id=int(user_id)).first()
            if user:
                context['current_user'] = user
                context['user_name'] = user.name
            else:
                context['current_user'] = current_user
                context['user_name'] = 'Supervisor'
        except:
            context['current_user'] = current_user
            context['user_name'] = 'Supervisor'
        
        # Get statistics with error handling
        try:
            context['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
        except Exception as e:
            current_app.logger.error(f"Error getting pending time off: {e}")
            db.session.rollback()
        
        try:
            context['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
        except Exception as e:
            current_app.logger.error(f"Error getting pending swaps: {e}")
            db.session.rollback()
        
        try:
            context['total_employees'] = Employee.query.filter_by(is_supervisor=False).count()
        except Exception as e:
            current_app.logger.error(f"Error counting employees: {e}")
            db.session.rollback()
        
        # Try to render a template
        templates = [
            'supervisor_dashboard.html',
            'dashboard_classic.html',
            'supervisor_dashboard_simple.html',
            'basic_dashboard.html'
        ]
        
        for template in templates:
            try:
                return render_template(template, **context)
            except:
                continue
        
        # If no template works, use inline HTML
        return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Supervisor Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container-fluid">
            <span class="navbar-brand">Workforce Scheduler</span>
            <a href="{{ url_for('auth.logout') }}" class="btn btn-outline-light btn-sm">Logout</a>
        </div>
    </nav>
    
    <div class="container mt-4">
        <h1>Supervisor Dashboard</h1>
        <p>Welcome, {{ user_name }}!</p>
        
        <div class="row">
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Pending Time Off</h5>
                        <p class="display-4">{{ pending_time_off }}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Pending Swaps</h5>
                        <p class="display-4">{{ pending_swaps }}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Total Employees</h5>
                        <p class="display-4">{{ total_employees }}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Coverage Gaps</h5>
                        <p class="display-4">{{ coverage_gaps }}</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="mt-4">
            <h2>Quick Links</h2>
            <div class="list-group">
                <a href="{{ url_for('supervisor.time_off_requests') }}" class="list-group-item list-group-item-action">
                    Review Time Off Requests
                </a>
                <a href="{{ url_for('supervisor.swap_requests') }}" class="list-group-item list-group-item-action">
                    Review Shift Swaps
                </a>
                <a href="{{ url_for('schedule.view_schedule') if 'schedule' in current_app.blueprints else '#' }}" class="list-group-item list-group-item-action">
                    View Schedule
                </a>
                <a href="{{ url_for('employee_import.upload_employees') if 'employee_import' in current_app.blueprints else '#' }}" class="list-group-item list-group-item-action">
                    Upload Employee Data
                </a>
            </div>
        </div>
    </div>
</body>
</html>
        ''', **context)
        
    except Exception as e:
        current_app.logger.error(f"Critical error in supervisor dashboard: {e}")
        current_app.logger.error(traceback.format_exc())
        db.session.rollback()
        flash('An error occurred loading the dashboard.', 'danger')
        return redirect(url_for('home'))  # Use the root route which exists

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests"""
    try:
        db.session.rollback()  # Clear any stale transactions
        
        status_filter = request.args.get('status', 'all')
        crew_filter = request.args.get('crew', 'all')
        
        query = TimeOffRequest.query.options(joinedload(TimeOffRequest.employee))
        
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        if crew_filter != 'all':
            query = query.join(Employee).filter(Employee.crew == crew_filter)
        
        requests = query.order_by(TimeOffRequest.created_at.desc()).all()
        
        stats = {
            'pending_count': TimeOffRequest.query.filter_by(status='pending').count(),
            'approved_this_week': TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.created_at >= datetime.now() - timedelta(days=7)
            ).count(),
            'total_days_requested': 0
        }
        
        return render_template('time_off_requests.html', 
                             requests=requests,
                             stats=stats,
                             status_filter=status_filter,
                             crew_filter=crew_filter)
    
    except Exception as e:
        current_app.logger.error(f"Error in time_off_requests: {e}")
        db.session.rollback()
        flash('Error loading time off requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>')
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request"""
    try:
        time_off = TimeOffRequest.query.get_or_404(request_id)
        
        if time_off.status != 'pending':
            flash('This request has already been processed.', 'warning')
            return redirect(url_for('supervisor.time_off_requests'))
        
        time_off.status = 'approved'
        time_off.approved_by_id = current_user.id
        time_off.approved_date = datetime.now()
        
        # Create vacation calendar entries
        current_date = time_off.start_date
        while current_date <= time_off.end_date:
            existing = VacationCalendar.query.filter_by(
                employee_id=time_off.employee_id,
                date=current_date
            ).first()
            
            if not existing:
                vacation_entry = VacationCalendar(
                    employee_id=time_off.employee_id,
                    date=current_date,
                    request_id=time_off.id,
                    type=time_off.request_type,
                    status='approved'
                )
                db.session.add(vacation_entry)
            
            current_date += timedelta(days=1)
        
        db.session.commit()
        flash(f'Time off request for {time_off.employee.name} has been approved.', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving time off: {e}")
        flash('Error approving request.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/deny-time-off/<int:request_id>', methods=['POST'])
@login_required
@supervisor_required
def deny_time_off(request_id):
    """Deny a time off request"""
    try:
        time_off = TimeOffRequest.query.get_or_404(request_id)
        
        if time_off.status != 'pending':
            flash('This request has already been processed.', 'warning')
            return redirect(url_for('supervisor.time_off_requests'))
        
        time_off.status = 'denied'
        time_off.approved_by_id = current_user.id
        time_off.approved_date = datetime.now()
        
        db.session.commit()
        flash(f'Time off request for {time_off.employee.name} has been denied.', 'info')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error denying time off: {e}")
        flash('Error denying request.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/swap-requests')
@login_required
@supervisor_required
def swap_requests():
    """View and manage shift swap requests"""
    try:
        db.session.rollback()
        
        swaps = ShiftSwapRequest.query.order_by(
            ShiftSwapRequest.created_at.desc()
        ).all()
        
        stats = {
            'pending_count': ShiftSwapRequest.query.filter_by(status='pending').count(),
            'approved_this_week': ShiftSwapRequest.query.filter(
                ShiftSwapRequest.status == 'approved',
                ShiftSwapRequest.created_at >= datetime.now() - timedelta(days=7)
            ).count()
        }
        
        return render_template('swap_requests.html', swaps=swaps, stats=stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in swap_requests: {e}")
        db.session.rollback()
        flash('Error loading swap requests.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View coverage gaps"""
    try:
        db.session.rollback()
        
        start_date = request.args.get('start_date', date.today())
        end_date = request.args.get('end_date', date.today() + timedelta(days=7))
        
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        positions = Position.query.all()
        position_requirements = {p.id: getattr(p, 'min_coverage', 2) for p in positions}
        
        schedules = Schedule.query.filter(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        ).all()
        
        gaps = []
        current_date = start_date
        
        while current_date <= end_date:
            for position in positions:
                scheduled = len([s for s in schedules 
                               if s.date == current_date and s.position_id == position.id])
                required = position_requirements.get(position.id, 0)
                
                if scheduled < required:
                    gaps.append({
                        'date': current_date,
                        'position': position.name,
                        'scheduled': scheduled,
                        'required': required,
                        'gap': required - scheduled
                    })
            
            current_date += timedelta(days=1)
        
        return render_template('coverage_gaps.html',
                             gaps=gaps,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        current_app.logger.error(f"Error in coverage_gaps: {e}")
        db.session.rollback()
        flash('Error loading coverage gaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs"""
    try:
        db.session.rollback()
        
        positions = Position.query.order_by(Position.name).all()
        
        coverage_data = []
        for position in positions:
            coverage_data.append({
                'position': position,
                'department': getattr(position, 'department', 'Unknown'),
                'min_coverage': getattr(position, 'min_coverage', 0),
                'crew_coverage': {'A': 0, 'B': 0, 'C': 0, 'D': 0}
            })
        
        staffing = {}
        for crew in ['A', 'B', 'C', 'D']:
            crew_employees = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
            staffing[crew] = {
                'total': len(crew_employees),
                'by_position': {}
            }
            
            for emp in crew_employees:
                if emp.position:
                    pos_name = emp.position.name
                    staffing[crew]['by_position'][pos_name] = staffing[crew]['by_position'].get(pos_name, 0) + 1
        
        return render_template('coverage_needs.html',
                             coverage_data=coverage_data,
                             staffing=staffing)
    
    except Exception as e:
        current_app.logger.error(f"Error in coverage_needs: {e}")
        db.session.rollback()
        flash('Error loading coverage needs.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/update-coverage', methods=['POST'])
@login_required
@supervisor_required
def update_coverage():
    """Update position coverage requirements"""
    try:
        position_id = request.form.get('position_id')
        position = Position.query.get_or_404(position_id)
        
        min_coverage = request.form.get('min_coverage', type=int)
        if min_coverage is not None and hasattr(position, 'min_coverage'):
            position.min_coverage = min_coverage
        
        db.session.commit()
        flash(f'Coverage requirements updated for {position.name}', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating coverage: {e}")
        flash('Error updating coverage requirements.', 'danger')
    
    return redirect(url_for('supervisor.coverage_needs'))

@supervisor_bp.route('/supervisor/overtime-distribution')
@login_required
@supervisor_required
def overtime_distribution():
    """View overtime distribution"""
    try:
        db.session.rollback()
        
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        ot_data = []
        for emp in employees:
            try:
                thirteen_weeks_ago = date.today() - timedelta(weeks=13)
                ot_records = OvertimeHistory.query.filter(
                    OvertimeHistory.employee_id == emp.id,
                    OvertimeHistory.week_start_date >= thirteen_weeks_ago
                ).all()
                
                total_ot = sum(record.overtime_hours for record in ot_records)
                avg_ot = total_ot / 13 if ot_records else 0
                
                current_week_start = date.today() - timedelta(days=date.today().weekday())
                current_ot = OvertimeHistory.query.filter_by(
                    employee_id=emp.id,
                    week_start_date=current_week_start
                ).first()
                
                ot_data.append({
                    'employee': emp,
                    'total_13_weeks': total_ot,
                    'average_weekly': round(avg_ot, 1),
                    'current_week': current_ot.overtime_hours if current_ot else 0,
                    'weeks_with_data': len(ot_records)
                })
            except:
                ot_data.append({
                    'employee': emp,
                    'total_13_weeks': 0,
                    'average_weekly': 0,
                    'current_week': 0,
                    'weeks_with_data': 0
                })
        
        ot_data.sort(key=lambda x: x['total_13_weeks'])
        
        return render_template('overtime_distribution.html', 
                             overtime_data=ot_data)
    
    except Exception as e:
        current_app.logger.error(f"Error in overtime_distribution: {e}")
        db.session.rollback()
        flash('Error loading overtime distribution.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display vacation calendar"""
    try:
        db.session.rollback()
        
        month = request.args.get('month', type=int, default=date.today().month)
        year = request.args.get('year', type=int, default=date.today().year)
        
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)
        
        vacations = VacationCalendar.query.filter(
            VacationCalendar.date >= start_date,
            VacationCalendar.date <= end_date
        ).all()
        
        crew_vacations = {'A': [], 'B': [], 'C': [], 'D': []}
        for vacation in vacations:
            if vacation.employee and vacation.employee.crew in crew_vacations:
                crew_vacations[vacation.employee.crew].append(vacation)
        
        return render_template('vacation_calendar.html',
                             month=month,
                             year=year,
                             crew_vacations=crew_vacations,
                             start_date=start_date,
                             end_date=end_date)
    
    except Exception as e:
        current_app.logger.error(f"Error in vacation_calendar: {e}")
        db.session.rollback()
        flash('Error loading vacation calendar.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/api/vacation-calendar')
@login_required
@supervisor_required
def api_vacation_calendar():
    """API endpoint for vacation calendar data"""
    try:
        db.session.rollback()
        
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        
        if start_date:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        else:
            start_date = date.today().replace(day=1)
            
        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        vacations = VacationCalendar.query.filter(
            VacationCalendar.date >= start_date,
            VacationCalendar.date <= end_date
        ).options(joinedload(VacationCalendar.employee)).all()
        
        events = []
        for vacation in vacations:
            if vacation.employee:
                color = {
                    'A': '#28a745',
                    'B': '#17a2b8', 
                    'C': '#ffc107',
                    'D': '#dc3545'
                }.get(vacation.employee.crew, '#6c757d')
                
                events.append({
                    'id': vacation.id,
                    'title': f"{vacation.employee.name} ({vacation.type})",
                    'start': vacation.date.isoformat(),
                    'end': (vacation.date + timedelta(days=1)).isoformat(),
                    'color': color,
                    'crew': vacation.employee.crew,
                    'employee_id': vacation.employee_id,
                    'type': vacation.type
                })
        
        return jsonify(events)
        
    except Exception as e:
        current_app.logger.error(f"Error in api_vacation_calendar: {e}")
        db.session.rollback()
        return jsonify({'error': 'Failed to load calendar data'}), 500

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page"""
    try:
        db.session.rollback()
        
        employees = Employee.query.order_by(Employee.crew, Employee.name).all()
        positions = Position.query.order_by(Position.name).all()
        
        crew_stats = {}
        for crew in ['A', 'B', 'C', 'D']:
            crew_employees = [e for e in employees if e.crew == crew]
            crew_stats[crew] = {
                'total': len(crew_employees),
                'supervisors': len([e for e in crew_employees if e.is_supervisor])
            }
        
        return render_template('employee_management.html',
                             employees=employees,
                             positions=positions,
                             crew_stats=crew_stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in employee_management: {e}")
        db.session.rollback()
        flash('Error loading employee management.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/crew-management') 
@login_required
@supervisor_required
def crew_management():
    """Crew management interface"""
    try:
        db.session.rollback()
        
        crews = {}
        for crew_name in ['A', 'B', 'C', 'D', 'Unassigned']:
            if crew_name == 'Unassigned':
                crew_employees = Employee.query.filter(
                    or_(Employee.crew == None, Employee.crew == '')
                ).order_by(Employee.name).all()
            else:
                crew_employees = Employee.query.filter_by(crew=crew_name).order_by(Employee.name).all()
            
            crews[crew_name] = crew_employees
        
        positions = Position.query.order_by(Position.name).all()
        
        crew_stats = {}
        for crew_name in ['A', 'B', 'C', 'D']:
            crew_stats[crew_name] = {
                'total': len(crews.get(crew_name, [])),
                'positions': {},
                'supervisor_count': len([e for e in crews.get(crew_name, []) if e.is_supervisor])
            }
            
            for emp in crews.get(crew_name, []):
                if emp.position:
                    pos_name = emp.position.name
                    crew_stats[crew_name]['positions'][pos_name] = \
                        crew_stats[crew_name]['positions'].get(pos_name, 0) + 1
        
        return render_template('crew_management.html',
                             crews=crews,
                             positions=positions,
                             crew_stats=crew_stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in crew_management: {e}")
        db.session.rollback()
        flash('Error loading crew management.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/update-crew', methods=['POST'])
@login_required
@supervisor_required
def update_crew():
    """Update employee crew assignment"""
    try:
        employee_id = request.form.get('employee_id')
        new_crew = request.form.get('new_crew')
        
        employee = Employee.query.get_or_404(employee_id)
        old_crew = employee.crew
        
        employee.crew = new_crew if new_crew != 'Unassigned' else None
        db.session.commit()
        
        flash(f'{employee.name} moved from Crew {old_crew or "Unassigned"} to Crew {new_crew}', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating crew: {e}")
        flash('Error updating crew assignment.', 'danger')
    
    return redirect(url_for('supervisor.crew_management'))

# Template download routes
@supervisor_bp.route('/supervisor/download-employee-template')
@login_required
@supervisor_required
def download_employee_template():
    """Download employee upload template"""
    try:
        db.session.rollback()
        
        from utils.excel_templates_generator import generate_employee_template
        
        filepath = generate_employee_template()
        return send_file(filepath, as_attachment=True, 
                        download_name='employee_upload_template.xlsx')
                        
    except Exception as e:
        current_app.logger.error(f"Error generating template: {e}")
        flash('Error generating template.', 'danger')
        return redirect(url_for('supervisor.employee_management'))

@supervisor_bp.route('/supervisor/download-current-employees')
@login_required
@supervisor_required
def download_current_employees():
    """Export current employee list"""
    try:
        db.session.rollback()
        
        employees = Employee.query.filter_by(is_supervisor=False).all()
        
        data = []
        for emp in employees:
            data.append({
                'Employee ID': emp.employee_id,
                'First Name': emp.name.split()[0] if emp.name else '',
                'Last Name': emp.name.split()[-1] if emp.name and len(emp.name.split()) > 1 else '',
                'Email': emp.email,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Department': getattr(emp.position, 'department', '') if emp.position else ''
            })
        
        df = pd.DataFrame(data)
        
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'upload_files')
        os.makedirs(upload_folder, exist_ok=True)
        
        filepath = os.path.join(upload_folder, 
                               f'employees_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
        df.to_excel(filepath, index=False)
        
        return send_file(filepath, as_attachment=True)
        
    except Exception as e:
        current_app.logger.error(f"Error exporting employees: {e}")
        db.session.rollback()
        flash('Error exporting employee data.', 'danger')
        return redirect(url_for('supervisor.employee_management'))

# API endpoints
@supervisor_bp.route('/api/dashboard-stats')
@login_required
@supervisor_required
def api_dashboard_stats():
    """API endpoint for real-time dashboard statistics"""
    try:
        db.session.rollback()
        
        stats = {
            'pending_time_off': 0,
            'pending_swaps': 0,
            'coverage_gaps': 0,
            'total_employees': 0,
            'employees_on_leave': 0,
            'last_updated': datetime.now().strftime('%H:%M:%S')
        }
        
        try:
            stats['pending_time_off'] = TimeOffRequest.query.filter_by(status='pending').count()
        except:
            pass
            
        try:
            stats['pending_swaps'] = ShiftSwapRequest.query.filter_by(status='pending').count()
        except:
            pass
            
        try:
            stats['total_employees'] = Employee.query.filter_by(is_supervisor=False).count()
        except:
            pass
        
        try:
            today = date.today()
            scheduled = Schedule.query.filter_by(date=today).count()
            stats['coverage_gaps'] = max(0, 20 - scheduled)
        except:
            pass
        
        try:
            today = date.today()
            stats['employees_on_leave'] = TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= today,
                TimeOffRequest.end_date >= today
            ).count()
        except:
            pass
        
        return jsonify(stats)
    
    except Exception as e:
        current_app.logger.error(f"Error in api_dashboard_stats: {e}")
        return jsonify({'error': 'Failed to load statistics'}), 500
