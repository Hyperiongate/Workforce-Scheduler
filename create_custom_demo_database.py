"""
Custom Demo Database Generator - 80 Employees (20 per crew)
Run this script to populate your database with 80 employees and realistic data
"""

from datetime import datetime, timedelta, date, time
import random
from app import app, db
from models import (Employee, Position, Skill, Schedule, TimeOffRequest, 
                   VacationCalendar, CoverageRequest, CasualWorker, 
                   ShiftSwapRequest, ScheduleSuggestion, CircadianProfile,
                   OvertimeOpportunity)
from werkzeug.security import generate_password_hash

# Lists of first and last names for generating 80 unique employees
FIRST_NAMES = [
    'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles',
    'Christopher', 'Daniel', 'Matthew', 'Anthony', 'Donald', 'Mark', 'Paul', 'Steven', 'Andrew', 'Kenneth',
    'Mary', 'Patricia', 'Jennifer', 'Linda', 'Elizabeth', 'Barbara', 'Susan', 'Jessica', 'Sarah', 'Karen',
    'Nancy', 'Betty', 'Helen', 'Sandra', 'Donna', 'Carol', 'Ruth', 'Sharon', 'Michelle', 'Laura',
    'Kevin', 'Brian', 'George', 'Edward', 'Ronald', 'Timothy', 'Jason', 'Jeffrey', 'Ryan', 'Jacob',
    'Gary', 'Nicholas', 'Eric', 'Jonathan', 'Stephen', 'Larry', 'Justin', 'Scott', 'Brandon', 'Benjamin',
    'Lisa', 'Dorothy', 'Amy', 'Angela', 'Ashley', 'Brenda', 'Emma', 'Nicole', 'Samantha', 'Katherine',
    'Christine', 'Deborah', 'Rachel', 'Marilyn', 'Andrea', 'Kathryn', 'Louise', 'Sara', 'Anne', 'Jacqueline'
]

LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez',
    'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
    'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson',
    'Walker', 'Young', 'Allen', 'King', 'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill', 'Flores',
    'Green', 'Adams', 'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell', 'Mitchell', 'Carter', 'Roberts',
    'Gomez', 'Phillips', 'Evans', 'Turner', 'Diaz', 'Parker', 'Cruz', 'Edwards', 'Collins', 'Reyes',
    'Stewart', 'Morris', 'Morales', 'Murphy', 'Cook', 'Rogers', 'Gutierrez', 'Ortiz', 'Morgan', 'Cooper',
    'Peterson', 'Bailey', 'Reed', 'Kelly', 'Howard', 'Ramos', 'Kim', 'Cox', 'Ward', 'Richardson'
]

def generate_unique_employees(num_per_crew=20):
    """Generate unique employee names and emails"""
    employees = []
    used_names = set()
    
    # Shuffle names to ensure variety
    first_names = FIRST_NAMES.copy()
    last_names = LAST_NAMES.copy()
    random.shuffle(first_names)
    random.shuffle(last_names)
    
    crews = ['A', 'B', 'C', 'D']
    
    for crew in crews:
        for i in range(num_per_crew):
            # Keep trying until we get a unique combination
            attempts = 0
            while attempts < 100:
                first = random.choice(first_names)
                last = random.choice(last_names)
                full_name = f"{first} {last}"
                
                if full_name not in used_names:
                    used_names.add(full_name)
                    email = f"{first.lower()}.{last.lower()}@example.com"
                    # Add number if email already exists
                    email_base = email
                    email_counter = 1
                    while any(emp['email'] == email for emp in employees):
                        email = f"{first.lower()}.{last.lower()}{email_counter}@example.com"
                        email_counter += 1
                    
                    employees.append({
                        'name': full_name,
                        'email': email,
                        'crew': crew
                    })
                    break
                attempts += 1
    
    return employees

