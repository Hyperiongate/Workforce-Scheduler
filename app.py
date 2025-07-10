from flask import Flask, render_template, jsonify, request, redirect, url_for
import os
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from models import db, Employee, Position, Schedule, Skill, TimeOffRequest, CoverageRequest

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
        
        db.session.commit()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

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

if __name__ == '__main__':
    app.run(debug=True)
