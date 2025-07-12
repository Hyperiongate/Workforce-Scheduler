from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, date
import os
from sqlalchemy import inspect, case, and_, or_, func
from models import db, Employee, Position, Skill, Schedule, Availability, TimeOffRequest, VacationCalendar, CoverageRequest, CasualWorker, CasualAssignment, ShiftSwapRequest, ScheduleSuggestion, CircadianProfile, SleepLog, SleepRecommendation, ShiftTransitionPlan, CoverageNotification, OvertimeOpportunity, ShiftTradePost, ShiftTradeProposal, ShiftTrade, TradeMatchPreference
from circadian_advisor import CircadianAdvisor
import json
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Fixed database URL configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Handle Render's PostgreSQL URL format
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Fallback to SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workforce.db'

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

# ==================== HELPER FUNCTIONS ====================

def get_coverage_gaps(crew='ALL', days_ahead=7):
    """Get coverage gaps for the specified crew and time period"""
    gaps = []
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)
    
    current = start_date
    while current <= end_date:
        # Check each shift type
        for shift_type in ['day', 'evening', 'night']:
            scheduled_query = Schedule.query.filter(
                Schedule.date == current,
                Schedule.shift_type == shift_type
            )
            
            if crew != 'ALL':
                scheduled_query = scheduled_query.filter(Schedule.crew == crew)
            
            scheduled_count = scheduled_query.count()
            
            # Define minimum coverage requirements
            min_coverage = {
                'day': 4,
                'evening': 3,
                'night': 2
            }
            
            if scheduled_count < min_coverage.get(shift_type, 2):
                gaps.append({
                    'date': current,
                    'shift_type': shift_type,
                    'scheduled': scheduled_count,
                    'required': min_coverage.get(shift_type, 2),
                    'gap': min_coverage.get(shift_type, 2) - scheduled_count
                })
    
        current += timedelta(days=1)
    
    return gaps

def get_off_duty_crews(schedule_date, shift_type):
    """Determine which crews are off duty for a given date and shift"""
    # This is a simplified version - in reality, you'd check the actual rotation pattern
    off_crews = []
    
    # Example logic: based on date, determine which crews are off
    day_number = (schedule_date - date(2024, 1, 1)).days % 4
    
    if shift_type == 'day':
        if day_number in [0, 1]:
            off_crews = ['C', 'D']
        else:
            off_crews = ['A', 'B']
    elif shift_type == 'night':
        if day_number in [0, 1]:
            off_crews = ['A', 'B']
        else:
            off_crews = ['C', 'D']
    
    return off_crews

def update_circadian_profile_on_schedule_change(employee_id, shift_type):
    """Update circadian profile when schedule changes"""
    profile = CircadianProfile.query.filter_by(employee_id=employee_id).first()
    if not profile:
        profile = CircadianProfile(
            employee_id=employee_id,
            chronotype='intermediate',
            preferred_shift=shift_type
        )
        db.session.add(profile)
    
    profile.current_shift_type = shift_type
    profile.last_shift_change = datetime.now()

def calculate_trade_compatibility(user, trade_post):
    """Calculate compatibility score for a trade"""
    schedule = trade_post.schedule
    
    # Check position match
    if user.position_id == schedule.position_id:
        return 'high'
    
    # Check skill match
    if schedule.position:
        required_skills = [s.id for s in schedule.position.required_skills]
        user_skills = [s.id for s in user.skills]
        if all(skill in user_skills for skill in required_skills):
            return 'medium'
    
    return 'low'

def get_trade_history(employee_id, limit=10):
    """Get trade history for an employee"""
    trades = ShiftTrade.query.filter(
        or_(
            ShiftTrade.employee1_id == employee_id,
            ShiftTrade.employee2_id == employee_id
        ),
        ShiftTrade.status == 'completed'
    ).order_by(ShiftTrade.completed_at.desc()).limit(limit).all()
    
    return trades

def get_overtime_opportunities():
    """Get upcoming overtime opportunities"""
    # This would typically query from a dedicated table or calculate based on gaps
    opportunities = []
    gaps = get_coverage_gaps('ALL', 14)
    
    for gap in gaps:
        if gap['gap'] > 0:
            opportunities.append({
                'id': f"{gap['date']}_{gap['shift_type']}",
                'date': gap['date'],
                'shift_type': gap['shift_type'],
                'positions_needed': gap['gap'],
                'start_time': datetime.strptime('07:00', '%H:%M').time() if gap['shift_type'] == 'day' else datetime.strptime('19:00', '%H:%M').time(),
                'end_time': datetime.strptime('19:00', '%H:%M').time() if gap['shift_type'] == 'day' else datetime.strptime('07:00', '%H:%M').time(),
                'hours': 12
            })
    
    return opportunities[:10]  # Return first 10