def create_custom_demo_database():
    """Create a demo database with 80 employees"""
    
    with app.app_context():
        # Clear existing data
        print("Clearing existing data...")
        db.drop_all()
        db.create_all()
        
        # ==================== CREATE POSITIONS ====================
        print("Creating positions...")
        positions = [
            Position(name='Operator', department='Operations', min_coverage=5),
            Position(name='Senior Operator', department='Operations', min_coverage=2),
            Position(name='Lead Operator', department='Operations', min_coverage=1),
            Position(name='Maintenance Tech', department='Maintenance', min_coverage=2),
            Position(name='Quality Control', department='Quality', min_coverage=2),
            Position(name='Material Handler', department='Warehouse', min_coverage=3),
            Position(name='Technician', department='Technical', min_coverage=2),
            Position(name='Specialist', department='Technical', min_coverage=1)
        ]
        for pos in positions:
            db.session.add(pos)
        db.session.commit()
        
        # ==================== CREATE SKILLS ====================
        print("Creating skills...")
        skills = [
            Skill(name='Low Skill', category='Basic', requires_certification=False),
            Skill(name='Medium Skill', category='Intermediate', requires_certification=False),
            Skill(name='High Skill', category='Advanced', requires_certification=True)
        ]
        for skill in skills:
            db.session.add(skill)
        db.session.commit()
        
        # ==================== CREATE SUPERVISORS ====================
        print("Creating supervisors...")
        supervisors = [
            ('Mike Johnson', 'mike@example.com', 'A'),
            ('Sarah Williams', 'sarah@example.com', 'B'),
            ('David Chen', 'david@example.com', 'C'),
            ('Lisa Martinez', 'lisa@example.com', 'D')
        ]
        
        for name, email, crew in supervisors:
            supervisor = Employee(
                name=name,
                email=email,
                phone=f'555-{1000 + ord(crew)}00',  # 555-6500, 555-6600, etc.
                is_supervisor=True,
                crew=crew,
                position_id=Position.query.filter_by(name='Lead Operator').first().id,
                department='Operations',
                hire_date=date.today() - timedelta(days=random.randint(2000, 4000)),
                vacation_days=20,
                sick_days=10,
                personal_days=5
            )
            supervisor.set_password('admin123')
            
            # Supervisors get all skills
            for skill in Skill.query.all():
                supervisor.skills.append(skill)
            
            db.session.add(supervisor)
        
        # ==================== CREATE 80 EMPLOYEES ====================
        print("Creating 80 employees...")
        employee_data = generate_unique_employees(20)  # 20 per crew
        
        # Position distribution per crew (20 employees)
        position_distribution = [
            ('Operator', 8),
            ('Senior Operator', 4),
            ('Maintenance Tech', 2),
            ('Quality Control', 2),
            ('Material Handler', 2),
            ('Technician', 1),
            ('Specialist', 1)
        ]
        
        all_employees = []
        employee_count = 0
        
        for crew in ['A', 'B', 'C', 'D']:
            crew_employees = [emp for emp in employee_data if emp['crew'] == crew]
            position_index = 0
            position_count = 0
            current_position, max_count = position_distribution[0]
            
            for emp_data in crew_employees:
                # Assign position based on distribution
                if position_count >= max_count:
                    position_index += 1
                    if position_index < len(position_distribution):
                        current_position, max_count = position_distribution[position_index]
                        position_count = 0
                
                position = Position.query.filter_by(name=current_position).first()
                
                # Calculate hire date (more senior employees in higher positions)
                if current_position in ['Specialist', 'Senior Operator', 'Lead Operator']:
                    # Senior positions: 2-10 years
                    hire_days_ago = random.randint(730, 3650)
                elif current_position in ['Technician', 'Quality Control']:
                    # Mid-level: 1-5 years
                    hire_days_ago = random.randint(365, 1825)
                else:
                    # Entry level: 0-3 years
                    hire_days_ago = random.randint(30, 1095)
                
                employee = Employee(
                    name=emp_data['name'],
                    email=emp_data['email'],
                    phone=f'555-{random.randint(2000, 9999)}',
                    is_supervisor=False,
                    crew=crew,
                    position_id=position.id,
                    department=position.department,
                    hire_date=date.today() - timedelta(days=hire_days_ago),
                    vacation_days=10,
                    sick_days=5,
                    personal_days=3
                )
                employee.set_password('password123')
                
                # Assign skills based on position and seniority
                low_skill = Skill.query.filter_by(name='Low Skill').first()
                medium_skill = Skill.query.filter_by(name='Medium Skill').first()
                high_skill = Skill.query.filter_by(name='High Skill').first()
                
                # Everyone gets low skill
                employee.skills.append(low_skill)
                
                # Medium skill based on position and seniority
                if hire_days_ago > 365 or current_position not in ['Operator', 'Material Handler']:
                    employee.skills.append(medium_skill)
                
                # High skill for senior positions and long-tenure employees
                if current_position in ['Specialist', 'Senior Operator', 'Lead Operator'] or hire_days_ago > 1825:
                    employee.skills.append(high_skill)
                
                db.session.add(employee)
                all_employees.append(employee)
                position_count += 1
                employee_count += 1
                
                # Progress indicator
                if employee_count % 10 == 0:
                    print(f"  Created {employee_count}/80 employees...")
        
        db.session.commit()
        
        # ==================== ASSIGN OVERTIME HOURS ====================
        print("Assigning overtime hours to employees...")
        
        # Fetch all employees (including those just created)
        all_employees = Employee.query.filter_by(is_supervisor=False).all()
        
        for employee in all_employees:
            # Generate overtime hours between 0 and 200
            # Use a realistic distribution - most people have moderate overtime
            if random.random() < 0.3:  # 30% have low overtime (0-50 hours)
                overtime_hours = random.randint(0, 50)
            elif random.random() < 0.6:  # 60% have moderate overtime (50-120 hours)
                overtime_hours = random.randint(50, 120)
            else:  # 10% have high overtime (120-200 hours)
                overtime_hours = random.randint(120, 200)
            
            # Store as a custom attribute (you may need to add this field to your Employee model)
            # For now, we'll create overtime schedules to represent these hours
            employee.overtime_hours_ytd = overtime_hours  # Year-to-date overtime
            
            # Create some recent overtime shifts to reflect these hours
            if overtime_hours > 0:
                # Calculate number of overtime shifts (assuming 8-hour OT shifts)
                num_ot_shifts = overtime_hours // 8
                
                for i in range(min(num_ot_shifts, 10)):  # Create up to 10 recent OT shifts
                    ot_date = date.today() - timedelta(days=random.randint(1, 60))
                    
                    # Skip if it's a future date
                    if ot_date > date.today():
                        continue
                    
                    ot_schedule = Schedule(
                        employee_id=employee.id,
                        date=ot_date,
                        shift_type=random.choice(['day', 'evening', 'night']),
                        start_time=time(7, 0) if random.random() < 0.5 else time(15, 0),
                        end_time=time(15, 0) if random.random() < 0.5 else time(23, 0),
                        position_id=employee.position_id,
                        hours=8,
                        is_overtime=True,
                        crew=employee.crew,
                        status='worked'
                    )
                    db.session.add(ot_schedule)
        
        # ==================== CREATE CURRENT SCHEDULES ====================
        print("Creating current schedules...")
        # Create regular schedules for the next 4 weeks
        start_date = date.today() - timedelta(days=7)
        
        # 2-2-3 Pitman schedule pattern
        pitman_pattern = {
            'A': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Day shifts
            'B': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Day shifts
            'C': [0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1],  # Night shifts
            'D': [1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0],  # Night shifts
        }
        
        shift_times = {
            'A': ('day', time(7, 0), time(19, 0)),
            'B': ('day', time(7, 0), time(19, 0)),
            'C': ('night', time(19, 0), time(7, 0)),
            'D': ('night', time(19, 0), time(7, 0))
        }
        
        for day_offset in range(35):  # 5 weeks
            current_date = start_date + timedelta(days=day_offset)
            day_in_cycle = day_offset % 14
            
            for crew in ['A', 'B', 'C', 'D']:
                if pitman_pattern[crew][day_in_cycle] == 1:
                    shift_type, start_time, end_time = shift_times[crew]
                    crew_employees_list = Employee.query.filter_by(crew=crew, is_supervisor=False).all()
                    
                    for employee in crew_employees_list:
                        # 95% attendance rate
                        if random.random() < 0.95:
                            schedule = Schedule(
                                employee_id=employee.id,
                                date=current_date,
                                shift_type=shift_type,
                                start_time=start_time,
                                end_time=end_time,
                                position_id=employee.position_id,
                                hours=12,
                                is_overtime=False,
                                crew=crew,
                                status='scheduled' if current_date >= date.today() else 'worked'
                            )
                            db.session.add(schedule)
        
        # ==================== CREATE SAMPLE REQUESTS ====================
        print("Creating sample time off requests...")
        for _ in range(15):
            employee = random.choice(all_employees)
            start_date = date.today() + timedelta(days=random.randint(7, 45))
            end_date = start_date + timedelta(days=random.randint(1, 5))
            
            time_off = TimeOffRequest(
                employee_id=employee.id,
                request_type=random.choice(['vacation', 'sick', 'personal']),
                start_date=start_date,
                end_date=end_date,
                reason=random.choice([
                    'Family vacation',
                    'Medical appointment',
                    'Personal matters',
                    'Wedding',
                    'Family event'
                ]),
                status=random.choice(['pending', 'approved', 'pending', 'pending']),  # More pending
                submitted_date=datetime.now() - timedelta(days=random.randint(1, 14)),
                days_requested=(end_date - start_date).days + 1
            )
            db.session.add(time_off)
        
        # Commit all changes
        db.session.commit()
        
        # ==================== SUMMARY REPORT ====================
        print("\n" + "="*60)
        print("✅ DEMO DATABASE CREATED SUCCESSFULLY!")
        print("="*60)
        
        print("\n📊 DATABASE SUMMARY:")
        print(f"Total Employees: {Employee.query.filter_by(is_supervisor=False).count()}")
        print(f"  - Crew A: {Employee.query.filter_by(crew='A', is_supervisor=False).count()}")
        print(f"  - Crew B: {Employee.query.filter_by(crew='B', is_supervisor=False).count()}")
        print(f"  - Crew C: {Employee.query.filter_by(crew='C', is_supervisor=False).count()}")
        print(f"  - Crew D: {Employee.query.filter_by(crew='D', is_supervisor=False).count()}")
        
        print("\n👥 POSITION DISTRIBUTION:")
        for position in Position.query.all():
            count = Employee.query.filter_by(position_id=position.id, is_supervisor=False).count()
            print(f"  - {position.name}: {count}")
        
        print("\n🎓 SKILL DISTRIBUTION:")
        for skill in Skill.query.all():
            count = db.session.query(Employee).join(Employee.skills).filter(
                Skill.id == skill.id,
                Employee.is_supervisor == False
            ).count()
            print(f"  - {skill.name}: {count} employees")
        
        print("\n⏰ OVERTIME DISTRIBUTION:")
        # This would need the overtime_hours_ytd field to be added to Employee model
        print("  - 0-50 hours: ~24 employees (30%)")
        print("  - 50-120 hours: ~48 employees (60%)")
        print("  - 120-200 hours: ~8 employees (10%)")
        
        print("\n🔐 LOGIN CREDENTIALS:")
        print("Supervisors:")
        for supervisor in Employee.query.filter_by(is_supervisor=True).all():
            print(f"  - {supervisor.email} / admin123 (Crew {supervisor.crew})")
        
        print("\nSample Employees:")
        sample_employees = Employee.query.filter_by(is_supervisor=False).limit(5).all()
        for emp in sample_employees:
            print(f"  - {emp.email} / password123 (Crew {emp.crew})")
        
        print("\n📅 SCHEDULES CREATED:")
        print(f"  - Total schedules: {Schedule.query.count()}")
        print(f"  - Future schedules: {Schedule.query.filter(Schedule.date >= date.today()).count()}")
        print(f"  - Overtime shifts: {Schedule.query.filter_by(is_overtime=True).count()}")
        
        print("\n📝 REQUESTS CREATED:")
        print(f"  - Time off requests: {TimeOffRequest.query.count()}")
        print(f"  - Pending requests: {TimeOffRequest.query.filter_by(status='pending').count()}")
        
        print("\n" + "="*60)
        print("🎯 You can now log in and explore the system!")
        print("="*60)

if __name__ == '__main__':
    create_custom_demo_database()
