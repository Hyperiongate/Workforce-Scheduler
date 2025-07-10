from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import os
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from models import db, Employee, Position, Schedule, Skill, TimeOffRequest, CoverageRequest, CasualWorker, CasualAssignment
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///workforce.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database with app
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()
    
    # Add some sample data if database is empty
    if Employee.query.count() == 0:
        # Add sample positions
        positions = [
            Position(name='Cashier', description='Handle customer transactions'),
            Position(name='Stock Clerk', description='Manage inventory and restock shelves'),
            Position(name='Supervisor', description='Oversee daily operations'),
            Position(name='Customer Service', description='Assist customers with inquiries')
        ]
        for p in positions:
            db.session.add(p)
        
        # Add sample employees
        employees = [
            Employee(name='John Doe', email='john@example.com', phone='555-0101', crew='Day Shift', is_supervisor=False),
            Employee(name='Jane Smith', email='jane@example.com', phone='555-0102', crew='Day Shift', is_supervisor=False),
            Employee(name='Mike Johnson', email='mike@example.com', phone='555-0103', crew='Day Shift', is_supervisor=True),
            Employee(name='Sarah Williams', email='sarah@example.com', phone='555-0104', crew='Night Shift', is_supervisor=False),
            Employee(name='Tom Brown', email='tom@example.com', phone='555-0105', crew='Night Shift', is_supervisor=False)
        ]
        for e in employees:
            db.session.add(e)
        
        db.session.commit()
        
        # Add sample schedules for today
        cashier = Position.query.filter_by(name='Cashier').first()
        stock = Position.query.filter_by(name='Stock Clerk').first()
        supervisor = Position.query.filter_by(name='Supervisor').first()
        
        john = Employee.query.filter_by(name='John Doe').first()
        jane = Employee.query.filter_by(name='Jane Smith').first()
        mike = Employee.query.filter_by(name='Mike Johnson').first()
        
        from datetime import time
        today = date.today()
        
        schedules = [
            Schedule(date=today, start_time=time(9, 0), end_time=time(17, 0), 
                    employee_id=john.id, position_id=cashier.id, status='confirmed'),
            Schedule(date=today, start_time=time(9, 0), end_time=time(17, 0), 
                    employee_id=jane.id, position_id=stock.id, status='confirmed'),
            Schedule(date=today, start_time=time(8, 0), end_time=time(18, 0), 
                    employee_id=mike.id, position_id=supervisor.id, status='confirmed')
        ]
        for s in schedules:
            db.session.add(s)
        
        # Add sample casual workers
        casual_workers = [
            CasualWorker(
                name='Alex Rivera',
                email='alex.r@email.com',
                phone='555-0201',
                skills='Forklift certified, Customer service',
                availability='{"weekday_morning": true, "weekends": true, "short_notice": true}',
                rating=4.8
            ),
            CasualWorker(
                name='Pat Chen',
                email='pat.chen@email.com',
                phone='555-0202',
                skills='Food handling, Cash register',
                availability='{"weekday_afternoon": true, "weekday_evening": true}',
                rating=4.5
            ),
            CasualWorker(
                name='Jordan Taylor',
                email='j.taylor@email.com',
                phone='555-0203',
                skills='Heavy lifting, Warehouse experience',
                availability='{"weekends": true, "short_notice": true}',
                rating=5.0
            )
        ]
        for cw in casual_workers:
            db.session.add(cw)
        
        db.session.commit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    # Get open coverage requests
    coverage_requests = CoverageRequest.query.filter_by(status='open').all()
    
    # Get available casual workers
    casual_workers = CasualWorker.query.filter_by(status='available').limit(5).all()
    
    # Get today's schedules
    today = date.today()
    schedules = Schedule.query.filter_by(date=today).all()
    
    return render_template('dashboard.html', 
                         schedules=schedules,
                         coverage_requests=coverage_requests,
                         casual_workers=casual_workers)

# Casual Worker Registration
@app.route('/register-casual', methods=['GET', 'POST'])
def register_casual():
    if request.method == 'POST':
        try:
            worker = CasualWorker(
                name=request.form['name'],
                email=request.form['email'],
                phone=request.form['phone'],
                skills=request.form.get('skills', ''),
                availability=request.form.get('availability', '{}')
            )
            db.session.add(worker)
            db.session.commit()
            flash('Registration successful! We\'ll contact you when work is available.', 'success')
            return redirect(url_for('register_casual'))
        except Exception as e:
            flash('Registration failed. Email may already be registered.', 'error')
            return redirect(url_for('register_casual'))
    
    return render_template('register_casual.html')

