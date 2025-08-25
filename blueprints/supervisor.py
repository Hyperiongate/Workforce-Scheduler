# blueprints/supervisor.py - COMPLETE FILE WITH DEMO DATA INTEGRATION
"""
Supervisor blueprint with complete error handling and database migration support
Includes: Predictive Staffing, Communications Hub, and Enhanced Request Management
UPDATED WITH DEMO DATA SERVICE
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_file, render_template_string
from flask_login import login_required, current_user
from models import db, Employee, TimeOffRequest, ShiftSwapRequest, Schedule, Position, OvertimeHistory, SupervisorMessage, VacationCalendar
from datetime import date, datetime, timedelta
from sqlalchemy import func, and_, or_, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from functools import wraps
from utils.demo_data import demo_service
import pandas as pd
import os
import io
import logging
import random

# Set up logging
logger = logging.getLogger(__name__)

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

def safe_count_query(model, **filters):
    """Safely count records even if columns don't exist"""
    try:
        query = model.query
        for key, value in filters.items():
            if hasattr(model, key):
                query = query.filter_by(**{key: value})
        return query.count()
    except (ProgrammingError, OperationalError) as e:
        logger.error(f"Database error in count query for {model.__name__}: {e}")
        db.session.rollback()
        return 0

@supervisor_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def dashboard():
    """Enhanced supervisor dashboard with demo data"""
    # Get demo statistics
    try:
        stats = demo_service.get_dashboard_summary_stats()
        
        context = {
            'user_name': current_user.name,
            **stats  # Spread all the demo stats
        }
        
        # Add aliases for backward compatibility
        context['pending_time_off_count'] = context['pending_time_off']
        context['pending_swaps_count'] = context['pending_swaps']
        
    except Exception as e:
        logger.error(f"Error getting demo stats: {e}")
        # Fallback to safe defaults
        context = {
            'user_name': current_user.name,
            'pending_time_off': 0,
            'pending_swaps': 0,
            'total_employees': 0,
            'coverage_gaps': 0,
            'today_scheduled': 0,
            'today_on_leave': 0,
            'critical_maintenance': 0,
            'pending_time_off_count': 0,
            'pending_swaps_count': 0
        }
    
    # Try to render the enhanced dashboard template
    try:
        return render_template('supervisor_dashboard_enhanced.html', **context)
    except Exception as e:
        logger.debug(f"Enhanced template not found or failed, using standard: {e}")
        try:
            return render_template('supervisor_dashboard.html', **context)
        except Exception as e2:
            logger.error(f"Both templates failed: {e2}")
            flash('Dashboard templates have an error. Please check template files.', 'danger')
            return redirect(url_for('main.index'))

# ==========================================
# TIME OFF MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/time-off-requests')
@login_required
@supervisor_required
def time_off_requests():
    """View and manage time off requests - FIXED"""
    pending_requests = []
    
    try:
        # Try to get requests with safe query using only basic columns
        pending_requests = TimeOffRequest.query.filter_by(status='pending').all()
    except (ProgrammingError, OperationalError) as e:
        logger.error(f"Database error in time off requests: {e}")
        db.session.rollback()
        
        # Try raw SQL as fallback with minimal columns
        try:
            result = db.session.execute(
                text("""
                    SELECT id, employee_id, start_date, end_date, status, 
                           COALESCE(reason, '') as reason
                    FROM time_off_request
                    WHERE status = 'pending'
                    ORDER BY start_date
                """)
            )
            # Convert to objects manually
            for row in result:
                # Create a simple object to hold the data
                class SimpleRequest:
                    pass
                req = SimpleRequest()
                req.id = row[0]
                req.employee_id = row[1]
                req.start_date = row[2]
                req.end_date = row[3]
                req.status = row[4]
                req.reason = row[5] or ''
                # Try to get employee
                try:
                    req.employee = Employee.query.get(req.employee_id)
                except:
                    req.employee = None
                pending_requests.append(req)
        except Exception as e2:
            logger.error(f"Failed to get requests even with raw SQL: {e2}")
            flash('Error loading time off requests. Database may need updating.', 'danger')
    
    return render_template('time_off_requests.html', requests=pending_requests)

