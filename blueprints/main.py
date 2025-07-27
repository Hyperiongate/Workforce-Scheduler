# ========================================
# main.py - Complete Overtime Management Route
# ========================================

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
from models import db, Employee, Position, OvertimeHistory

main = Blueprint('main', __name__)

@main.route('/overtime-management')
@login_required
def overtime_management():
    # Get filter parameters
    search_term = request.args.get('search', '')
    crew_filter = request.args.get('crew', '')
    position_filter = request.args.get('position', '')
    ot_range_filter = request.args.get('ot_range', '')
    page = request.args.get('page', 1, type=int)
    
    # Get sorting parameters
    sort_params = []
    for i in range(1, 5):
        sort_field = request.args.get(f'sort{i}')
        sort_dir = request.args.get(f'dir{i}', 'asc')
        if sort_field:
            sort_params.append((sort_field, sort_dir))
    
    # Base query
    query = Employee.query.filter(Employee.id != current_user.id)
    
    # Apply search filter
    if search_term:
        search_pattern = f'%{search_term}%'
        query = query.filter(
            or_(
                Employee.name.ilike(search_pattern),
                Employee.employee_id.ilike(search_pattern)
            )
        )
    
    # Apply crew filter
    if crew_filter:
        query = query.filter(Employee.crew == crew_filter)
    
    # Apply position filter
    if position_filter:
        try:
            position_id = int(position_filter)
            query = query.filter(Employee.position_id == position_id)
        except ValueError:
            pass
    
    # Apply overtime range filter using OvertimeHistory
    if ot_range_filter:
        # Subquery to get 13-week overtime totals
        thirteen_weeks_ago = datetime.now().date() - timedelta(weeks=13)
        overtime_subquery = db.session.query(
            OvertimeHistory.employee_id,
            func.sum(OvertimeHistory.overtime_hours).label('total_ot')
        ).filter(
            OvertimeHistory.week_start_date >= thirteen_weeks_ago
        ).group_by(OvertimeHistory.employee_id).subquery()
        
        # Join with subquery
        query = query.outerjoin(
            overtime_subquery,
            Employee.id == overtime_subquery.c.employee_id
        )
        
        if ot_range_filter == '0-50':
            query = query.filter(
                or_(
                    overtime_subquery.c.total_ot.between(0, 50),
                    overtime_subquery.c.total_ot.is_(None)
                )
            )
        elif ot_range_filter == '50-100':
            query = query.filter(overtime_subquery.c.total_ot.between(50, 100))
        elif ot_range_filter == '100-150':
            query = query.filter(overtime_subquery.c.total_ot.between(100, 150))
        elif ot_range_filter == '150+':
            query = query.filter(overtime_subquery.c.total_ot > 150)
    
    # Apply sorting
    for sort_field, sort_dir in sort_params:
        if sort_field == 'crew':
            order_column = Employee.crew
        elif sort_field == 'jobtitle':
            if 'position' not in str(query):
                query = query.outerjoin(Position, Employee.position_id == Position.id)
            order_column = Position.name
        elif sort_field == 'seniority':
            order_column = Employee.hire_date
        elif sort_field == 'overtime':
            # Sort by 13-week total from property
            continue  # Handle after query execution
        else:
            continue
        
        if sort_dir == 'desc':
            order_column = order_column.desc()
        else:
            order_column = order_column.asc()
        
        query = query.order_by(order_column)
    
    # Default sort by name if no sorting specified
    if not sort_params:
        query = query.order_by(Employee.name)
    
    # Ensure position is loaded
    query = query.options(db.joinedload(Employee.position))
    
    # Execute query to get all employees
    all_employees = query.all()
    
    # If sorting by overtime, sort in memory after calculating totals
    if any(sort[0] == 'overtime' for sort in sort_params):
        sort_dir = next((sort[1] for sort in sort_params if sort[0] == 'overtime'), 'asc')
        reverse = (sort_dir == 'desc')
        all_employees.sort(key=lambda e: e.last_13_weeks_overtime, reverse=reverse)
    
    # Manual pagination
    per_page = 20
    total_count = len(all_employees)
    total_pages = (total_count + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    employees = all_employees[start_idx:end_idx]
    
    # Calculate statistics
    total_overtime_hours = 0
    employees_with_overtime = 0
    high_overtime_employees = []
    
    for emp in all_employees:
        ot_hours = emp.last_13_weeks_overtime
        total_overtime_hours += ot_hours
        
        if ot_hours > 0:
            employees_with_overtime += 1
        
        if ot_hours > 200:
            high_overtime_employees.append(emp)
    
    if all_employees:
        avg_overtime = round(total_overtime_hours / len(all_employees))
    else:
        avg_overtime = 0
    
    high_overtime_count = len(high_overtime_employees)
    
    # Get all positions
    positions = Position.query.order_by(Position.name).all()
    
    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(weeks=13)
    
    return render_template('overtime_management.html',
        employees=employees,
        positions=positions,
        total_overtime_hours=int(total_overtime_hours),
        employees_with_overtime=employees_with_overtime,
        avg_overtime=avg_overtime,
        high_overtime_count=high_overtime_count,
        high_overtime_employees=high_overtime_employees,
        start_date=start_date,
        end_date=end_date,
        total_pages=total_pages,
        page=page,
        search_term=search_term,
        crew_filter=crew_filter,
        position_filter=position_filter,
        ot_range_filter=ot_range_filter
    )

@main.route('/export-overtime-excel')
@login_required
def export_overtime_excel():
    """Export overtime data to Excel"""
    try:
        # Get filter parameters
        search_term = request.args.get('search', '')
        crew_filter = request.args.get('crew', '')
        position_filter = request.args.get('position', '')
        ot_range_filter = request.args.get('ot_range', '')
        
        # Build query with filters
        query = Employee.query.filter(Employee.id != current_user.id)
        
        if search_term:
            search_pattern = f'%{search_term}%'
            query = query.filter(
                or_(
                    Employee.name.ilike(search_pattern),
                    Employee.employee_id.ilike(search_pattern)
                )
            )
        
        if crew_filter:
            query = query.filter(Employee.crew == crew_filter)
        
        if position_filter:
            try:
                position_id = int(position_filter)
                query = query.filter(Employee.position_id == position_id)
            except ValueError:
                pass
        
        # Get all matching employees
        employees = query.options(db.joinedload(Employee.position)).all()
        
        # Filter by overtime range in memory
        if ot_range_filter:
            filtered_employees = []
            for emp in employees:
                ot_total = emp.last_13_weeks_overtime
                if ot_range_filter == '0-50' and 0 <= ot_total <= 50:
                    filtered_employees.append(emp)
                elif ot_range_filter == '50-100' and 50 < ot_total <= 100:
                    filtered_employees.append(emp)
                elif ot_range_filter == '100-150' and 100 < ot_total <= 150:
                    filtered_employees.append(emp)
                elif ot_range_filter == '150+' and ot_total > 150:
                    filtered_employees.append(emp)
            employees = filtered_employees
        
        # Create DataFrame
        data = []
        for emp in employees:
            # Get years employed
            years_employed = 0
            if emp.hire_date:
                delta = datetime.now().date() - emp.hire_date
                years_employed = delta.days // 365
            
            data.append({
                'Employee ID': emp.employee_id,
                'Name': emp.name,
                'Crew': emp.crew or '',
                'Position': emp.position.name if emp.position else '',
                'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
                'Years Employed': years_employed,
                'Current Week OT': emp.current_week_overtime,
                '13-Week Total OT': emp.last_13_weeks_overtime,
                'Weekly Average OT': emp.average_weekly_overtime,
                'Trend': emp.overtime_trend
            })
        
        df = pd.DataFrame(data)
        
        # Create Excel file
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Overtime Report', index=False)
            
            workbook = writer.book
            worksheet = writer.sheets['Overtime Report']
            
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#11998e',
                'font_color': '#FFFFFF',
                'border': 1
            })
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:B', 25)
            worksheet.set_column('C:C', 8)
            worksheet.set_column('D:D', 20)
            worksheet.set_column('E:E', 12)
            worksheet.set_column('F:J', 15)
        
        output.seek(0)
        
        filename = f'overtime_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('main.overtime_management'))


