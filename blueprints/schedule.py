# blueprints/schedule.py - COMPLETE IMPLEMENTATION
"""
Schedule management blueprint with full pattern support
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Employee, Schedule, Position, OvertimeHistory
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_
from utils.schedule_pattern_engine import SchedulePatternEngine
import json

schedule_bp = Blueprint('schedule', __name__)

@schedule_bp.route('/schedule/select')
@login_required
def schedule_select():
    """Schedule pattern selection page"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Pattern information for display
    patterns = [
        {
            'id': 'pitman',
            'name': 'Pitman (2-2-3)',
            'description': '2 days on, 2 off, 3 on, 2 off, 2 on, 3 off',
            'shift_length': '12-hour',
            'cycle_days': 14,
            'pros': ['Every other weekend off', 'No more than 3 consecutive days'],
            'cons': ['Can have 7 days in a row across week boundary'],
            'variations': ['Fixed', 'Rapid Rotation', '2-Week Rotation', '4-Week Rotation']
        },
        {
            'id': 'dupont',
            'name': 'DuPont',
            'description': '4 nights, 3 off, 3 days, 1 off, 3 nights, 3 off, 4 days, 7 off',
            'shift_length': '12-hour',
            'cycle_days': 28,
            'pros': ['7 consecutive days off', 'Built-in recovery time'],
            'cons': ['Complex pattern', 'Requires rotation'],
            'variations': ['Standard (rotating only)']
        },
        {
            'id': 'southern_swing',
            'name': 'Southern Swing',
            'description': 'Rotating through days, evenings, and nights',
            'shift_length': '8-hour',
            'cycle_days': 28,
            'pros': ['Gradual shift changes', 'Experience all shifts'],
            'cons': ['Only 1 weekend off per month', 'Constant rotation'],
            'variations': ['Standard']
        },
        {
            'id': 'fixed_fixed',
            'name': 'Fixed Teams',
            'description': 'Mon-Thu teams (4x12) and Fri-Sun teams (3x12)',
            'shift_length': '12-hour',
            'cycle_days': 7,
            'pros': ['Completely predictable', 'Choose lifestyle'],
            'cons': ['Unequal hours', 'Weekend teams work every weekend'],
            'variations': ['Standard']
        },
        {
            'id': 'four_on_four_off',
            'name': '4-on-4-off',
            'description': 'Work 4 days, off 4 days',
            'shift_length': '12-hour',
            'cycle_days': 8,
            'pros': ['Simple pattern', 'Equal work/off days'],
            'cons': ['Averages 42 hours/week'],
            'variations': ['Fixed', 'Rotating']
        },
        {
            'id': 'five_and_two',
            'name': '5 & 2 Schedule',
            'description': 'Work stretches of 5 and 2 days',
            'shift_length': '12-hour',
            'cycle_days': 14,
            'pros': ['Long breaks', 'Balanced coverage'],
            'cons': ['Complex pattern', '5 consecutive work days'],
            'variations': ['Fixed only']
        }
    ]
    
    return render_template('schedule_selection.html', patterns=patterns)