@supervisor_bp.route('/supervisor/approve-time-off/<int:request_id>')
@login_required
@supervisor_required
def approve_time_off(request_id):
    """Approve a time off request - FIXED"""
    try:
        # Use raw SQL to update with only existing columns
        db.session.execute(
            text("""
                UPDATE time_off_request 
                SET status = 'approved'
                WHERE id = :request_id
            """),
            {'request_id': request_id}
        )
        db.session.commit()
        flash('Time off request approved!', 'success')
    except Exception as e:
        logger.error(f"Error approving time off: {e}")
        db.session.rollback()
        flash('Error approving request. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

@supervisor_bp.route('/supervisor/deny-time-off/<int:request_id>')
@login_required
@supervisor_required
def deny_time_off(request_id):
    """Deny a time off request - FIXED"""
    try:
        db.session.execute(
            text("""
                UPDATE time_off_request 
                SET status = 'denied'
                WHERE id = :request_id
            """),
            {'request_id': request_id}
        )
        db.session.commit()
        flash('Time off request denied.', 'info')
    except Exception as e:
        logger.error(f"Error denying time off: {e}")
        db.session.rollback()
        flash('Error denying request. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.time_off_requests'))

# ==========================================
# SHIFT SWAP MANAGEMENT - FIXED
# ==========================================

@supervisor_bp.route('/supervisor/shift-swaps')
@login_required
@supervisor_required
def shift_swaps():
    """View and manage shift swap requests - FIXED"""
    pending_swaps = []
    
    try:
        # Try basic query first
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').all()
    except (ProgrammingError, OperationalError) as e:
        logger.error(f"Database error in shift swaps: {e}")
        db.session.rollback()
        
        # Try simpler raw SQL query with only columns that exist
        try:
            result = db.session.execute(
                text("""
                    SELECT id, requester_id, status, 
                           COALESCE(reason, '') as reason, 
                           created_at
                    FROM shift_swap_request
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                """)
            )
            for row in result:
                class SimpleSwap:
                    pass
                swap = SimpleSwap()
                swap.id = row[0]
                swap.requester_id = row[1]
                swap.status = row[2]
                swap.reason = row[3] or ''
                swap.created_at = row[4]
                try:
                    swap.requester = Employee.query.get(swap.requester_id)
                except:
                    swap.requester = None
                pending_swaps.append(swap)
        except Exception as e2:
            logger.error(f"Failed to get swaps even with raw SQL: {e2}")
            flash('Error loading shift swaps. Database may need updating.', 'danger')
    
    return render_template('shift_swaps.html', swaps=pending_swaps)

@supervisor_bp.route('/supervisor/approve-swap/<int:swap_id>')
@login_required
@supervisor_required
def approve_swap(swap_id):
    """Approve a shift swap request - FIXED"""
    try:
        db.session.execute(
            text("""
                UPDATE shift_swap_request 
                SET status = 'approved'
                WHERE id = :swap_id
            """),
            {'swap_id': swap_id}
        )
        db.session.commit()
        flash('Shift swap approved!', 'success')
    except Exception as e:
        logger.error(f"Error approving swap: {e}")
        db.session.rollback()
        flash('Error approving swap. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.shift_swaps'))

@supervisor_bp.route('/supervisor/deny-swap/<int:swap_id>')
@login_required
@supervisor_required
def deny_swap(swap_id):
    """Deny a shift swap request - FIXED"""
    try:
        db.session.execute(
            text("""
                UPDATE shift_swap_request 
                SET status = 'denied'
                WHERE id = :swap_id
            """),
            {'swap_id': swap_id}
        )
        db.session.commit()
        flash('Shift swap denied.', 'info')
    except Exception as e:
        logger.error(f"Error denying swap: {e}")
        db.session.rollback()
        flash('Error denying swap. Please try again.', 'danger')
    
    return redirect(url_for('supervisor.shift_swaps'))

