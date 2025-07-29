# blueprints/staffing_api.py

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from models import (
    db, Employee, Schedule, Position, PositionCoverage, VacationCalendar,
    OvertimeHistory, OvertimeOpportunity, EmployeeSkill, CoverageGap,
    OvertimeResponse, CoverageNotification
)
from engines.coverage_gap_engine import CoverageGapDetectionEngine
from engines.overtime_assignment_engine import OvertimeAssignmentEngine

staffing_api_bp = Blueprint('staffing_api', __name__, url_prefix='/api/staffing')

# Initialize engines
def get_engines():
    models = {
        'Employee': Employee,
        'Schedule': Schedule,
        'Position': Position,
        'PositionCoverage': PositionCoverage,
        'VacationCalendar': VacationCalendar,
        'OvertimeHistory': OvertimeHistory,
        'OvertimeOpportunity': OvertimeOpportunity,
        'EmployeeSkill': EmployeeSkill,
        'CoverageGap': CoverageGap
    }
    gap_engine = CoverageGapDetectionEngine(db, models)
    ot_engine = OvertimeAssignmentEngine(db, models)
    return gap_engine, ot_engine

@staffing_api_bp.route('/coverage-gaps/current')
@login_required
def get_current_gaps():
    """Get current shift coverage gaps"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    gap_engine, _ = get_engines()
    
    # Determine current shift
    now = datetime.now()
    current_hour = now.hour
    shift_type = 'day' if 6 <= current_hour < 18 else 'night'
    
    # Get gaps
    gaps = gap_engine.detect_current_gaps(shift_type=shift_type)
    
    return jsonify({
        'shift_type': shift_type,
        'timestamp': now.isoformat(),
        'gaps': gaps,
        'total_gaps': sum(g['gap'] for g in gaps),
        'critical_count': len([g for g in gaps if g['critical']])
    })

@staffing_api_bp.route('/coverage-gaps/future')
@login_required
def get_future_gaps():
    """Get future coverage gaps"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    days_ahead = request.args.get('days', 14, type=int)
    gap_engine, _ = get_engines()
    
    gaps = gap_engine.detect_future_gaps(days_ahead=days_ahead)
    
    # Group by urgency
    urgency_groups = {
        'immediate': [],
        'urgent': [],
        'high': [],
        'medium': [],
        'low': []
    }
    
    for gap in gaps:
        urgency_groups[gap['urgency']].append(gap)
    
    return jsonify({
        'days_ahead': days_ahead,
        'total_gaps': len(gaps),
        'gaps_by_urgency': urgency_groups,
        'positions_affected': len(set(g['position_id'] for g in gaps))
    })

@staffing_api_bp.route('/coverage-gaps/summary')
@login_required
def get_gap_summary():
    """Get comprehensive gap summary for dashboard"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    gap_engine, _ = get_engines()
    summary = gap_engine.get_gap_summary()
    
    return jsonify(summary)

@staffing_api_bp.route('/coverage-gaps/check-time-off', methods=['POST'])
@login_required
def check_time_off_impact():
    """Check coverage impact of a time off request"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    employee_id = data.get('employee_id')
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
    
    gap_engine, _ = get_engines()
    impact = gap_engine.check_time_off_impact(employee_id, start_date, end_date)
    
    return jsonify(impact)