# ========================================
# employee_import.py - Employee Import with Overtime
# ========================================

from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import pandas as pd
from datetime import datetime, timedelta
import io

employee_import = Blueprint('employee_import', __name__)

@employee_import.route('/upload-employees', methods=['GET', 'POST'])
@login_required
def upload_employees():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and file.filename.endswith(('.xlsx', '.xls')):
            try:
                # Read Excel file
                df = pd.read_excel(file)
                
                # Validate required columns
                required_columns = ['Employee ID', 'Name', 'Email', 'Crew']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    flash(f'Missing required columns: {", ".join(missing_columns)}', 'error')
                    return redirect(request.url)
                
                # Get or create positions
                position_map = {}
                if 'Position' in df.columns:
                    unique_positions = df['Position'].dropna().unique()
                    for pos_name in unique_positions:
                        position = Position.query.filter_by(name=pos_name).first()
                        if not position:
                            position = Position(name=pos_name)
                            db.session.add(position)
                            db.session.flush()
                        position_map[pos_name] = position.id
                
                # Process employees
                employees_added = 0
                employees_updated = 0
                
                for _, row in df.iterrows():
                    # Skip invalid rows
                    if pd.isna(row['Employee ID']) or pd.isna(row['Name']) or pd.isna(row['Email']):
                        continue
                    
                    # Check if employee exists
                    employee = Employee.query.filter_by(employee_id=str(row['Employee ID'])).first()
                    
                    if not employee:
                        employee = Employee(
                            employee_id=str(row['Employee ID']),
                            name=row['Name'],
                            email=row['Email'].lower(),
                            password_hash=generate_password_hash('password123')
                        )
                        employees_added += 1
                    else:
                        employee.name = row['Name']
                        employee.email = row['Email'].lower()
                        employees_updated += 1
                    
                    # Update crew
                    if 'Crew' in df.columns and not pd.isna(row['Crew']):
                        employee.crew = str(row['Crew']).upper()
                    
                    # Update position
                    if 'Position' in df.columns and not pd.isna(row['Position']):
                        employee.position_id = position_map.get(row['Position'])
                    
                    # Update hire date
                    if 'Hire Date' in df.columns and not pd.isna(row['Hire Date']):
                        try:
                            if isinstance(row['Hire Date'], str):
                                employee.hire_date = datetime.strptime(row['Hire Date'], '%Y-%m-%d').date()
                            else:
                                employee.hire_date = pd.to_datetime(row['Hire Date']).date()
                        except:
                            pass
                    
                    # Update supervisor status
                    if 'Is Supervisor' in df.columns:
                        employee.is_supervisor = bool(row['Is Supervisor'])
                    
                    db.session.add(employee)
                    db.session.flush()
                    
                    # PROCESS OVERTIME DATA
                    # Map overtime columns to OvertimeHistory records
                    
                    # Current week overtime
                    current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
                    if 'Current Week OT' in df.columns and not pd.isna(row['Current Week OT']):
                        update_overtime_record(employee.id, current_week_start, float(row['Current Week OT']))
                    
                    # Process weekly overtime columns
                    for week_num in range(1, 14):
                        col_names = [f'Week {week_num} OT', f'Week{week_num}OT', f'Week {week_num} Overtime']
                        week_start = current_week_start - timedelta(weeks=week_num)
                        
                        for col_name in col_names:
                            if col_name in df.columns and not pd.isna(row[col_name]):
                                update_overtime_record(employee.id, week_start, float(row[col_name]))
                                break
                
                db.session.commit()
                
                flash(f'Successfully processed {employees_added} new employees and updated {employees_updated} existing employees', 'success')
                return redirect(url_for('main.overtime_management'))
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error processing file: {str(e)}', 'error')
                return redirect(request.url)
        else:
            flash('Please upload a valid Excel file (.xlsx or .xls)', 'error')
            return redirect(request.url)
    
    # GET request
    employee_count = Employee.query.filter(Employee.id != current_user.id).count()
    return render_template('upload_employees.html', employee_count=employee_count)

