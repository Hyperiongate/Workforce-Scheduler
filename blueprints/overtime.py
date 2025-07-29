# blueprints/overtime.py
"""
Overtime management blueprint with smart assignment algorithm
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import (db, Employee, Position, Schedule, OvertimeHistory, 
                   OvertimeOpportunity, CoverageNotification, Skill,
                   CrewCoverageRequirement, CasualWorker)
from datetime import date, timedelta, datetime
from sqlalchemy import func, and_, or_
import json

overtime_bp = Blueprint('overtime', __name__, url_prefix='/overtime')

class OvertimeAssignmentEngine:
    """Smart overtime assignment algorithm"""
    
    @staticmethod
    def get_eligible_employees(position_id, date_needed, shift_type, crew_needed=None):
        """
        Get employees eligible for overtime in priority order
        
        Priority Order:
        1. Off-duty employees from crews about to come on shift
        2. Off-duty employees from crews just finishing
        3. Employees already working (double shifts - last resort)
        """
        eligible = []
        position = Position.query.get(position_id)
        if not position:
            return eligible
        
        # Get required skills for this position
        required_skills = [skill.id for skill in position.required_skills]
        
        # Determine which crews are off on the needed date
        scheduled_crews = db.session.query(Employee.crew).join(Schedule).filter(
            Schedule.date == date_needed,
            Schedule.shift_type == shift_type
        ).distinct().all()
        scheduled_crews = [c[0] for c in scheduled_crews if c[0]]
        
        off_duty_crews = [c for c in ['A', 'B', 'C', 'D'] if c not in scheduled_crews]
        
        # Get all qualified employees
        base_query = Employee.query.filter(
            Employee.is_supervisor == False,
            Employee.position_id == position_id  # Same position preferred
        )
        
        # If specific skills required, filter by those
        if required_skills:
            base_query = base_query.join(Employee.skills).filter(
                Skill.id.in_(required_skills)
            )
        
        all_eligible = base_query.all()
        
        # Calculate each employee's priority score
        for emp in all_eligible:
            score = OvertimeAssignmentEngine._calculate_priority_score(
                emp, date_needed, shift_type, off_duty_crews, crew_needed
            )
            eligible.append({
                'employee': emp,
                'score': score,
                'overtime_hours': emp.last_13_weeks_overtime,
                'is_off_duty': emp.crew in off_duty_crews,
                'availability': OvertimeAssignmentEngine._check_availability(emp, date_needed, shift_type)
            })
        
        # Sort by priority score (higher is better)
        eligible.sort(key=lambda x: x['score'], reverse=True)
        
        return eligible
    
    @staticmethod
    def _calculate_priority_score(employee, date_needed, shift_type, off_duty_crews, crew_needed):
        """Calculate priority score for overtime assignment"""
        score = 100.0
        
        # Crew assignment scoring
        if crew_needed and employee.crew == crew_needed:
            score += 50  # Strong preference for same crew
        
        # Off-duty bonus
        if employee.crew in off_duty_crews:
            score += 30
        else:
            score -= 50  # Penalty for already working
        
        # Overtime history (less overtime = higher priority)
        # Inverse relationship: those with less OT get higher scores
        ot_hours = employee.last_13_weeks_overtime or 0
        if ot_hours < 40:
            score += 20
        elif ot_hours < 80:
            score += 10
        elif ot_hours > 120:
            score -= 20
        elif ot_hours > 160:
            score -= 40
        
        # Seniority bonus (for tie-breaking)
        if employee.hire_date:
            years_of_service = (date.today() - employee.hire_date).days / 365.25
            score += min(years_of_service * 2, 20)  # Max 20 points for seniority
        
        # Check recent shifts (avoid back-to-back different shifts)
        recent_shift = Schedule.query.filter(
            Schedule.employee_id == employee.id,
            Schedule.date == date_needed - timedelta(days=1)
        ).first()
        
        if recent_shift:
            if recent_shift.shift_type != shift_type:
                score -= 30  # Penalty for shift change without rest
        
        # Fatigue check - consecutive days worked
        consecutive_days = OvertimeAssignmentEngine._count_consecutive_days(employee, date_needed)
        if consecutive_days >= 6:
            score -= 50
        elif consecutive_days >= 4:
            score -= 20
        
        return score
    
    @staticmethod
    def _check_availability(employee, date_needed, shift_type):
        """Check if employee is available for overtime"""
        # Check for approved time off
        time_off = db.session.query(TimeOffRequest).filter(
            TimeOffRequest.employee_id == employee.id,
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date <= date_needed,
            TimeOffRequest.end_date >= date_needed
        ).first()
        
        if time_off:
            return {'available': False, 'reason': 'On approved time off'}
        
        # Check if already scheduled
        existing_schedule = Schedule.query.filter(
            Schedule.employee_id == employee.id,
            Schedule.date == date_needed
        ).first()
        
        if existing_schedule:
            if existing_schedule.shift_type == shift_type:
                return {'available': False, 'reason': 'Already scheduled for this shift'}
            else:
                return {'available': True, 'reason': 'Would be double shift', 'warning': True}
        
        return {'available': True, 'reason': 'Available'}
    
    @staticmethod
    def _count_consecutive_days(employee, date_needed):
        """Count consecutive days worked leading up to date_needed"""
        count = 0
        check_date = date_needed - timedelta(days=1)
        
        for i in range(7):  # Check up to 7 days back
            schedule = Schedule.query.filter(
                Schedule.employee_id == employee.id,
                Schedule.date == check_date
            ).first()
            
            if schedule:
                count += 1
                check_date -= timedelta(days=1)
            else:
                break
        
        return count

# API Routes for Quick Actions

@overtime_bp.route('/api/post', methods=['POST'])
@login_required
def post_overtime():
    """Post overtime opportunity"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.json
        position_id = data.get('position_id')
        date_str = data.get('date')
        shift_type = data.get('shift_type')
        crew = data.get('crew')
        urgent = data.get('urgent', False)
        
        # Parse date
        date_needed = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        
        # Get eligible employees
        eligible = OvertimeAssignmentEngine.get_eligible_employees(
            position_id, date_needed, shift_type, crew
        )
        
        # Create overtime opportunity
        opportunity = OvertimeOpportunity(
            position_id=position_id,
            date=date_needed,
            shift_type=shift_type,
            posted_by_id=current_user.id,
            status='open',
            urgent=urgent,
            response_deadline=datetime.now() + timedelta(hours=4 if urgent else 24)
        )
        db.session.add(opportunity)
        db.session.flush()
        
        # Send notifications to eligible employees
        notifications_sent = 0
        for emp_data in eligible[:10]:  # Notify top 10 eligible
            if emp_data['availability']['available']:
                notification = CoverageNotification(
                    coverage_request_id=opportunity.id,
                    sent_to_type='individual',
                    sent_to_employee_id=emp_data['employee'].id,
                    sent_by_id=current_user.id,
                    message=f"Overtime available: {shift_type} shift on {date_needed.strftime('%b %d')} - {Position.query.get(position_id).name}"
                )
                db.session.add(notification)
                notifications_sent += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'opportunity_id': opportunity.id,
            'eligible_count': len(eligible),
            'notifications_sent': notifications_sent,
            'message': f'Overtime posted to {notifications_sent} eligible employees'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@overtime_bp.route('/api/assign-mandatory', methods=['POST'])
