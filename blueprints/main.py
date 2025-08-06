# FIX FOR YOUR EXISTING DASHBOARD ROUTE
# Location: blueprints/main.py
# Find the dashboard() function and replace it with this updated version

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Supervisor Operations Center Dashboard"""
    if not current_user.is_supervisor:
        return redirect(url_for('main.employee_dashboard'))
    
    try:
        # Get real-time staffing data
        today = date.today()
        
        # Get pending counts - REQUIRED by template
        pending_time_off = TimeOffRequest.query.filter_by(status='pending').count()
        pending_swaps = ShiftSwapRequest.query.filter_by(status='pending').count()
        total_employees = Employee.query.count()
        
        # Calculate coverage gaps for today - REQUIRED by template
        all_gaps = get_coverage_gaps()
        coverage_gaps = len([g for g in all_gaps if g['date'] == today])
        
        # NEW: Add missing variables that dashboard.html expects
        # Today's scheduled employees
        try:
            today_scheduled = Schedule.query.filter_by(date=today).count()
        except:
            today_scheduled = 0
        
        # Employees on leave today
        try:
            from models import VacationCalendar  # Import if not already imported
            today_on_leave = VacationCalendar.query.filter(
                and_(
                    VacationCalendar.date == today,
                    VacationCalendar.status == 'approved'
                )
            ).count()
        except:
            today_on_leave = 0
        
        # Critical maintenance issues
        try:
            critical_maintenance = MaintenanceIssue.query.filter(
                and_(
                    MaintenanceIssue.priority == 'critical',
                    MaintenanceIssue.status.in_(['open', 'in_progress'])
                )
            ).count()
        except:
            critical_maintenance = 0
        
        # Format current date
        current_date = today.strftime('%A, %B %d, %Y')
        
        # Return with ALL variables the template expects
        return render_template('dashboard.html',
            # Original 4 variables
            pending_time_off=pending_time_off,
            pending_swaps=pending_swaps,
            total_employees=total_employees,
            coverage_gaps=coverage_gaps,
            # NEW: Additional required variables
            today_scheduled=today_scheduled,
            today_on_leave=today_on_leave,
            critical_maintenance=critical_maintenance,
            current_date=current_date
        )
        
    except Exception as e:
        print(f"Dashboard error: {str(e)}")
        traceback.print_exc()
        flash('Error loading dashboard. Please try again.', 'error')
        
        # If error, render with safe defaults
        return render_template('dashboard.html',
            pending_time_off=0,
            pending_swaps=0,
            total_employees=0,
            coverage_gaps=0,
            today_scheduled=0,
            today_on_leave=0,
            critical_maintenance=0,
            current_date=date.today().strftime('%A, %B %d, %Y')
        )