def get_overtime_eligible_employees():
    """Get employees eligible for overtime"""
    # Get employees with less than 40 hours this week
    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)
    
    employees = Employee.query.filter_by(is_supervisor=False).all()
    eligible = []
    
    for emp in employees:
        week_hours = db.session.query(func.sum(Schedule.hours)).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= week_start,
            Schedule.date <= week_end
        ).scalar() or 0
        
        if week_hours < 60:  # Eligible if under 60 hours
            eligible.append({
                'employee': emp,
                'current_hours': week_hours,
                'available_hours': 60 - week_hours
            })
    
    return eligible

def is_eligible_for_overtime(employee, opportunity):
    """Check if employee is eligible for specific overtime"""
    # Check weekly hours limit
    week_start = opportunity['date'] - timedelta(days=opportunity['date'].weekday())
    week_end = week_start + timedelta(days=6)
    
    current_hours = db.session.query(func.sum(Schedule.hours)).filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= week_start,
        Schedule.date <= week_end
    ).scalar() or 0
    
    if current_hours + opportunity['hours'] > 60:
        return False
    
    # Check if already scheduled that day
    existing = Schedule.query.filter_by(
        employee_id=employee.id,
        date=opportunity['date']
    ).first()
    
    return existing is None

def execute_shift_trade(trade):
    """Execute an approved shift trade"""
    schedule1 = Schedule.query.get(trade.schedule1_id)
    schedule2 = Schedule.query.get(trade.schedule2_id)
    
    # Swap employee assignments
    temp_employee = schedule1.employee_id
    schedule1.employee_id = schedule2.employee_id
    schedule2.employee_id = temp_employee
    
    # Update trade status
    trade.status = 'completed'
    trade.completed_at = datetime.now()

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
        # Explicitly specify the join condition
        pending_requests_query = pending_requests_query.join(
            Employee, TimeOffRequest.employee_id == Employee.id
        ).filter(crew_filter)
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

# ==================== SHIFT TRADE MARKETPLACE ROUTES ====================