# ==========================================
# EMPLOYEE MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/employee-management')
@login_required
@supervisor_required
def employee_management():
    """Employee management page"""
    try:
        employees = Employee.query.filter_by(is_supervisor=False).all()
        return render_template('employee_management.html', employees=employees)
    except Exception as e:
        logger.error(f"Error in employee management: {e}")
        flash('Error loading employee data.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Crew management page"""
    try:
        crews = {}
        for crew in ['A', 'B', 'C', 'D']:
            crews[crew] = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
        
        unassigned = Employee.query.filter(
            or_(Employee.crew == None, Employee.crew == ''),
            Employee.is_supervisor == False
        ).all()
        
        return render_template('crew_management.html', crews=crews, unassigned=unassigned)
    except Exception as e:
        logger.error(f"Error in crew management: {e}")
        flash('Error loading crew data.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# SCHEDULE MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display vacation calendar"""
    try:
        today = date.today()
        start_of_month = date(today.year, today.month, 1)
        
        if today.month == 12:
            end_of_month = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end_of_month = date(today.year, today.month + 1, 1) - timedelta(days=1)
        
        # Try to get time off requests with safe query
        time_off_requests = []
        try:
            time_off_requests = TimeOffRequest.query.filter(
                TimeOffRequest.status == 'approved',
                TimeOffRequest.start_date <= end_of_month,
                TimeOffRequest.end_date >= start_of_month
            ).all()
        except Exception as e:
            logger.error(f"Error getting time off requests: {e}")
            db.session.rollback()
        
        return render_template('vacation_calendar.html',
                             time_off_requests=time_off_requests,
                             current_month=today)
    except Exception as e:
        logger.error(f"Error in vacation calendar: {e}")
        flash('Error loading vacation calendar.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-gaps')
@login_required
@supervisor_required
def coverage_gaps():
    """View coverage gaps with demo data"""
    try:
        gaps = demo_service.get_coverage_gaps_data()
        return render_template('coverage_gaps.html', gaps=gaps)
    except Exception as e:
        logger.error(f"Error in coverage gaps: {e}")
        flash('Error loading coverage gaps.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/coverage-needs')
@login_required
@supervisor_required
def coverage_needs():
    """View and manage coverage needs - COMPLETE FIXED VERSION"""
    try:
        # Get all positions ordered by name
        positions = Position.query.order_by(Position.name).all()
        
        # Initialize data structures for template
        crew_totals = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        current_coverage = {
            'A': {},
            'B': {},
            'C': {},
            'D': {}
        }
        
        # Count total employees by crew (excluding supervisors)
        for crew in ['A', 'B', 'C', 'D']:
            crew_totals[crew] = Employee.query.filter_by(
                crew=crew, 
                is_supervisor=False
            ).count()
        
        # Initialize position coverage for all crews
        for position in positions:
            # Set default min_coverage if not set
            if not hasattr(position, 'min_coverage') or position.min_coverage is None:
                position.min_coverage = 1
            
            # Count employees by position and crew
            for crew in ['A', 'B', 'C', 'D']:
                count = Employee.query.filter_by(
                    crew=crew,
                    position_id=position.id,
                    is_supervisor=False
                ).count()
                current_coverage[crew][position.id] = count
        
        # Calculate total current staff
        total_current_staff = sum(crew_totals.values())
        
        # Render the template with all required variables
        return render_template('coverage_needs.html',
                             positions=positions,
                             crew_totals=crew_totals,
                             current_coverage=current_coverage,
                             total_current_staff=total_current_staff)
                             
    except Exception as e:
        logger.error(f"Error in coverage needs: {e}")
        logger.error(f"Error details: {str(e)}")
        flash('Error loading coverage needs. Make sure employee data is uploaded first.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# OVERTIME MANAGEMENT
# ==========================================

@supervisor_bp.route('/supervisor/overtime-distribution')
@login_required
@supervisor_required
def overtime_distribution():
    """View overtime distribution report with demo data"""
    try:
        overtime_data = demo_service.get_overtime_distribution_data()
        return render_template('overtime_distribution.html', overtime_data=overtime_data)
    except Exception as e:
        logger.error(f"Error in overtime distribution: {e}")
        flash('Error loading overtime distribution.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# NEW DASHBOARD PAGES WITH DEMO DATA
# ==========================================

@supervisor_bp.route('/supervisor/today-schedule')
@login_required
@supervisor_required
def today_schedule():
    """View today's schedule overview with demo data"""
    try:
        schedule_data = demo_service.get_today_schedule_data()
        
        # Convert demo data to template format
        crew_schedules = {}
        for crew, data in schedule_data['crews'].items():
            # Create fake employee objects for template
            scheduled_employees = []
            on_leave_employees = []
            
            for name in data['scheduled_employees']:
                class FakeEmployee:
                    def __init__(self, name):
                        self.name = name
                        self.id = random.randint(1000, 9999)
                scheduled_employees.append(FakeEmployee(name))
            
            for name in data['on_leave_employees']:
                on_leave_employees.append(FakeEmployee(name))
            
            crew_schedules[crew] = {
                'total': data['total'],
                'scheduled': scheduled_employees,
                'on_leave': on_leave_employees
            }
        
        return render_template('today_schedule.html', 
                             crew_schedules=crew_schedules,
                             today=schedule_data['date'])
    except Exception as e:
        logger.error(f"Error in today's schedule: {e}")
        flash('Error loading schedule', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/crew-status')
@login_required
@supervisor_required
def crew_status():
    """Real-time crew status overview with demo data"""
    try:
        crew_data = demo_service.get_crew_status_data()
        return render_template('crew_status.html', crew_data=crew_data)
        
    except Exception as e:
        logger.error(f"Error in crew status: {e}")
        flash('Error loading crew status', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@supervisor_bp.route('/supervisor/all-requests')
@login_required
@supervisor_required
def all_requests():
    """View all request history"""
    try:
        # Get all time off requests with safe query
        time_off = []
        try:
            time_off = TimeOffRequest.query.order_by(
                TimeOffRequest.created_at.desc()
            ).limit(100).all()
        except:
            logger.error("Error getting time off requests")
        
        # Get all shift swap requests with safe query
        shift_swaps = []
        try:
            shift_swaps = ShiftSwapRequest.query.order_by(
                ShiftSwapRequest.created_at.desc()
            ).limit(100).all()
        except:
            logger.error("Error getting shift swap requests")
        
        return render_template('all_requests.html',
                             time_off_requests=time_off,
                             shift_swaps=shift_swaps)
        
    except Exception as e:
        logger.error(f"Error in all requests: {e}")
        flash('Error loading requests', 'danger')
        return redirect(url_for('supervisor.dashboard'))

# ==========================================
# DEMO API ENDPOINTS - REPLACE EXISTING
# ==========================================

@supervisor_bp.route('/api/predictive-staffing', methods=['POST'])
@login_required
@supervisor_required
def api_predictive_staffing():
    """API endpoint for predictive staffing analysis - DEMO VERSION"""
    try:
        data = request.get_json()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({'error': 'Start and end dates required'}), 400
        
        # Use demo service
        result = demo_service.get_predictive_staffing_data(start_date, end_date)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in predictive staffing API: {e}")
        return jsonify({'error': str(e)}), 500

@supervisor_bp.route('/api/communication-counts')
@login_required
@supervisor_required
def api_communication_counts():
    """Get unread message counts for communications hub - DEMO VERSION"""
    try:
        counts = demo_service.get_communication_counts()
        return jsonify({
            'success': True,
            **counts
        })
        
    except Exception as e:
        logger.error(f"Error getting communication counts: {e}")
        return jsonify({
            'success': True,
            'supervisor_to_supervisor': 0,
            'employee_to_supervisor': 0,
            'plantwide_recent': 0
        })

@supervisor_bp.route('/api/supervisor-messages')
@login_required
@supervisor_required
def api_get_supervisor_messages():
    """Get messages between supervisors - DEMO VERSION"""
    try:
        messages = demo_service.get_supervisor_messages()
        unread_count = sum(1 for m in messages if m['unread'])
        
        return jsonify({
            'success': True,
            'messages': messages,
            'unread_count': unread_count
        })
        
    except Exception as e:
        logger.error(f"Error getting supervisor messages: {e}")
        return jsonify({
            'success': True,
            'messages': [],
            'unread_count': 0
        })

@supervisor_bp.route('/api/employee-messages')
@login_required
@supervisor_required
def api_get_employee_messages():
    """Get messages from employees to supervisor - DEMO VERSION"""
    try:
        messages = demo_service.get_employee_messages()
        unread_count = sum(1 for m in messages if m['unread'])
        
        return jsonify({
            'success': True,
            'messages': messages,
            'unread_count': unread_count
        })
        
    except Exception as e:
        logger.error(f"Error getting employee messages: {e}")
        return jsonify({
            'success': True,
            'messages': [],
            'unread_count': 0
        })

@supervisor_bp.route('/api/send-supervisor-message', methods=['POST'])
@login_required
@supervisor_required
def api_send_supervisor_message():
    """Send message to another supervisor - DEMO VERSION"""
    try:
        data = request.get_json()
        recipient_id = data.get('recipient_id')
        subject = data.get('subject')
        message = data.get('message')
        
        if not all([recipient_id, subject, message]):
            return jsonify({'error': 'All fields required'}), 400
        
        # Use demo service
        result = demo_service.send_demo_message(
            'supervisor',
            recipient_id=recipient_id,
            subject=subject,
            message=message
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error sending supervisor message: {e}")
        return jsonify({'error': 'Failed to send message'}), 500

@supervisor_bp.route('/api/send-plantwide-message', methods=['POST'])
@login_required
@supervisor_required
def api_send_plantwide_message():
    """Send announcement to all employees - DEMO VERSION"""
    try:
        data = request.get_json()
        subject = data.get('subject')
        message = data.get('message')
        priority = data.get('priority', 'normal')
        
        if not all([subject, message]):
            return jsonify({'error': 'Subject and message required'}), 400
        
        # Simulate sending to all employees (demo)
        recipient_count = random.randint(95, 105)  # Simulated employee count
        
        result = demo_service.send_demo_message(
            'plantwide',
            subject=subject,
            message=message,
            priority=priority,
            recipients=recipient_count
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error sending plantwide message: {e}")
        return jsonify({'error': 'Failed to send announcement'}), 500

# ==========================================
# API ENDPOINTS (ORIGINAL)
# ==========================================

@supervisor_bp.route('/api/coverage-needs', methods=['POST'])
@login_required
@supervisor_required
def api_update_coverage_needs():
    """API endpoint to update coverage requirements"""
    try:
        data = request.get_json()
        crew = data.get('crew')
        position_id = data.get('position_id')
        min_coverage = data.get('min_coverage', 0)
        
        # Log the update
        logger.info(f"Coverage update: Crew {crew}, Position {position_id}, Min Coverage {min_coverage}")
        
        # In a real implementation, you would save this to a CoverageRequirement table
        # For now, just return success
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating coverage needs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# DATABASE MIGRATION CHECK
# ==========================================

@supervisor_bp.route('/supervisor/check-database')
@login_required
@supervisor_required
def check_database():
    """Check database schema and show migration needs - FIXED"""
    issues = []
    
    # Check TimeOffRequest columns
    try:
        db.session.execute(text("SELECT status FROM time_off_request LIMIT 1"))
    except Exception as e:
        issues.append(f"time_off_request table issue: {str(e)}")
        db.session.rollback()
    
    # Check ShiftSwapRequest columns  
    try:
        db.session.execute(text("SELECT status FROM shift_swap_request LIMIT 1"))
    except Exception as e:
        issues.append(f"shift_swap_request table issue: {str(e)}")
        db.session.rollback()
    
    # Check Position table
    try:
        db.session.execute(text("SELECT name FROM position LIMIT 1"))
    except Exception as e:
        issues.append(f"position table issue: {str(e)}")
        db.session.rollback()
    
    return jsonify({
        'database_ok': len(issues) == 0,
        'issues': issues
    })

# ==========================================
# ERROR HANDLERS
# ==========================================

@supervisor_bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@supervisor_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==========================================
# UTILITY FUNCTIONS - FIXED
# ==========================================

def get_pending_time_off_count():
    """Get pending time off count with FIXED error handling"""
    try:
        # Try basic ORM query first
        result = TimeOffRequest.query.filter_by(status='pending').count()
        return result or 0
    except Exception as e:
        logger.error(f"ORM query failed for time off count: {e}")
        db.session.rollback()
        
        # Fall back to raw SQL with minimal columns
        try:
            result = db.session.execute(
                text("SELECT COUNT(*) FROM time_off_request WHERE status = 'pending'")
            ).scalar()
            return result or 0
        except Exception as e2:
            logger.error(f"Raw SQL also failed for time off count: {e2}")
            db.session.rollback()
            return 0

def get_pending_swaps_count():
    """Get pending swaps count with FIXED error handling"""
    try:
        # Try basic ORM query first
        result = ShiftSwapRequest.query.filter_by(status='pending').count()
        return result or 0
    except Exception as e:
        logger.error(f"ORM query failed for swaps count: {e}")
        db.session.rollback()
        
        # Fall back to raw SQL with minimal columns
        try:
            result = db.session.execute(
                text("SELECT COUNT(*) FROM shift_swap_request WHERE status = 'pending'")
            ).scalar()
            return result or 0
        except Exception as e2:
            logger.error(f"Raw SQL also failed for swaps count: {e2}")
            db.session.rollback()
            return 0

def get_employees_on_leave_today():
    """Get count of employees on leave today with FIXED error handling"""
    try:
        today = date.today()
        result = TimeOffRequest.query.filter(
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date <= today,
            TimeOffRequest.end_date >= today
        ).count()
        return result or 0
    except Exception as e:
        logger.error(f"Error getting employees on leave: {e}")
        db.session.rollback()
        
        # Try raw SQL fallback
        try:
            result = db.session.execute(
                text("""
                    SELECT COUNT(*) FROM time_off_request 
                    WHERE status = 'approved' 
                    AND start_date <= :today 
                    AND end_date >= :today
                """),
                {'today': today}
            ).scalar()
            return result or 0
        except Exception as e2:
            logger.error(f"Raw SQL failed for employees on leave: {e2}")
            db.session.rollback()
            return 0