@login_required
def assign_mandatory():
    """Assign mandatory overtime using reverse seniority"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.json
        position_id = data.get('position_id')
        date_str = data.get('date')
        shift_type = data.get('shift_type')
        
        date_needed = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get eligible employees
        eligible = OvertimeAssignmentEngine.get_eligible_employees(
            position_id, date_needed, shift_type
        )
        
        # Filter to only available employees
        available = [e for e in eligible if e['availability']['available'] and not e['availability'].get('warning')]
        
        if not available:
            return jsonify({'error': 'No available employees for mandatory assignment'}), 400
        
        # Sort by reverse seniority (newest employees first)
        available.sort(key=lambda x: x['employee'].hire_date or date.today(), reverse=True)
        
        # Assign to newest available employee
        selected = available[0]['employee']
        
        # Create schedule entry
        schedule = Schedule(
            employee_id=selected.id,
            date=date_needed,
            shift_type=shift_type,
            start_time='06:00' if shift_type == 'day' else '18:00',
            end_time='18:00' if shift_type == 'day' else '06:00',
            hours=12.0,
            is_overtime=True,
            overtime_reason='Mandatory assignment'
        )
        db.session.add(schedule)
        
        # Log the mandatory assignment
        notification = CoverageNotification(
            sent_to_type='individual',
            sent_to_employee_id=selected.id,
            sent_by_id=current_user.id,
            message=f"You have been assigned mandatory overtime: {shift_type} shift on {date_needed.strftime('%b %d')}",
            sent_at=datetime.now()
        )
        db.session.add(notification)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'assigned_to': {
                'id': selected.id,
                'name': selected.name,
                'hire_date': selected.hire_date.strftime('%Y-%m-%d') if selected.hire_date else None
            },
            'message': f'Mandatory overtime assigned to {selected.name}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@overtime_bp.route('/api/eligible-employees/<int:position_id>')
@login_required
def get_eligible_employees(position_id):
    """Get list of eligible employees for a position"""
    if not current_user.is_supervisor:
        return jsonify({'error': 'Unauthorized'}), 403
    
    date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    shift_type = request.args.get('shift', 'day')
    crew = request.args.get('crew')
    
    date_needed = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    eligible = OvertimeAssignmentEngine.get_eligible_employees(
        position_id, date_needed, shift_type, crew
    )
    
    # Format for JSON response
    result = []
    for emp_data in eligible:
        result.append({
            'employee_id': emp_data['employee'].id,
            'name': emp_data['employee'].name,
            'crew': emp_data['employee'].crew,
            'score': round(emp_data['score'], 2),
            'overtime_hours': emp_data['overtime_hours'],
            'is_off_duty': emp_data['is_off_duty'],
            'available': emp_data['availability']['available'],
            'availability_reason': emp_data['availability']['reason'],
            'warning': emp_data['availability'].get('warning', False)
        })
    
    return jsonify({
        'success': True,
        'position': Position.query.get(position_id).name,
        'date': date_str,
        'shift': shift_type,
        'eligible_count': len(result),
        'employees': result
    })

@overtime_bp.route('/quick-post/<int:position_id>')
@login_required
def quick_post_form(position_id):
    """Quick overtime posting form"""
    if not current_user.is_supervisor:
        flash('Supervisor access required', 'danger')
        return redirect(url_for('main.dashboard'))
    
    position = Position.query.get_or_404(position_id)
    
    # Get next 7 days for quick selection
    dates = []
    today = date.today()
    for i in range(7):
        d = today + timedelta(days=i)
        dates.append({
            'date': d,
            'display': d.strftime('%a %b %d'),
            'is_weekend': d.weekday() >= 5
        })
    
    return render_template('overtime/quick_post.html',
        position=position,
        dates=dates,
        shifts=['day', 'night'],
        crews=['A', 'B', 'C', 'D']
    )