@staffing_api_bp.route('/overtime/eligible-employees')
@login_required
def get_eligible_for_overtime():
    """Get list of eligible employees for overtime"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    position_id = request.args.get('position_id', type=int)
    date_str = request.args.get('date')
    shift_type = request.args.get('shift_type', 'day')
    
    if not position_id or not date_str:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    date_needed = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    _, ot_engine = get_engines()
    eligible = ot_engine.get_eligible_employees(position_id, date_needed, shift_type)
    
    # Format for response
    formatted = []
    for emp in eligible[:20]:  # Limit to top 20
        formatted.append({
            'employee_id': emp['employee'].id,
            'name': emp['employee'].name,
            'crew': emp['crew'],
            'priority_score': emp['priority_score'],
            'overtime_hours_13w': emp['overtime_hours_13w'],
            'consecutive_days': emp['consecutive_days'],
            'fatigue_score': emp['fatigue_score'],
            'is_off_duty': emp['is_off_duty'],
            'warnings': emp['availability'].get('warnings', []),
            'available': emp['availability']['available']
        })
    
    return jsonify({
        'position_id': position_id,
        'date': date_str,
        'shift_type': shift_type,
        'eligible_count': len(eligible),
        'employees': formatted
    })

@staffing_api_bp.route('/overtime/create-opportunity', methods=['POST'])
@login_required
def create_overtime_opportunity():
    """Create and post overtime opportunity"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    position_id = data.get('position_id')
    date_str = data.get('date')
    shift_type = data.get('shift_type', 'day')
    urgency = data.get('urgency', 'standard')
    notes = data.get('notes', '')
    
    if not position_id or not date_str:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    date_needed = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    _, ot_engine = get_engines()
    
    try:
        opportunity, notified = ot_engine.create_overtime_opportunity(
            position_id=position_id,
            date_needed=date_needed,
            shift_type=shift_type,
            posted_by_id=current_user.id,
            urgency=urgency,
            notes=notes
        )
        
        return jsonify({
            'success': True,
            'opportunity_id': opportunity.id,
            'notified_count': len(notified),
            'deadline': opportunity.response_deadline.isoformat(),
            'notified_employees': notified
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@staffing_api_bp.route('/overtime/assign-mandatory', methods=['POST'])
@login_required
def assign_mandatory_overtime():
    """Assign mandatory overtime using reverse seniority"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    position_id = data.get('position_id')
    date_str = data.get('date')
    shift_type = data.get('shift_type', 'day')
    
    if not position_id or not date_str:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    date_needed = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    _, ot_engine = get_engines()
    
    try:
        employee, schedule, log = ot_engine.assign_mandatory_overtime(
            position_id=position_id,
            date_needed=date_needed,
            shift_type=shift_type,
            assigned_by_id=current_user.id
        )
        
        return jsonify({
            'success': True,
            'assigned_to': {
                'id': employee.id,
                'name': employee.name,
                'hire_date': employee.hire_date.isoformat() if employee.hire_date else None
            },
            'schedule_id': schedule.id,
            'log': log
        })
    
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@staffing_api_bp.route('/overtime/distribution-report')
@login_required
def get_overtime_distribution():
    """Get overtime distribution report"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    weeks = request.args.get('weeks', 13, type=int)
    start_date = date.today() - timedelta(weeks=weeks)
    
    _, ot_engine = get_engines()
    report = ot_engine.get_overtime_distribution_report(start_date=start_date)
    
    return jsonify(report)

@staffing_api_bp.route('/overtime/respond', methods=['POST'])
@login_required
def respond_to_overtime():
    """Employee response to overtime opportunity"""
    data = request.json
    opportunity_id = data.get('opportunity_id')
    response = data.get('response')  # accepted/declined
    reason = data.get('reason', '')
    
    if not opportunity_id or not response:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        # Record response
        ot_response = OvertimeResponse(
            opportunity_id=opportunity_id,
            employee_id=current_user.id,
            response=response,
            reason=reason
        )
        db.session.add(ot_response)
        
        # If accepted, check if first to accept
        if response == 'accepted':
            opportunity = OvertimeOpportunity.query.get(opportunity_id)
            if opportunity and opportunity.status == 'open':
                # Award to first acceptor
                opportunity.status = 'filled'
                opportunity.filled_by_id = current_user.id
                opportunity.filled_at = datetime.now()
                
                # Create schedule entry
                schedule = Schedule(
                    employee_id=current_user.id,
                    date=opportunity.date,
                    shift_type=opportunity.shift_type,
                    start_time='06:00' if opportunity.shift_type == 'day' else '18:00',
                    end_time='18:00' if opportunity.shift_type == 'day' else '06:00',
                    hours=12.0,
                    is_overtime=True,
                    overtime_reason='Voluntary overtime'
                )
                db.session.add(schedule)
                
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'Overtime shift assigned to you!',
                    'schedule_id': schedule.id
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'This opportunity has already been filled'
                })
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Response recorded'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@staffing_api_bp.route('/gaps/recommended-actions')
@login_required
def get_recommended_actions():
    """Get recommended actions for coverage gaps"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    gap_engine, _ = get_engines()
    
    # Get all current and urgent future gaps
    current_gaps = gap_engine.detect_current_gaps()
    future_gaps = gap_engine.detect_future_gaps(days_ahead=7)
    urgent_gaps = [g for g in future_gaps if g['urgency'] in ['immediate', 'urgent', 'high']]
    
    all_gaps = current_gaps + urgent_gaps
    actions = gap_engine.get_recommended_actions(all_gaps)
    
    return jsonify({
        'total_actions': len(actions),
        'actions': actions
    })

@staffing_api_bp.route('/fatigue/check/<int:employee_id>')
@login_required
def check_employee_fatigue(employee_id):
    """Check fatigue indicators for an employee"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    check_date = request.args.get('date')
    if check_date:
        check_date = datetime.strptime(check_date, '%Y-%m-%d').date()
    else:
        check_date = date.today()
    
    _, ot_engine = get_engines()
    
    # Calculate fatigue metrics
    consecutive = ot_engine._calculate_consecutive_days(employee_id, check_date)
    fatigue_score = ot_engine._calculate_fatigue_score(employee_id, check_date, 'day', consecutive)
    
    employee = Employee.query.get(employee_id)
    
    return jsonify({
        'employee_id': employee_id,
        'employee_name': employee.name if employee else 'Unknown',
        'check_date': check_date.isoformat(),
        'consecutive_days': consecutive,
        'fatigue_score': fatigue_score,
        'fatigue_level': 'high' if fatigue_score > 7 else 'medium' if fatigue_score > 4 else 'low',
        'warnings': []
    })