@schedule_bp.route('/schedule/wizard/<pattern>')
@login_required
def schedule_wizard(pattern):
    """Pattern-specific schedule creation wizard"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Validate pattern
    valid_patterns = ['pitman', 'southern_swing', 'fixed_fixed', 'dupont', 
                      'five_and_two', 'four_on_four_off', 'panama', 'continental']
    
    if pattern not in valid_patterns:
        flash('Invalid schedule pattern selected.', 'danger')
        return redirect(url_for('schedule.schedule_select'))
    
    # Get data for wizard
    employees = Employee.query.filter_by(is_supervisor=False).order_by(Employee.name).all()
    positions = Position.query.order_by(Position.name).all()
    
    # Group employees by current crew
    employees_by_crew = {}
    unassigned_employees = []
    
    for emp in employees:
        if emp.crew:
            if emp.crew not in employees_by_crew:
                employees_by_crew[emp.crew] = []
            employees_by_crew[emp.crew].append(emp)
        else:
            unassigned_employees.append(emp)
    
    # Get crew statistics
    crew_stats = {}
    for crew in ['A', 'B', 'C', 'D']:
        crew_stats[crew] = {
            'count': len(employees_by_crew.get(crew, [])),
            'positions': {}
        }
        # Count positions in each crew
        for emp in employees_by_crew.get(crew, []):
            if emp.position:
                pos_name = emp.position.name
                crew_stats[crew]['positions'][pos_name] = crew_stats[crew]['positions'].get(pos_name, 0) + 1
    
    # Pattern-specific configuration
    pattern_configs = {
        'pitman': {
            'name': 'Pitman (2-2-3)',
            'shift_hours': 12,
            'allows_fixed': True,
            'allows_rotating': True,
            'rotation_options': ['fixed', 'rapid', '2_week', '4_week']
        },
        'dupont': {
            'name': 'DuPont',
            'shift_hours': 12,
            'allows_fixed': False,
            'allows_rotating': True,
            'rotation_options': ['standard']
        },
        'southern_swing': {
            'name': 'Southern Swing',
            'shift_hours': 8,
            'allows_fixed': False,
            'allows_rotating': True,
            'rotation_options': ['standard']
        },
        'fixed_fixed': {
            'name': 'Fixed Teams',
            'shift_hours': 12,
            'allows_fixed': True,
            'allows_rotating': False,
            'rotation_options': []
        },
        'four_on_four_off': {
            'name': '4-on-4-off',
            'shift_hours': 12,
            'allows_fixed': True,
            'allows_rotating': True,
            'rotation_options': ['standard']
        },
        'five_and_two': {
            'name': '5 & 2 Schedule',
            'shift_hours': 12,
            'allows_fixed': True,
            'allows_rotating': False,
            'rotation_options': []
        }
    }
    
    return render_template('schedule_wizard.html',
                         pattern=pattern,
                         pattern_config=pattern_configs.get(pattern, {}),
                         employees=employees,
                         positions=positions,
                         employees_by_crew=employees_by_crew,
                         unassigned_employees=unassigned_employees,
                         crew_stats=crew_stats)

@schedule_bp.route('/schedule/create-pattern', methods=['POST'])
@login_required
def create_pattern_schedule():
    """Create schedule using pattern engine"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Extract parameters
        pattern = data.get('pattern')
        start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        
        # Build configuration
        config = {
            'variation': data.get('variation', 'fixed'),
            'day_shift_start': data.get('day_shift_start', '06:00'),
            'night_shift_start': data.get('night_shift_start', '18:00'),
            'created_by_id': current_user.id
        }
        
        # Additional config from wizard
        if 'rotation_frequency' in data:
            config['rotation_frequency'] = data['rotation_frequency']
        if 'fair_rotation' in data:
            config['fair_rotation'] = data['fair_rotation']
        
        # Create pattern engine
        engine = SchedulePatternEngine()
        
        # Generate schedules
        schedules = engine.generate_schedule(pattern, start_date, end_date, config)
        
        # Validate schedules
        validation_results = engine.validate_schedule(schedules)
        
        if not validation_results['is_valid']:
            return jsonify({
                'success': False,
                'error': 'Schedule validation failed',
                'validation_issues': validation_results
            }), 400
        
        # Check for conflicts with existing schedules
        existing_count = Schedule.query.filter(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        ).count()
        
        if existing_count > 0:
            if not data.get('force_overwrite'):
                return jsonify({
                    'success': False,
                    'error': 'Existing schedules found',
                    'existing_count': existing_count,
                    'requires_confirmation': True
                }), 409
            else:
                # Delete existing schedules in range
                Schedule.query.filter(
                    Schedule.date >= start_date,
                    Schedule.date <= end_date
                ).delete()
        
        # Save schedules to database
        for schedule in schedules:
            db.session.add(schedule)
        
        db.session.commit()
        
        # Return success with statistics
        return jsonify({
            'success': True,
            'message': f'Successfully created {len(schedules)} schedules',
            'statistics': validation_results['statistics'],
            'redirect_url': url_for('schedule.view_schedules')
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating pattern schedule: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@schedule_bp.route('/schedule/preview-pattern', methods=['POST'])
@login_required
def preview_pattern():
    """Preview schedule pattern before creation"""
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Extract parameters
        pattern = data.get('pattern')
        start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        
        # Generate 4 weeks for preview
        preview_end = start_date + timedelta(days=27)
        
        config = {
            'variation': data.get('variation', 'fixed'),
            'day_shift_start': data.get('day_shift_start', '06:00'),
            'night_shift_start': data.get('night_shift_start', '18:00')
        }
        
        # Create pattern engine
        engine = SchedulePatternEngine()
        
        # Generate preview schedules
        schedules = engine.generate_schedule(pattern, start_date, preview_end, config)
        
        # Format for calendar display
        calendar_data = []
        crew_colors = {'A': '#28a745', 'B': '#17a2b8', 'C': '#ffc107', 'D': '#dc3545'}
        
        for schedule in schedules:
            employee = Employee.query.get(schedule.employee_id)
            if employee:
                calendar_data.append({
                    'title': f"{employee.crew}-{schedule.shift_type[0].upper()}",
                    'start': schedule.date.isoformat(),
                    'color': crew_colors.get(employee.crew, '#6c757d'),
                    'crew': employee.crew,
                    'shift': schedule.shift_type
                })
        
        # Group by date for summary
        summary_by_date = {}
        for item in calendar_data:
            date_key = item['start']
            if date_key not in summary_by_date:
                summary_by_date[date_key] = {'day': 0, 'night': 0, 'evening': 0}
            summary_by_date[date_key][item['shift']] += 1
        
        return jsonify({
            'success': True,
            'calendar_data': calendar_data,
            'summary': summary_by_date,
            'total_shifts': len(schedules)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error previewing pattern: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@schedule_bp.route('/schedule/view')
@login_required
def view_schedules():
    """View current schedules"""
    # Get date range from query params
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    view_type = request.args.get('view', 'week')  # week, month, pattern
    
    if not start_date:
        start_date = date.today()
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        if view_type == 'week':
            end_date = start_date + timedelta(days=6)
        elif view_type == 'month':
            # Last day of month
            if start_date.month == 12:
                end_date = date(start_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(start_date.year, start_date.month + 1, 1) - timedelta(days=1)
        else:  # pattern view - show 4 weeks
            end_date = start_date + timedelta(days=27)
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Get schedules
    schedules = Schedule.query.filter(
        Schedule.date >= start_date,
        Schedule.date <= end_date
    ).order_by(Schedule.date, Schedule.shift_type).all()
    
    # Organize schedules by date and shift
    schedule_grid = {}
    dates = []
    current = start_date
    
    while current <= end_date:
        dates.append(current)
        schedule_grid[current] = {
            'day': [],
            'evening': [],
            'night': []
        }
        current += timedelta(days=1)
    
    # Populate grid
    for schedule in schedules:
        if schedule.date in schedule_grid:
            shift_type = schedule.shift_type
            if shift_type not in schedule_grid[schedule.date]:
                schedule_grid[schedule.date][shift_type] = []
            schedule_grid[schedule.date][shift_type].append(schedule)
    
    # Get crew statistics
    crew_stats = {}
    for crew in ['A', 'B', 'C', 'D']:
        crew_schedules = [s for s in schedules if s.employee.crew == crew]
        crew_stats[crew] = {
            'total_shifts': len(crew_schedules),
            'day_shifts': len([s for s in crew_schedules if s.shift_type == 'day']),
            'night_shifts': len([s for s in crew_schedules if s.shift_type == 'night']),
            'hours': sum(s.hours for s in crew_schedules)
        }
    
    return render_template('schedule_view.html',
                         schedules=schedules,
                         schedule_grid=schedule_grid,
                         dates=dates,
                         start_date=start_date,
                         end_date=end_date,
                         view_type=view_type,
                         crew_stats=crew_stats)

@schedule_bp.route('/schedule/create', methods=['GET', 'POST'])
@login_required
def create_schedule():
    """Legacy schedule creation - redirect to pattern selection"""
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('main.employee_dashboard'))
    
    # Redirect to new pattern selection
    flash('Please use the pattern-based schedule creator for better results.', 'info')
    return redirect(url_for('schedule.schedule_select'))

# API endpoints for schedule management
@schedule_bp.route('/api/schedule/validate-coverage', methods=['POST'])
@login_required
def validate_coverage():
    """Validate coverage requirements for a date range"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        
        # Get position requirements
        positions = Position.query.all()
        min_coverage = {}
        for pos in positions:
            min_coverage[pos.id] = pos.min_coverage or 1
        
        # Check each date
        coverage_issues = []
        current = start_date
        
        while current <= end_date:
            # Get schedules for this date
            day_schedules = Schedule.query.filter_by(date=current).all()
            
            # Count by position and shift
            coverage = {
                'day': {},
                'night': {}
            }
            
            for schedule in day_schedules:
                shift = schedule.shift_type
                pos_id = schedule.position_id
                
                if shift not in coverage:
                    coverage[shift] = {}
                
                if pos_id not in coverage[shift]:
                    coverage[shift][pos_id] = 0
                
                coverage[shift][pos_id] += 1
            
            # Check minimums
            for pos_id, min_required in min_coverage.items():
                for shift in ['day', 'night']:
                    actual = coverage.get(shift, {}).get(pos_id, 0)
                    if actual < min_required:
                        position = Position.query.get(pos_id)
                        coverage_issues.append({
                            'date': current.isoformat(),
                            'shift': shift,
                            'position': position.name,
                            'required': min_required,
                            'actual': actual,
                            'gap': min_required - actual
                        })
            
            current += timedelta(days=1)
        
        return jsonify({
            'valid': len(coverage_issues) == 0,
            'issues': coverage_issues,
            'total_gaps': sum(issue['gap'] for issue in coverage_issues)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@schedule_bp.route('/api/schedule/crew-balance', methods=['GET'])
@login_required
def check_crew_balance():
    """Check if crews have balanced schedules"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        # Get date range
        days_ahead = int(request.args.get('days', 28))
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead - 1)
        
        # Get schedules
        schedules = Schedule.query.filter(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        ).all()
        
        # Calculate crew statistics
        crew_stats = {}
        for crew in ['A', 'B', 'C', 'D']:
            crew_employees = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
            crew_schedules = [s for s in schedules if s.employee.crew == crew]
            
            crew_stats[crew] = {
                'employees': len(crew_employees),
                'total_shifts': len(crew_schedules),
                'total_hours': sum(s.hours for s in crew_schedules),
                'shifts_per_employee': len(crew_schedules) / len(crew_employees) if crew_employees else 0,
                'hours_per_employee': sum(s.hours for s in crew_schedules) / len(crew_employees) if crew_employees else 0,
                'day_shifts': len([s for s in crew_schedules if s.shift_type == 'day']),
                'night_shifts': len([s for s in crew_schedules if s.shift_type == 'night'])
            }
        
        # Check balance
        avg_hours = sum(c['hours_per_employee'] for c in crew_stats.values()) / 4
        balance_threshold = 0.1  # 10% variance allowed
        
        balance_issues = []
        for crew, stats in crew_stats.items():
            variance = abs(stats['hours_per_employee'] - avg_hours) / avg_hours if avg_hours > 0 else 0
            if variance > balance_threshold:
                balance_issues.append({
                    'crew': crew,
                    'variance_percent': round(variance * 100, 1),
                    'hours_difference': round(stats['hours_per_employee'] - avg_hours, 1)
                })
        
        return jsonify({
            'balanced': len(balance_issues) == 0,
            'crew_stats': crew_stats,
            'average_hours': round(avg_hours, 1),
            'balance_issues': balance_issues
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