@app.route('/shift-marketplace')
@login_required
def shift_marketplace():
    """Main shift trade marketplace view"""
    # Get filters from query params
    filters = {
        'start_date': request.args.get('start_date', date.today().strftime('%Y-%m-%d')),
        'end_date': request.args.get('end_date', (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')),
        'shift_type': request.args.get('shift_type', ''),
        'position': request.args.get('position', ''),
        'compatibility': request.args.get('compatibility', '')
    }
    
    # Get available trades (exclude user's own posts)
    available_trades_query = ShiftTradePost.query.filter(
        ShiftTradePost.status == 'active',
        ShiftTradePost.poster_id != current_user.id
    ).join(Schedule)
    
    # Apply filters
    if filters['start_date']:
        available_trades_query = available_trades_query.filter(
            Schedule.date >= datetime.strptime(filters['start_date'], '%Y-%m-%d').date()
        )
    if filters['end_date']:
        available_trades_query = available_trades_query.filter(
            Schedule.date <= datetime.strptime(filters['end_date'], '%Y-%m-%d').date()
        )
    if filters['shift_type']:
        available_trades_query = available_trades_query.filter(
            Schedule.shift_type == filters['shift_type']
        )
    if filters['position']:
        available_trades_query = available_trades_query.filter(
            Schedule.position_id == int(filters['position'])
        )
    
    available_trades = available_trades_query.order_by(Schedule.date).all()
    
    # Calculate compatibility for each trade
    for trade in available_trades:
        trade.compatibility = calculate_trade_compatibility(current_user, trade)
    
    # Filter by compatibility if specified
    if filters['compatibility']:
        available_trades = [t for t in available_trades if t.compatibility == filters['compatibility']]
    
    # Get user's posted shifts
    my_posts = ShiftTradePost.query.filter_by(
        poster_id=current_user.id,
        status='active'
    ).all()
    
    # Get user's active trades
    my_trades = ShiftTrade.query.filter(
        or_(
            ShiftTrade.employee1_id == current_user.id,
            ShiftTrade.employee2_id == current_user.id
        ),
        ShiftTrade.status.in_(['pending', 'approved'])
    ).all()
    
    # Get trade history
    trade_history = get_trade_history(current_user.id)
    
    # Get upcoming shifts for posting
    my_upcoming_shifts = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date <= date.today() + timedelta(days=60)
    ).order_by(Schedule.date).all()
    
    # Get positions for filter
    positions = Position.query.all()
    
    # Calculate statistics
    stats = {
        'available_trades': len(available_trades),
        'my_posted_shifts': len(my_posts),
        'my_active_trades': len(my_trades),
        'pending_trades': len([t for t in my_trades if t.status == 'pending']),
        'completed_trades': ShiftTrade.query.filter(
            or_(
                ShiftTrade.employee1_id == current_user.id,
                ShiftTrade.employee2_id == current_user.id
            ),
            ShiftTrade.status == 'completed'
        ).count()
    }
    
    return render_template('shift_marketplace.html',
                         available_trades=available_trades,
                         my_posts=my_posts,
                         my_trades=my_trades,
                         trade_history=trade_history,
                         my_upcoming_shifts=my_upcoming_shifts,
                         positions=positions,
                         filters=filters,
                         stats=stats)

@app.route('/shift-marketplace/post', methods=['POST'])
@login_required
def post_shift_for_trade():
    """Post a shift for trade"""
    schedule_id = request.form.get('schedule_id')
    
    # Verify ownership
    schedule = Schedule.query.get_or_404(schedule_id)
    if schedule.employee_id != current_user.id:
        flash('You can only post your own shifts for trade.', 'danger')
        return redirect(url_for('shift_marketplace'))
    
    # Check if already posted
    existing_post = ShiftTradePost.query.filter_by(
        schedule_id=schedule_id,
        status='active'
    ).first()
    
    if existing_post:
        flash('This shift is already posted for trade.', 'warning')
        return redirect(url_for('shift_marketplace'))
    
    # Create trade post
    trade_post = ShiftTradePost(
        poster_id=current_user.id,
        schedule_id=schedule_id,
        preferred_start_date=request.form.get('preferred_start_date') or None,
        preferred_end_date=request.form.get('preferred_end_date') or None,
        preferred_shift_types=','.join(request.form.getlist('preferred_shifts')),
        notes=request.form.get('notes', ''),
        auto_approve=request.form.get('auto_approve') == 'on',
        expires_at=datetime.now() + timedelta(days=30)
    )
    
    db.session.add(trade_post)
    db.session.commit()
    
    flash('Your shift has been posted to the trade marketplace!', 'success')
    return redirect(url_for('shift_marketplace'))

@app.route('/api/trade-post/<int:post_id>')
@login_required
def get_trade_post_details(post_id):
    """Get details of a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    
    # Increment view count
    post.view_count += 1
    db.session.commit()
    
    # Get schedule details
    schedule = post.schedule
    
    return jsonify({
        'id': post.id,
        'position': schedule.position.name if schedule.position else 'Unknown',
        'date': schedule.date.strftime('%A, %B %d, %Y'),
        'start_time': schedule.start_time.strftime('%I:%M %p'),
        'end_time': schedule.end_time.strftime('%I:%M %p'),
        'shift_type': schedule.shift_type,
        'notes': post.notes,
        'poster': post.poster.name
    })

@app.route('/api/my-compatible-shifts/<int:post_id>')
@login_required
def get_my_compatible_shifts(post_id):
    """Get user's shifts compatible with a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    schedule = post.schedule
    
    # Get user's upcoming shifts
    my_shifts_query = Schedule.query.filter(
        Schedule.employee_id == current_user.id,
        Schedule.date >= date.today(),
        Schedule.date != schedule.date  # Can't trade for same date
    )
    
    # Apply preferences if any
    if post.preferred_start_date:
        my_shifts_query = my_shifts_query.filter(
            Schedule.date >= post.preferred_start_date
        )
    if post.preferred_end_date:
        my_shifts_query = my_shifts_query.filter(
            Schedule.date <= post.preferred_end_date
        )
    if post.preferred_shift_types:
        preferred_types = post.preferred_shift_types.split(',')
        my_shifts_query = my_shifts_query.filter(
            Schedule.shift_type.in_(preferred_types)
        )
    
    my_shifts = my_shifts_query.order_by(Schedule.date).all()
    
    # Calculate compatibility for each shift
    shifts_data = []
    for shift in my_shifts:
        compatibility = 'high'
        if shift.position_id != schedule.position_id:
            compatibility = 'medium'
        if shift.shift_type != schedule.shift_type:
            compatibility = 'low' if compatibility == 'medium' else 'medium'
        
        shifts_data.append({
            'id': shift.id,
            'date': shift.date.strftime('%m/%d/%Y'),
            'position': shift.position.name if shift.position else 'TBD',
            'start_time': shift.start_time.strftime('%I:%M %p'),
            'end_time': shift.end_time.strftime('%I:%M %p'),
            'shift_type': shift.shift_type,
            'compatibility': compatibility
        })
    
    return jsonify(shifts_data)

@app.route('/api/trade-proposal/create', methods=['POST'])
@login_required
def create_trade_proposal():
    """Create a trade proposal"""
    trade_post_id = request.form.get('trade_post_id')
    offered_schedule_id = request.form.get('offered_schedule_id')
    message = request.form.get('message', '')
    
    # Verify trade post exists and is active
    trade_post = ShiftTradePost.query.get_or_404(trade_post_id)
    if trade_post.status != 'active':
        return jsonify({'success': False, 'message': 'This trade post is no longer active.'})
    
    # Verify ownership of offered schedule
    offered_schedule = Schedule.query.get_or_404(offered_schedule_id)
    if offered_schedule.employee_id != current_user.id:
        return jsonify({'success': False, 'message': 'You can only offer your own shifts.'})
    
    # Check if already proposed
    existing_proposal = ShiftTradeProposal.query.filter_by(
        trade_post_id=trade_post_id,
        proposer_id=current_user.id,
        status='pending'
    ).first()
    
    if existing_proposal:
        return jsonify({'success': False, 'message': 'You already have a pending proposal for this trade.'})
    
    # Create proposal
    proposal = ShiftTradeProposal(
        trade_post_id=trade_post_id,
        proposer_id=current_user.id,
        offered_schedule_id=offered_schedule_id,
        message=message
    )
    
    db.session.add(proposal)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Trade proposal sent successfully!'})

@app.route('/api/trade-proposals/<int:post_id>')
@login_required
def get_trade_proposals(post_id):
    """Get proposals for a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    
    # Verify ownership
    if post.poster_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    proposals = ShiftTradeProposal.query.filter_by(
        trade_post_id=post_id,
        status='pending'
    ).all()
    
    proposals_data = []
    for proposal in proposals:
        offered_shift = proposal.offered_schedule
        proposals_data.append({
            'id': proposal.id,
            'proposer_name': proposal.proposer.name,
            'offered_shift': f"{offered_shift.date.strftime('%m/%d')} - {offered_shift.position.name if offered_shift.position else 'TBD'} ({offered_shift.shift_type})",
            'message': proposal.message,
            'created_at': proposal.created_at.strftime('%m/%d %I:%M %p')
        })
    
    return jsonify(proposals_data)

@app.route('/api/trade-proposal/<int:proposal_id>/accept', methods=['POST'])
@login_required
def accept_trade_proposal(proposal_id):
    """Accept a trade proposal"""
    proposal = ShiftTradeProposal.query.get_or_404(proposal_id)
    
    # Verify ownership
    if proposal.trade_post.poster_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if proposal.status != 'pending':
        return jsonify({'success': False, 'message': 'This proposal is no longer pending.'})
    
    # Update proposal status
    proposal.status = 'accepted'
    proposal.responded_at = datetime.now()
    
    # Update trade post status
    proposal.trade_post.status = 'matched'
    
    # Reject other proposals for this post
    other_proposals = ShiftTradeProposal.query.filter(
        ShiftTradeProposal.trade_post_id == proposal.trade_post_id,
        ShiftTradeProposal.id != proposal_id,
        ShiftTradeProposal.status == 'pending'
    ).all()
    
    for other in other_proposals:
        other.status = 'rejected'
        other.responded_at = datetime.now()
    
    # Create shift trade record
    trade = ShiftTrade(
        employee1_id=proposal.trade_post.poster_id,
        employee2_id=proposal.proposer_id,
        schedule1_id=proposal.trade_post.schedule_id,
        schedule2_id=proposal.offered_schedule_id,
        trade_post_id=proposal.trade_post_id,
        trade_proposal_id=proposal_id,
        status='pending' if not proposal.trade_post.auto_approve else 'approved',
        requires_approval=not proposal.trade_post.auto_approve
    )
    
    db.session.add(trade)
    
    # If auto-approve, execute the trade immediately
    if proposal.trade_post.auto_approve:
        execute_shift_trade(trade)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Trade proposal accepted!'})

@app.route('/api/trade-proposal/<int:proposal_id>/reject', methods=['POST'])
@login_required
def reject_trade_proposal(proposal_id):
    """Reject a trade proposal"""
    proposal = ShiftTradeProposal.query.get_or_404(proposal_id)
    
    # Verify ownership
    if proposal.trade_post.poster_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    proposal.status = 'rejected'
    proposal.responded_at = datetime.now()
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/trade-post/<int:post_id>/cancel', methods=['POST'])
@login_required
def cancel_trade_post(post_id):
    """Cancel a trade post"""
    post = ShiftTradePost.query.get_or_404(post_id)
    
    # Verify ownership
    if post.poster_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    post.status = 'cancelled'
    
    # Reject all pending proposals
    proposals = ShiftTradeProposal.query.filter_by(
        trade_post_id=post_id,
        status='pending'
    ).all()
    
    for proposal in proposals:
        proposal.status = 'rejected'
        proposal.responded_at = datetime.now()
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/trade/<int:trade_id>/cancel', methods=['POST'])
@login_required
def cancel_trade(trade_id):
    """Cancel a pending trade"""
    trade = ShiftTrade.query.get_or_404(trade_id)
    
    # Verify participant
    if current_user.id not in [trade.employee1_id, trade.employee2_id]:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if trade.status != 'pending':
        return jsonify({'success': False, 'message': 'Only pending trades can be cancelled.'})
    
    trade.status = 'cancelled'
    
    # Reactivate the trade post if it was from marketplace
    if trade.trade_post:
        trade.trade_post.status = 'active'
    
    db.session.commit()
    
    return jsonify({'success': True})

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
    
    # Parse opportunity ID to get date and shift type
    parts = opportunity_id.split('_')
    opp_date = datetime.strptime(parts[0], '%Y-%m-%d').date()
    shift_type = parts[1]
    
    opportunity = {
        'date': opp_date,
        'shift_type': shift_type,
        'hours': 12,
        'start_time': datetime.strptime('07:00', '%H:%M').time() if shift_type == 'day' else datetime.strptime('19:00', '%H:%M').time(),
        'end_time': datetime.strptime('19:00', '%H:%M').time() if shift_type == 'day' else datetime.strptime('07:00', '%H:%M').time()
    }
    
    assignments_made = 0
    
    for emp_id in employee_ids:
        employee = Employee.query.get(emp_id)
        
        # Verify employee is eligible
        if not is_eligible_for_overtime(employee, opportunity):
            continue
        
        # Create overtime schedule
        schedule = Schedule(
            employee_id=employee.id,
            date=opportunity['date'],
            shift_type=opportunity['shift_type'],
            start_time=opportunity['start_time'],
            end_time=opportunity['end_time'],
            position_id=employee.position_id,
            hours=opportunity['hours'],
            is_overtime=True,
            crew=employee.crew
        )
        db.session.add(schedule)
        assignments_made += 1
    
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
        ShiftSwapRequest.status == 'pending'
    ).all()
    
    # Filter to show only relevant swaps for this supervisor
    relevant_swaps = []
    for swap in pending_swaps:
        requester = Employee.query.get(swap.requester_id)
        target = Employee.query.get(swap.target_employee_id) if swap.target_employee_id else None
        
        # Check if this supervisor oversees either employee
        if requester.crew == current_user.crew or (target and target.crew == current_user.crew):
            relevant_swaps.append(swap)
    
    recent_swaps = ShiftSwapRequest.query.filter(
        ShiftSwapRequest.status.in_(['approved', 'denied'])
    ).order_by(ShiftSwapRequest.created_at.desc()).limit(10).all()
    
    return render_template('swap_requests.html',
                         pending_swaps=relevant_swaps,
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

# ==================== DATABASE INITIALIZATION ROUTES ====================

@app.route('/init-db')
def init_db():
    """Initialize database with all tables"""
    with app.app_context():
        # Create all tables first
        db.create_all()
        
        # Now check if admin exists
        admin = Employee.query.filter_by(email='admin@workforce.com').first()
        if not admin:
            admin = Employee(
                name='Admin User',
                email='admin@workforce.com',
                is_supervisor=True,
                crew='A',
                vacation_days=20,
                sick_days=10,
                personal_days=5
            )
            admin.set_password('admin123')
            db.session.add(admin)
            
            # Create some default positions
            positions = [
                Position(name='Nurse', department='Healthcare', min_coverage=2),
                Position(name='Security Officer', department='Security', min_coverage=1),
                Position(name='Technician', department='Operations', min_coverage=3),
                Position(name='Customer Service', department='Support', min_coverage=2)
            ]
            for pos in positions:
                db.session.add(pos)
            
            # Create some default skills
            skills = [
                Skill(name='CPR Certified', category='Medical', requires_certification=True),
                Skill(name='First Aid', category='Medical', requires_certification=True),
                Skill(name='Security Clearance', category='Security', requires_certification=True),
                Skill(name='Emergency Response', category='General'),
                Skill(name='Equipment Operation', category='Technical')
            ]
            for skill in skills:
                db.session.add(skill)
            
            db.session.commit()
        
        return '''
        <h2>Database Initialized!</h2>
        <p>Admin account created:</p>
        <ul>
            <li>Email: admin@workforce.com</li>
            <li>Password: admin123</li>
        </ul>
        <p><a href="/login">Go to login</a></p>
        '''

@app.route('/add-coverage-tables')
def add_coverage_tables():
    """Add the new coverage notification and overtime tables"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Add Coverage Tables</h2>
        <p>This will add the CoverageNotification and OvertimeOpportunity tables to your database.</p>
        <p>These tables enable:</p>
        <ul>
            <li>Push notifications for coverage needs</li>
            <li>Smart overtime distribution</li>
            <li>Employee response tracking</li>
        </ul>
        <p><a href="/add-coverage-tables?confirm=yes" class="btn btn-primary">Click here to confirm</a></p>
        '''
    
    try:
        # Create all tables (this will only add new ones)
        db.create_all()
        return '''
        <h2>Success!</h2>
        <p>Coverage notification and overtime tables have been added to the database.</p>
        <p>New features available:</p>
        <ul>
            <li>Coverage push notifications</li>
            <li>Overtime opportunity management</li>
            <li>Smart crew distribution</li>
        </ul>
        <p><a href="/">Return to home</a></p>
        '''
    except Exception as e:
        return f'<h2>Error</h2><p>Failed to add tables: {str(e)}</p>'

@app.route('/add-marketplace-tables')
def add_marketplace_tables():
    """Add the shift trade marketplace tables"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>Add Shift Trade Marketplace Tables</h2>
        <p>This will add the new shift trade marketplace tables to your database.</p>
        <p>New tables to be added:</p>
        <ul>
            <li>ShiftTradePost - Posts of shifts available for trade</li>
            <li>ShiftTradeProposal - Trade proposals from employees</li>
            <li>ShiftTrade - Completed or pending trades</li>
            <li>TradeMatchPreference - Employee trade preferences</li>
        </ul>
        <p>Features enabled:</p>
        <ul>
            <li>Post shifts for trade in marketplace</li>
            <li>Browse and filter available trades</li>
            <li>Smart compatibility matching</li>
            <li>Trade history tracking</li>
            <li>Auto-approval options</li>
        </ul>
        <p><a href="/add-marketplace-tables?confirm=yes" class="btn btn-primary">Click here to confirm</a></p>
        '''
    
    try:
        # Create all tables (this will only add new ones)
        db.create_all()
        return '''
        <h2>Success!</h2>
        <p>Shift trade marketplace tables have been added to the database.</p>
        <p>New features available:</p>
        <ul>
            <li>Shift Trade Marketplace - Employees can now post and trade shifts</li>
            <li>Smart Matching - System suggests compatible trades</li>
            <li>Trade History - Track all completed trades</li>
        </ul>
        <p>Employees can access the marketplace from their dashboard.</p>
        <p><a href="/">Return to home</a></p>
        '''
    except Exception as e:
        return f'<h2>Error</h2><p>Failed to add marketplace tables: {str(e)}</p>'

@app.route('/reset-db')
def reset_db():
    """Reset database - WARNING: This will delete all data!"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>⚠️ WARNING: Reset Database</h2>
        <p style="color: red;"><strong>This will DELETE ALL DATA in the database!</strong></p>
        <p>Only use this for initial setup or if you're sure you want to start over.</p>
        <p><a href="/reset-db?confirm=yes" onclick="return confirm('Are you SURE you want to delete all data?')" style="background: red; color: white; padding: 10px; text-decoration: none;">Yes, reset the database</a></p>
        <p><a href="/" style="background: green; color: white; padding: 10px; text-decoration: none;">Cancel and go back</a></p>
        '''
    
    try:
        with app.app_context():
            # For PostgreSQL, we need to drop tables with CASCADE
            from sqlalchemy import text
            
            # Get the database engine
            engine = db.engine
            
            # Drop all tables using raw SQL with CASCADE
            with engine.connect() as conn:
                # First, drop all tables in the public schema
                conn.execute(text("DROP SCHEMA public CASCADE"))
                conn.execute(text("CREATE SCHEMA public"))
                conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
                conn.commit()
            
            # Now recreate all tables with correct schema
            db.create_all()
            
        return '''
        <h2>✅ Database Reset Complete!</h2>
        <p>All tables have been dropped and recreated with the correct schema.</p>
        <p><a href="/init-db" style="background: blue; color: white; padding: 10px; text-decoration: none;">Now initialize the database with default data</a></p>
        '''
    except Exception as e:
        return f'<h2>Error</h2><p>Failed to reset database: {str(e)}</p>'

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==================== MAIN ====================

@app.route('/populate-crews')
def populate_crews():
    """Populate database with 4 complete crews for development"""
    if request.args.get('confirm') != 'yes':
        return '''
        <h2>🏗️ Populate 4 Crews for Development</h2>
        <p>This will create <strong>40 employees</strong> (10 per crew) with:</p>
        <ul>
            <li><strong>Crew A:</strong> 10 employees (Day shift preference)</li>
            <li><strong>Crew B:</strong> 10 employees (Day shift preference)</li>
            <li><strong>Crew C:</strong> 10 employees (Night shift preference)</li>
            <li><strong>Crew D:</strong> 10 employees (Night shift preference)</li>
        </ul>
        <p>Each crew will have:</p>
        <ul>
            <li>1 Crew Lead (supervisor)</li>
            <li>3 Nurses</li>
            <li>2 Security Officers</li>
            <li>2 Technicians</li>
            <li>2 Customer Service Representatives</li>
        </ul>
        <p><strong>Login credentials:</strong></p>
        <ul>
            <li>Email format: [name].[lastname]@company.com</li>
            <li>Password: password123 (for all)</li>
        </ul>
        <p><a href="/populate-crews?confirm=yes" class="btn btn-primary" onclick="return confirm('Create 40 employees across 4 crews?')">Yes, Populate Crews</a></p>
        <p><a href="/dashboard" class="btn btn-secondary">Cancel</a></p>
        '''
    
    try:
        # Get positions (assuming they exist from init-db)
        nurse = Position.query.filter_by(name='Nurse').first()
        security = Position.query.filter_by(name='Security Officer').first()
        tech = Position.query.filter_by(name='Technician').first()
        customer_service = Position.query.filter_by(name='Customer Service').first()
        
        # Get skills
        skills = {
            'cpr': Skill.query.filter_by(name='CPR Certified').first(),
            'first_aid': Skill.query.filter_by(name='First Aid').first(),
            'security': Skill.query.filter_by(name='Security Clearance').first(),
            'emergency': Skill.query.filter_by(name='Emergency Response').first(),
            'equipment': Skill.query.filter_by(name='Equipment Operation').first()
        }
        
        # Employee data for each crew
        crew_templates = {
            'A': {
                'shift_preference': 'day',
                'employees': [
                    {'name': 'Alice Anderson', 'email': 'alice.anderson@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Adam Martinez', 'email': 'adam.martinez@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Angela Brown', 'email': 'angela.brown@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Andrew Wilson', 'email': 'andrew.wilson@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Amanda Davis', 'email': 'amanda.davis@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Aaron Johnson', 'email': 'aaron.johnson@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Anna Miller', 'email': 'anna.miller@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Alex Thompson', 'email': 'alex.thompson@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Amy Garcia', 'email': 'amy.garcia@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Anthony Lee', 'email': 'anthony.lee@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            },
            'B': {
                'shift_preference': 'day',
                'employees': [
                    {'name': 'Barbara Bennett', 'email': 'barbara.bennett@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Brian Clark', 'email': 'brian.clark@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Betty Rodriguez', 'email': 'betty.rodriguez@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Benjamin Lewis', 'email': 'benjamin.lewis@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Brenda Walker', 'email': 'brenda.walker@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Blake Hall', 'email': 'blake.hall@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Bonnie Allen', 'email': 'bonnie.allen@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Bruce Young', 'email': 'bruce.young@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Brittany King', 'email': 'brittany.king@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Bradley Wright', 'email': 'bradley.wright@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            },
            'C': {
                'shift_preference': 'night',
                'employees': [
                    {'name': 'Carol Campbell', 'email': 'carol.campbell@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Charles Parker', 'email': 'charles.parker@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Christine Evans', 'email': 'christine.evans@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Christopher Turner', 'email': 'christopher.turner@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Cynthia Collins', 'email': 'cynthia.collins@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Craig Edwards', 'email': 'craig.edwards@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Catherine Stewart', 'email': 'catherine.stewart@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Carl Sanchez', 'email': 'carl.sanchez@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Cheryl Morris', 'email': 'cheryl.morris@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Chad Rogers', 'email': 'chad.rogers@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            },
            'D': {
                'shift_preference': 'night',
                'employees': [
                    {'name': 'Diana Davidson', 'email': 'diana.davidson@company.com', 'position': nurse, 'is_supervisor': True, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'David Foster', 'email': 'david.foster@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Deborah Murphy', 'email': 'deborah.murphy@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid', 'emergency']},
                    {'name': 'Daniel Rivera', 'email': 'daniel.rivera@company.com', 'position': nurse, 'skills': ['cpr', 'first_aid']},
                    {'name': 'Donna Cook', 'email': 'donna.cook@company.com', 'position': security, 'skills': ['security', 'emergency']},
                    {'name': 'Dennis Morgan', 'email': 'dennis.morgan@company.com', 'position': security, 'skills': ['security', 'first_aid']},
                    {'name': 'Dorothy Peterson', 'email': 'dorothy.peterson@company.com', 'position': tech, 'skills': ['equipment', 'emergency']},
                    {'name': 'Douglas Cooper', 'email': 'douglas.cooper@company.com', 'position': tech, 'skills': ['equipment']},
                    {'name': 'Denise Bailey', 'email': 'denise.bailey@company.com', 'position': customer_service, 'skills': ['emergency']},
                    {'name': 'Derek Reed', 'email': 'derek.reed@company.com', 'position': customer_service, 'skills': ['first_aid']}
                ]
            }
        }
        
        created_count = 0
        
        for crew_letter, crew_data in crew_templates.items():
            for emp_data in crew_data['employees']:
                # Check if employee already exists
                existing = Employee.query.filter_by(email=emp_data['email']).first()
                if existing:
                    continue
                
                # Create employee
                employee = Employee(
                    name=emp_data['name'],
                    email=emp_data['email'],
                    phone=f'555-{crew_letter}{str(created_count).zfill(3)}',
                    is_supervisor=emp_data.get('is_supervisor', False),
                    position_id=emp_data['position'].id if emp_data['position'] else None,
                    crew=crew_letter,
                    shift_pattern=crew_data['shift_preference'],
                    hire_date=date.today() - timedelta(days=365),  # 1 year ago
                    vacation_days=10,
                    sick_days=5,
                    personal_days=3
                )
                
                # Set password
                employee.set_password('password123')
                
                # Add skills
                for skill_key in emp_data.get('skills', []):
                    if skill_key in skills and skills[skill_key]:
                        employee.skills.append(skills[skill_key])
                
                db.session.add(employee)
                created_count += 1
                
                # Create circadian profile
                profile = CircadianProfile(
                    employee_id=employee.id,
                    chronotype='morning' if crew_data['shift_preference'] == 'day' else 'evening',
                    current_shift_type=crew_data['shift_preference'],
                    preferred_shift=crew_data['shift_preference']
                )
                db.session.add(profile)
        
        db.session.commit()
        
        return f'''
        <h2>✅ Crews Populated Successfully!</h2>
        <p><strong>{created_count} employees</strong> have been created across 4 crews.</p>
        
        <h3>Crew Supervisors (can approve requests):</h3>
        <ul>
            <li><strong>Crew A:</strong> Alice Anderson (alice.anderson@company.com)</li>
            <li><strong>Crew B:</strong> Barbara Bennett (barbara.bennett@company.com)</li>
            <li><strong>Crew C:</strong> Carol Campbell (carol.campbell@company.com)</li>
            <li><strong>Crew D:</strong> Diana Davidson (diana.davidson@company.com)</li>
        </ul>
        
        <h3>Sample Regular Employees:</h3>
        <ul>
            <li><strong>Nurse:</strong> Adam Martinez (adam.martinez@company.com)</li>
            <li><strong>Security:</strong> Amanda Davis (amanda.davis@company.com)</li>
            <li><strong>Technician:</strong> Anna Miller (anna.miller@company.com)</li>
            <li><strong>Customer Service:</strong> Amy Garcia (amy.garcia@company.com)</li>
        </ul>
        
        <p><strong>All passwords:</strong> password123</p>
        
        <h3>Next Steps:</h3>
        <ol>
            <li><a href="/schedule/create" class="btn btn-primary">Create Schedules</a> - Set up shifts for your crews</li>
            <li><a href="/schedule/view" class="btn btn-info">View Schedules</a> - See crew assignments</li>
            <li><a href="/logout" class="btn btn-warning">Logout</a> - Try logging in as an employee</li>
        </ol>
        
        <p><a href="/dashboard" class="btn btn-success">Return to Dashboard</a></p>
        '''
        
    except Exception as e:
        db.session.rollback()
        return f'''
        <h2>❌ Error Populating Crews</h2>
        <p>An error occurred: {str(e)}</p>
        <p>Make sure you've run <a href="/init-db">/init-db</a> first to create positions and skills.</p>
        <p><a href="/dashboard" class="btn btn-secondary">Return to Dashboard</a></p>
        '''
