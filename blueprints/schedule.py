# blueprints/schedule.py
# COMPLETE FILE - Pattern Generation Now Working
# Last Updated: 2025-10-08

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Employee, Schedule, Position
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_
import json
import logging

logger = logging.getLogger(__name__)

schedule_bp = Blueprint('schedule', __name__)

@schedule_bp.route('/schedule/select')
@login_required
def schedule_select():
    try:
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('supervisor.dashboard'))
        
        logger.info(f"User {current_user.name} accessing schedule selection")
        
        return render_template('schedule_selection.html')
        
    except Exception as e:
        logger.error(f"Error in schedule_select: {str(e)}")
        flash('Error loading schedule selection page.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@schedule_bp.route('/schedule/wizard/<pattern>')
@login_required
def schedule_wizard(pattern):
    try:
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('supervisor.dashboard'))
        
        valid_patterns = [
            'pitman', 'dupont', 'southern_swing', 'fixed_fixed', 'four_on_four_off', 'five_and_two',
            'pitman_fixed', 'pitman_rapid', 'pitman_2week', 'pitman_4week',
            'four_on_four_off_fixed', 'four_on_four_off_modified', 'four_on_four_off_fast', 'four_on_four_off_weekly',
            'three_on_three_off', 'three_on_three_off_fixed', 'three_on_three_off_weekly', 'three_on_three_off_6week',
            'panama', 'fixed_five_two_12', 'fixed_four_three',
            'southern_swing_ccw', 'southern_swing_fixed', 'fixed_five_two_8', 'continental'
        ]
        
        if pattern not in valid_patterns:
            flash(f'Invalid schedule pattern: {pattern}', 'danger')
            return redirect(url_for('schedule.schedule_select'))
        
        employees = Employee.query.filter_by(is_active=True, is_supervisor=False).order_by(Employee.name).all()
        positions = Position.query.order_by(Position.name).all()
        
        employees_by_crew = {'A': [], 'B': [], 'C': [], 'D': [], 'Unassigned': []}
        for emp in employees:
            crew = emp.crew if emp.crew in ['A', 'B', 'C', 'D'] else 'Unassigned'
            employees_by_crew[crew].append(emp)
        
        crew_stats = {}
        for crew in ['A', 'B', 'C', 'D']:
            crew_employees = employees_by_crew.get(crew, [])
            crew_stats[crew] = {
                'count': len(crew_employees),
                'positions': {}
            }
            
            for emp in crew_employees:
                if emp.position:
                    pos_name = emp.position.name
                    if pos_name not in crew_stats[crew]['positions']:
                        crew_stats[crew]['positions'][pos_name] = 0
                    crew_stats[crew]['positions'][pos_name] += 1
        
        pattern_configs = {
            'pitman': {
                'name': 'Pitman (2-2-3)',
                'shift_hours': 12,
                'allows_fixed': True,
                'allows_rotating': True,
                'rotation_options': ['Fixed', 'Rapid Rotation', '2-Week Rotation', '4-Week Rotation']
            },
            'dupont': {
                'name': 'DuPont',
                'shift_hours': 12,
                'allows_fixed': False,
                'allows_rotating': True,
                'rotation_options': ['Standard']
            },
            'southern_swing': {
                'name': 'Southern Swing',
                'shift_hours': 8,
                'allows_fixed': False,
                'allows_rotating': True,
                'rotation_options': ['Standard']
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
                'rotation_options': ['Fixed', 'Rotating']
            },
            'five_and_two': {
                'name': '5 & 2 Schedule',
                'shift_hours': 12,
                'allows_fixed': True,
                'allows_rotating': False,
                'rotation_options': []
            },
        }
        
        return render_template('schedule_wizard.html',
                             pattern=pattern,
                             pattern_config=pattern_configs.get(pattern, {}),
                             employees=employees,
                             positions=positions,
                             employees_by_crew=employees_by_crew,
                             unassigned_employees=employees_by_crew.get('Unassigned', []),
                             crew_stats=crew_stats,
                             datetime=datetime,
                             timedelta=timedelta)
            
    except Exception as e:
        logger.error(f"Error in schedule_wizard: {str(e)}")
        flash('Error loading schedule wizard.', 'danger')
        return redirect(url_for('schedule.schedule_select'))

