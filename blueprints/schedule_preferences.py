# blueprints/schedule_preferences.py
"""
Schedule Preferences Blueprint - Complete Implementation
Allows employees to explore shift schedule options and submit preferences
Supervisors can view aggregated preferences and implement schedules
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Employee, Schedule, Position, ShiftPreference
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_
import json
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
schedule_preferences_bp = Blueprint('schedule_preferences', __name__)

# ==========================================
# MAIN ROUTES
# ==========================================

@schedule_preferences_bp.route('/schedule/preferences')
@login_required
def preferences():
    """Main schedule preferences tool"""
    try:
        # Load any existing preferences for the user
        existing_pref = None
        if not current_user.is_supervisor:
            existing_pref = ShiftPreference.query.filter_by(
                employee_id=current_user.id,
                is_active=True
            ).first()
        
        # For supervisors, get aggregate preferences
        aggregate_prefs = None
        if current_user.is_supervisor:
            aggregate_prefs = get_aggregate_preferences()
        
        return render_template('schedule_preferences.html',
                             existing_preference=existing_pref,
                             aggregate_preferences=aggregate_prefs)
                             
    except Exception as e:
        logger.error(f"Error loading schedule preferences: {e}")
        flash('Error loading preferences tool.', 'danger')
        return redirect(url_for('main.dashboard'))

@schedule_preferences_bp.route('/schedule/submit-preference', methods=['POST'])
@login_required
def submit_preference():
    """Submit employee schedule preference"""
    try:
        data = request.get_json()
        
        if current_user.is_supervisor:
            return jsonify({'success': False, 'error': 'Supervisors cannot submit preferences'})
        
        # Deactivate any existing preferences
        ShiftPreference.query.filter_by(
            employee_id=current_user.id,
            is_active=True
        ).update({'is_active': False})
        
        # Create new preference
        preference = ShiftPreference(
            employee_id=current_user.id,
            shift_length_pref=int(data.get('shiftLength', 50)),
            work_pattern_pref=int(data.get('workPattern', 50)),
            weekend_pref=int(data.get('weekendPref', 50)),
            schedule_type_pref=int(data.get('scheduleType', 50)),
            handover_time=int(data.get('handoverTime', 0)),
            selected_schedule=data.get('selectedSchedule'),
            submitted_at=datetime.now(),
            is_active=True
        )
        
        db.session.add(preference)
        db.session.commit()
        
        logger.info(f"Employee {current_user.name} submitted schedule preference: {data.get('selectedSchedule')}")
        
        return jsonify({
            'success': True,
            'message': 'Preference submitted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error submitting preference: {e}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })

@schedule_preferences_bp.route('/schedule/save-preference-template', methods=['POST'])
@login_required
def save_preference_template():
    """Save a preference template (supervisors only)"""
    try:
        if not current_user.is_supervisor:
            return jsonify({'success': False, 'error': 'Only supervisors can save templates'})
        
        data = request.get_json()
        template_name = data.get('name')
        preferences = data.get('preferences')
        
        # Save to database or file system
        # For now, we'll use a simple JSON file
        templates_file = 'schedule_preference_templates.json'
        
        try:
            with open(templates_file, 'r') as f:
                templates = json.load(f)
        except:
            templates = {}
        
        templates[template_name] = {
            'preferences': preferences,
            'created_by': current_user.name,
            'created_at': datetime.now().isoformat()
        }
        
        with open(templates_file, 'w') as f:
            json.dump(templates, f, indent=2)
        
        logger.info(f"Supervisor {current_user.name} saved preference template: {template_name}")
        
        return jsonify({
            'success': True,
            'message': 'Template saved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error saving template: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@schedule_preferences_bp.route('/schedule/preferences/report')
@login_required
def preferences_report():
    """View aggregated employee preferences (supervisors only)"""
    try:
        if not current_user.is_supervisor:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('main.dashboard'))
        
        # Get all active preferences
        preferences = ShiftPreference.query.filter_by(is_active=True).all()
        
        # Aggregate data
        schedule_counts = {}
        shift_length_avg = 0
        rotation_avg = 0
        
        if preferences:
            for pref in preferences:
                # Count schedule selections
                schedule = pref.selected_schedule or 'none'
                schedule_counts[schedule] = schedule_counts.get(schedule, 0) + 1
                
                # Calculate averages
                shift_length_avg += pref.shift_length_pref
                rotation_avg += pref.schedule_type_pref
            
            shift_length_avg /= len(preferences)
            rotation_avg /= len(preferences)
        
        # Get top preferences
        top_schedules = sorted(schedule_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return render_template('preferences_report.html',
                             total_responses=len(preferences),
                             schedule_counts=schedule_counts,
                             top_schedules=top_schedules,
                             shift_length_avg=shift_length_avg,
                             rotation_avg=rotation_avg,
                             preferences=preferences)
                             
    except Exception as e:
        logger.error(f"Error generating preferences report: {e}")
        flash('Error generating report.', 'danger')
        return redirect(url_for('supervisor.dashboard'))

@schedule_preferences_bp.route('/schedule/preferences/export')
@login_required
def export_preferences():
    """Export preferences to Excel (supervisors only)"""
    try:
        if not current_user.is_supervisor:
            return jsonify({'error': 'Access denied'}), 403
        
        import pandas as pd
        from io import BytesIO
        
        # Get all active preferences with employee info
        preferences = db.session.query(
            ShiftPreference,
            Employee
        ).join(
            Employee,
            ShiftPreference.employee_id == Employee.id
        ).filter(
            ShiftPreference.is_active == True
        ).all()
        
        # Create DataFrame
        data = []
        for pref, emp in preferences:
            data.append({
                'Employee': emp.name,
                'Email': emp.email,
                'Crew': emp.crew,
                'Position': emp.position.name if emp.position else '',
                'Shift Length Preference': f"{pref.shift_length_pref}% toward 12-hour",
                'Work Pattern': f"{pref.work_pattern_pref}% toward longer breaks",
                'Weekend Preference': f"{pref.weekend_pref}% toward full weekends",
                'Rotation Preference': f"{pref.schedule_type_pref}% toward rotation",
                'Selected Schedule': pref.selected_schedule,
                'Submitted': pref.submitted_at.strftime('%Y-%m-%d %H:%M')
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Employee Preferences', index=False)
            
            # Add summary sheet
            summary_data = {
                'Metric': [
                    'Total Responses',
                    'Average Shift Length Preference',
                    'Average Rotation Preference',
                    'Most Popular Schedule'
                ],
                'Value': [
                    len(preferences),
                    f"{df['Shift Length Preference'].str.rstrip('% toward 12-hour').astype(float).mean():.1f}%",
                    f"{df['Rotation Preference'].str.rstrip('% toward rotation').astype(float).mean():.1f}%",
                    df['Selected Schedule'].mode()[0] if not df.empty else 'N/A'
                ]
            }
            
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
        
        output.seek(0)
        
        from flask import send_file
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'schedule_preferences_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
        
    except Exception as e:
        logger.error(f"Error exporting preferences: {e}")
        flash('Error exporting preferences.', 'danger')
        return redirect(url_for('schedule_preferences.preferences_report'))

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_aggregate_preferences():
    """Get aggregated preference data for supervisors"""
    try:
        preferences = ShiftPreference.query.filter_by(is_active=True).all()
        
        if not preferences:
            return None
        
        # Calculate averages and distributions
        result = {
            'total_responses': len(preferences),
            'shift_length': {
                'avg': sum(p.shift_length_pref for p in preferences) / len(preferences),
                'prefer_8hr': len([p for p in preferences if p.shift_length_pref < 40]),
                'prefer_12hr': len([p for p in preferences if p.shift_length_pref > 60])
            },
            'rotation': {
                'avg': sum(p.schedule_type_pref for p in preferences) / len(preferences),
                'prefer_fixed': len([p for p in preferences if p.schedule_type_pref < 40]),
                'prefer_rotating': len([p for p in preferences if p.schedule_type_pref > 60])
            },
            'top_schedules': get_top_schedule_selections(preferences),
            'by_crew': get_preferences_by_crew(preferences)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting aggregate preferences: {e}")
        return None

def get_top_schedule_selections(preferences):
    """Get the most popular schedule selections"""
    schedule_counts = {}
    for pref in preferences:
        if pref.selected_schedule:
            schedule_counts[pref.selected_schedule] = schedule_counts.get(pref.selected_schedule, 0) + 1
    
    return sorted(schedule_counts.items(), key=lambda x: x[1], reverse=True)[:5]

def get_preferences_by_crew(preferences):
    """Break down preferences by crew"""
    crew_data = {}
    
    for pref in preferences:
        emp = Employee.query.get(pref.employee_id)
        if emp and emp.crew:
            if emp.crew not in crew_data:
                crew_data[emp.crew] = {
                    'count': 0,
                    'shift_length_sum': 0,
                    'rotation_sum': 0
                }
            
            crew_data[emp.crew]['count'] += 1
            crew_data[emp.crew]['shift_length_sum'] += pref.shift_length_pref
            crew_data[emp.crew]['rotation_sum'] += pref.schedule_type_pref
    
    # Calculate averages
    for crew in crew_data:
        if crew_data[crew]['count'] > 0:
            crew_data[crew]['shift_length_avg'] = crew_data[crew]['shift_length_sum'] / crew_data[crew]['count']
            crew_data[crew]['rotation_avg'] = crew_data[crew]['rotation_sum'] / crew_data[crew]['count']
    
    return crew_data

# ==========================================
# API ENDPOINTS
# ==========================================

@schedule_preferences_bp.route('/api/preferences/summary')
@login_required
def api_preferences_summary():
    """API endpoint for preference summary data"""
    try:
        if not current_user.is_supervisor:
            return jsonify({'error': 'Access denied'}), 403
        
        aggregate = get_aggregate_preferences()
        
        if not aggregate:
            return jsonify({
                'success': False,
                'message': 'No preferences submitted yet'
            })
        
        return jsonify({
            'success': True,
            'data': aggregate
        })
        
    except Exception as e:
        logger.error(f"Error in API preferences summary: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@schedule_preferences_bp.route('/api/preferences/employee/<int:employee_id>')
@login_required
def api_employee_preference(employee_id):
    """Get specific employee's preference"""
    try:
        # Check permission
        if not current_user.is_supervisor and current_user.id != employee_id:
            return jsonify({'error': 'Access denied'}), 403
        
        preference = ShiftPreference.query.filter_by(
            employee_id=employee_id,
            is_active=True
        ).first()
        
        if not preference:
            return jsonify({
                'success': False,
                'message': 'No preference found'
            })
        
        return jsonify({
            'success': True,
            'data': {
                'shift_length_pref': preference.shift_length_pref,
                'work_pattern_pref': preference.work_pattern_pref,
                'weekend_pref': preference.weekend_pref,
                'schedule_type_pref': preference.schedule_type_pref,
                'handover_time': preference.handover_time,
                'selected_schedule': preference.selected_schedule,
                'submitted_at': preference.submitted_at.isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting employee preference: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Log successful blueprint loading
logger.info("Schedule preferences blueprint loaded successfully")