# View all casual workers
@app.route('/casual-workers')
def casual_workers():
    workers = CasualWorker.query.all()
    return render_template('casual_workers.html', workers=workers)

# Request casual worker
@app.route('/request-casual', methods=['POST'])
def request_casual():
    try:
        # Create assignment
        assignment = CasualAssignment(
            worker_id=request.form['worker_id'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            start_time=datetime.strptime(request.form['start_time'], '%H:%M').time(),
            end_time=datetime.strptime(request.form['end_time'], '%H:%M').time(),
            position=request.form.get('position', 'General Labor')
        )
        db.session.add(assignment)
        
        # Update worker status
        worker = CasualWorker.query.get(request.form['worker_id'])
        if worker:
            worker.status = 'working'
            
            # In development, just print the notification
            print(f"NOTIFICATION TO {worker.name} ({worker.phone}): Work available on {assignment.date}")
        
        db.session.commit()
        flash(f'Work request sent to {worker.name}!', 'success')
    except Exception as e:
        flash('Failed to create work request.', 'error')
        print(f"Error: {e}")
    
    return redirect(url_for('dashboard'))

# Development route to recreate database
@app.route('/recreate-db')
def recreate_db():
    if app.debug:  # Only works in debug mode
        db.drop_all()
        db.create_all()
        
        # Re-run the initialization code
        with app.app_context():
            # (Copy the initialization code from above here if you want to repopulate)
            pass
        
        return "Database recreated! <a href='/'>Go home</a>"
    return "Only works in debug mode"

# API endpoint to get today's schedule
@app.route('/api/schedule/today')
def get_today_schedule():
    today = date.today()
    schedules = Schedule.query.filter_by(date=today).all()
    
    shifts = []
    for schedule in schedules:
        employee = Employee.query.get(schedule.employee_id)
        position = Position.query.get(schedule.position_id)
        
        shifts.append({
            'id': schedule.id,
            'position': position.name if position else 'Unknown',
            'time': f"{schedule.start_time.strftime('%I:%M %p')} - {schedule.end_time.strftime('%I:%M %p')}",
            'employee': employee.name if employee else 'Unassigned',
            'status': schedule.status
        })
    
    return jsonify({
        'success': True,
        'date': today.strftime('%Y-%m-%d'),
        'shifts': shifts
    })

# API endpoint to report absence
@app.route('/api/absence/report', methods=['POST'])
def report_absence():
    data = request.get_json()
    employee_name = data.get('employee', '')
    
    # Find the employee
    employee = Employee.query.filter_by(name=employee_name).first()
    if employee:
        # Find today's schedule for this employee
        today = date.today()
        schedule = Schedule.query.filter_by(
            employee_id=employee.id,
            date=today
        ).first()
        
        if schedule:
            # Update schedule status
            schedule.status = 'absent'
            
            # Create coverage request
            coverage = CoverageRequest(schedule_id=schedule.id)
            db.session.add(coverage)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Absence reported for {employee_name}. Coverage request sent to available staff.'
            })
    
    return jsonify({
        'success': False,
        'message': 'Employee not found or not scheduled today'
    })

# API endpoint to get employees
@app.route('/api/employees')
def get_employees():
    employees = Employee.query.filter_by(is_active=True).all()
    return jsonify({
        'success': True,
        'employees': [{
            'id': e.id,
            'name': e.name,
            'email': e.email,
            'crew': e.crew,
            'is_supervisor': e.is_supervisor
        } for e in employees]
    })

# API endpoint to get casual workers
@app.route('/api/casual-workers/available')
def get_available_casual_workers():
    workers = CasualWorker.query.filter_by(status='available').all()
    return jsonify({
        'success': True,
        'workers': [{
            'id': w.id,
            'name': w.name,
            'phone': w.phone,
            'skills': w.skills,
            'rating': w.rating,
            'availability': json.loads(w.availability) if w.availability else {}
        } for w in workers]
    })

if __name__ == '__main__':
    app.run(debug=True)