@schedule_bp.route('/schedule/view')
@login_required
def view_schedules():
    try:
        crew = request.args.get('crew', 'all')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        view_type = request.args.get('view', 'week')
        
        if not start_date:
            start_date = date.today()
        else:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if not end_date:
            if view_type == 'week':
                end_date = start_date + timedelta(days=6)
            elif view_type == 'month':
                if start_date.month == 12:
                    end_date = date(start_date.year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = date(start_date.year, start_date.month + 1, 1) - timedelta(days=1)
            else:
                end_date = start_date + timedelta(days=27)
        else:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        query = Schedule.query.filter(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        )
        
        if crew != 'all' and crew in ['A', 'B', 'C', 'D']:
            crew_employees = Employee.query.filter_by(crew=crew).all()
            employee_ids = [e.id for e in crew_employees]
            if employee_ids:
                query = query.filter(Schedule.employee_id.in_(employee_ids))
        
        schedules = query.order_by(Schedule.date, Schedule.shift_type).all()
        
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
        
        for schedule in schedules:
            if schedule.date in schedule_grid:
                shift_type = schedule.shift_type.value if schedule.shift_type else 'day'
                if shift_type in schedule_grid[schedule.date]:
                    schedule_grid[schedule.date][shift_type].append(schedule)
        
        crew_stats = {}
        for crew_letter in ['A', 'B', 'C', 'D']:
            crew_schedules = [s for s in schedules if s.employee and s.employee.crew == crew_letter]
            crew_stats[crew_letter] = {
                'total_shifts': len(crew_schedules),
                'day_shifts': len([s for s in crew_schedules if s.shift_type and s.shift_type.value == 'day']),
                'night_shifts': len([s for s in crew_schedules if s.shift_type and s.shift_type.value == 'night']),
                'hours': sum(s.hours or 8.0 for s in crew_schedules)
            }
        
        try:
            return render_template('schedule_view.html',
                                 schedules=schedules,
                                 schedule_grid=schedule_grid,
                                 dates=dates,
                                 start_date=start_date,
                                 end_date=end_date,
                                 view_type=view_type,
                                 crew=crew,
                                 crew_stats=crew_stats)
        except:
            return render_template('schedule_list.html',
                                 schedules=schedules,
                                 start_date=start_date,
                                 end_date=end_date,
                                 crew=crew)
                                 
    except Exception as e:
        logger.error(f"Error in view_schedules: {str(e)}")
        flash('Error loading schedules.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@schedule_bp.route('/schedule/api/create-pattern', methods=['POST'])
@login_required
def create_pattern_schedule():
    """
    UPDATED: Now actually creates schedules using pattern generators
    """
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        pattern = data.get('pattern')
        variation = data.get('variation')
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        replace_existing = data.get('replace_existing', True)
        
        # Validate required fields
        if not pattern:
            return jsonify({'success': False, 'error': 'Pattern is required'})
        
        if not start_date_str or not end_date_str:
            return jsonify({'success': False, 'error': 'Start and end dates are required'})
        
        # Parse dates
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD'})
        
        # Validate date range
        if start_date > end_date:
            return jsonify({'success': False, 'error': 'Start date must be before end date'})
        
        if (end_date - start_date).days > 365:
            return jsonify({'success': False, 'error': 'Schedule period cannot exceed 1 year'})
        
        # Import pattern generator
        try:
            from utils.pattern_generators import get_pattern_generator
        except ImportError as e:
            logger.error(f"Could not import pattern generators: {e}")
            return jsonify({
                'success': False,
                'error': 'Pattern generation system not available'
            }), 500
        
        # Get appropriate generator
        generator = get_pattern_generator(pattern, variation)
        
        if not generator:
            return jsonify({
                'success': False,
                'error': f'Pattern "{pattern}" with variation "{variation}" is not yet implemented'
            })
        
        # Generate schedules
        logger.info(f"Creating {pattern} ({variation}) schedule from {start_date} to {end_date}")
        
        result = generator.generate(
            start_date=start_date,
            end_date=end_date,
            created_by_id=current_user.id,
            replace_existing=replace_existing
        )
        
        if result['success']:
            logger.info(f"Successfully created {result['schedules_saved']} schedules")
            return jsonify({
                'success': True,
                'message': f'Successfully created {result["schedules_saved"]} schedule entries',
                'schedules_created': result['schedules_saved'],
                'date_range': result['date_range'],
                'statistics': result.get('statistics', {}),
                'redirect': url_for('schedule.view_schedules', 
                                   start_date=start_date.isoformat(),
                                   end_date=end_date.isoformat())
            })
        else:
            logger.error(f"Schedule generation failed: {result.get('error')}")
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error occurred')
            })
        
    except Exception as e:
        logger.error(f"Error creating pattern schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/schedule/api/preview-pattern', methods=['POST'])
@login_required
def preview_pattern():
    if not current_user.is_supervisor:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        pattern = data.get('pattern')
        start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        
        preview_data = []
        for day_offset in range(28):
            current_date = start_date + timedelta(days=day_offset)
            preview_data.append({
                'date': current_date.isoformat(),
                'day_name': current_date.strftime('%A'),
                'crews_working': {
                    'day': ['A', 'B'] if day_offset % 2 == 0 else ['C', 'D'],
                    'night': ['C', 'D'] if day_offset % 2 == 0 else ['A', 'B']
                }
            })
        
        return jsonify({
            'success': True,
            'preview': preview_data
        })
        
    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@schedule_bp.route('/schedule/create')
@login_required
def create_schedule():
    if not current_user.is_supervisor:
        flash('Access denied. Supervisors only.', 'danger')
        return redirect(url_for('supervisor.dashboard'))
    
    return redirect(url_for('schedule.schedule_select'))

@schedule_bp.errorhandler(404)
def not_found(error):
    flash('The requested schedule page was not found.', 'warning')
    return redirect(url_for('supervisor.dashboard'))

@schedule_bp.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error in schedule blueprint: {str(error)}")
    db.session.rollback()
    flash('An error occurred. Please try again.', 'danger')
    return redirect(url_for('supervisor.dashboard'))