def update_overtime_record(employee_id, week_start_date, overtime_hours):
    """Update or create overtime record"""
    ot_record = OvertimeHistory.query.filter_by(
        employee_id=employee_id,
        week_start_date=week_start_date
    ).first()
    
    if ot_record:
        ot_record.overtime_hours = overtime_hours
        ot_record.total_hours = ot_record.regular_hours + overtime_hours
    else:
        ot_record = OvertimeHistory(
            employee_id=employee_id,
            week_start_date=week_start_date,
            regular_hours=40,  # Default regular hours
            overtime_hours=overtime_hours,
            total_hours=40 + overtime_hours
        )
        db.session.add(ot_record)

@employee_import.route('/download-employee-template')
@login_required
def download_employee_template():
    # Create template
    template_data = {
        'Employee ID': ['EMP001', 'EMP002', 'EMP003'],
        'Name': ['John Smith', 'Jane Doe', 'Bob Johnson'],
        'Email': ['john.smith@company.com', 'jane.doe@company.com', 'bob.johnson@company.com'],
        'Crew': ['A', 'B', 'C'],
        'Position': ['Operator', 'Technician', 'Supervisor'],
        'Hire Date': ['2020-01-15', '2019-05-20', '2018-11-10'],
        'Is Supervisor': [False, False, True],
        'Current Week OT': [8.5, 12.0, 0],
        'Week 1 OT': [10.0, 8.0, 5.5],
        'Week 2 OT': [7.5, 15.0, 3.0],
        'Week 3 OT': [9.0, 11.5, 4.0],
        'Week 4 OT': [8.0, 13.0, 3.5],
        'Week 5 OT': [11.0, 10.5, 4.5],
        'Week 6 OT': [7.0, 14.0, 2.5],
        'Week 7 OT': [9.5, 12.5, 5.0],
        'Week 8 OT': [8.5, 11.0, 3.5],
        'Week 9 OT': [10.0, 13.5, 4.0],
        'Week 10 OT': [7.5, 12.0, 3.0],
        'Week 11 OT': [9.0, 11.0, 4.5],
        'Week 12 OT': [5.0, 12.0, 2.5],
        'Week 13 OT': [8.5, 12.0, 0]
    }
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Employees', index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['Employees']
        
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#4472C4',
            'font_color': '#FFFFFF',
            'border': 1
        })
        
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        worksheet.set_column('A:A', 12)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 25)
        worksheet.set_column('D:D', 8)
        worksheet.set_column('E:E', 15)
        worksheet.set_column('F:F', 12)
        worksheet.set_column('G:G', 12)
        worksheet.set_column('H:U', 10)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='employee_upload_template.xlsx'
    )

@employee_import.route('/export-current-employees')
@login_required
def export_current_employees():
    employees = Employee.query.filter(Employee.id != current_user.id).all()
    
    data = []
    for emp in employees:
        row = {
            'Employee ID': emp.employee_id,
            'Name': emp.name,
            'Email': emp.email,
            'Crew': emp.crew or '',
            'Position': emp.position.name if emp.position else '',
            'Hire Date': emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '',
            'Is Supervisor': emp.is_supervisor,
            'Current Week OT': emp.current_week_overtime
        }
        
        # Add 13 weeks of overtime data
        current_week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
        for week_num in range(1, 14):
            week_start = current_week_start - timedelta(weeks=week_num)
            week_ot = emp.get_overtime_for_week(week_start)
            row[f'Week {week_num} OT'] = week_ot
        
        data.append(row)
    
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Current Employees', index=False)
    
    output.seek(0)
    
    filename = f'current_employees_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


# ========================================
# app.py - Main Flask Application
# ========================================

from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = 'your-secret-key-here'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://username:password@localhost/workforce_db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return Employee.query.get(int(user_id))
    
    # Register blueprints
    app.register_blueprint(main)
    app.register_blueprint(employee_import)
    
    with app.app_context():
        db.create_all()
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
