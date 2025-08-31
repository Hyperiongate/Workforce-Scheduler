# Add this complete route to your blueprints/main.py file

@main_bp.route('/crew-management')
@login_required
@supervisor_required
def crew_management():
    """Interactive crew management with drag-and-drop interface"""
    try:
        # Get all active employees with their related data
        employees = Employee.query.filter_by(is_active=True).options(
            db.joinedload(Employee.position),
            db.joinedload(Employee.skills)
        ).all()
        
        # Organize employees by crew
        employees_by_crew = {
            'A': [],
            'B': [],
            'C': [],
            'D': [],
            'Unassigned': []
        }
        
        crew_counts = {
            'A': 0,
            'B': 0,
            'C': 0,
            'D': 0,
            'Unassigned': 0
        }
        
        total_employees = 0
        
        # Calculate overtime for each employee (last 13 weeks)
        end_date = date.today()
        start_date = end_date - timedelta(weeks=13)
        
        for employee in employees:
            # Calculate years employed
            years_employed = 0
            if hasattr(employee, 'hire_date') and employee.hire_date:
                years_employed = (date.today() - employee.hire_date).days // 365
            
            # Get overtime hours
            overtime_records = OvertimeHistory.query.filter(
                OvertimeHistory.employee_id == employee.id,
                OvertimeHistory.week_ending >= start_date,
                OvertimeHistory.week_ending <= end_date
            ).all()
            
            overtime_hours = sum(record.overtime_hours or 0 for record in overtime_records)
            
            # Create enhanced employee data
            employee_data = {
                'id': employee.id,
                'employee_id': employee.employee_id,
                'name': employee.name,
                'first_name': employee.first_name,
                'last_name': employee.last_name,
                'crew': employee.crew,
                'position': employee.position,
                'skills': getattr(employee, 'skills', []),
                'years_employed': years_employed,
                'overtime_hours': overtime_hours,
                'performance_score': getattr(employee, 'performance_score', 85),  # Default score
                'hire_date': getattr(employee, 'hire_date', None)
            }
            
            # Assign to crew
            crew = employee.crew if employee.crew in ['A', 'B', 'C', 'D'] else 'Unassigned'
            employees_by_crew[crew].append(employee_data)
            crew_counts[crew] += 1
            total_employees += 1
        
        # Calculate balance score
        crew_sizes = [crew_counts[crew] for crew in ['A', 'B', 'C', 'D']]
        if sum(crew_sizes) > 0:
            average_size = sum(crew_sizes) / 4
            variance = sum((size - average_size) ** 2 for size in crew_sizes) / 4
            balance_score = max(0, 100 - (variance / max(average_size, 1) * 100))
        else:
            balance_score = 100
        
        # Get skills distribution
        skills_distribution = calculate_skills_distribution(employees_by_crew)
        
        # Calculate skills coverage
        skills_coverage = calculate_skills_coverage(skills_distribution)
        
        # Calculate workload variance
        workload_variance = calculate_workload_variance(employees_by_crew)
        
        return render_template(
            'crew_management.html',
            employees_by_crew=employees_by_crew,
            crew_counts=crew_counts,
            total_employees=total_employees,
            balance_score=int(balance_score),
            skills_distribution=skills_distribution,
            skills_coverage=int(skills_coverage),
            workload_variance=workload_variance
        )
        
    except Exception as e:
        logger.error(f"Error in crew management: {str(e)}")
        flash('Error loading crew management page. Please try again.', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/crew-management/save', methods=['POST'])
@login_required
@supervisor_required
def save_crew_assignments():
    """Save crew assignment changes"""
    try:
        data = request.get_json()
        assignments = data.get('assignments', {})
        changes = data.get('changes', [])
        
        if not assignments:
            return jsonify({'success': False, 'error': 'No assignments provided'})
        
        # Track changes for logging
        updated_count = 0
        errors = []
        
        # Process each crew's assignments
        for crew, employee_ids in assignments.items():
            crew_value = crew if crew in ['A', 'B', 'C', 'D'] else None
            
            for employee_id in employee_ids:
                try:
                    employee = Employee.query.filter_by(employee_id=employee_id).first()
                    if employee:
                        old_crew = employee.crew
                        employee.crew = crew_value
                        
                        if old_crew != crew_value:
                            updated_count += 1
                            logger.info(f"Updated {employee_id} crew: {old_crew} -> {crew_value}")
                    else:
                        errors.append(f"Employee {employee_id} not found")
                        
                except Exception as e:
                    errors.append(f"Error updating {employee_id}: {str(e)}")
        
        # Commit changes
        db.session.commit()
        
        # Log the crew management action
        try:
            from models import AuditLog
            audit_log = AuditLog(
                user_id=current_user.id,
                action='crew_management_update',
                details=f"Updated {updated_count} employee crew assignments",
                timestamp=datetime.utcnow()
            )
            db.session.add(audit_log)
            db.session.commit()
        except:
            pass  # Audit log is optional
        
        return jsonify({
            'success': True,
            'updated_count': updated_count,
            'errors': errors
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving crew assignments: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def calculate_skills_distribution(employees_by_crew):
    """Calculate how skills are distributed across crews"""
    skills_data = {}
    
    # Get all unique skills
    all_skills = set()
    for crew_employees in employees_by_crew.values():
        for employee in crew_employees:
            for skill in employee.get('skills', []):
                all_skills.add(skill.name if hasattr(skill, 'name') else str(skill))
    
    # Count skills per crew
    for skill_name in all_skills:
        crew_counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        
        for crew, employees in employees_by_crew.items():
            if crew in ['A', 'B', 'C', 'D']:
                for employee in employees:
                    employee_skills = [s.name if hasattr(s, 'name') else str(s) 
                                     for s in employee.get('skills', [])]
                    if skill_name in employee_skills:
                        crew_counts[crew] += 1
        
        # Calculate balance rating
        total_with_skill = sum(crew_counts.values())
        if total_with_skill == 0:
            balance_percentage = 0
            balance_rating = 'poor'
        else:
            # Calculate distribution balance (how evenly distributed)
            counts = list(crew_counts.values())
            max_count = max(counts)
            min_count = min(counts)
            
            if max_count == 0:
                balance_percentage = 0
                balance_rating = 'poor'
            else:
                balance_percentage = int((min_count / max_count) * 100)
                if balance_percentage >= 80:
                    balance_rating = 'excellent'
                elif balance_percentage >= 60:
                    balance_rating = 'good'
                else:
                    balance_rating = 'poor'
        
        skills_data[skill_name] = {
            'name': skill_name,
            'crew_counts': crew_counts,
            'total': total_with_skill,
            'balance_percentage': balance_percentage,
            'balance_rating': balance_rating
        }
    
    # Convert to list format for template
    skills_list = []
    for skill_name, skill_data in skills_data.items():
        skills_list.append(skill_data)
    
    return skills_list

def calculate_skills_coverage(skills_distribution):
    """Calculate overall skills coverage percentage"""
    if not skills_distribution:
        return 100
    
    total_balance = sum(skill['balance_percentage'] for skill in skills_distribution)
    return total_balance / len(skills_distribution) if skills_distribution else 100

def calculate_workload_variance(employees_by_crew):
    """Calculate workload variance across crews"""
    crew_workloads = []
    
    for crew in ['A', 'B', 'C', 'D']:
        employees = employees_by_crew.get(crew, [])
        total_overtime = sum(emp.get('overtime_hours', 0) for emp in employees)
        avg_overtime = total_overtime / len(employees) if employees else 0
        crew_workloads.append(avg_overtime)
    
    if not crew_workloads:
        return 0.0
    
    mean_workload = sum(crew_workloads) / len(crew_workloads)
    variance = sum((workload - mean_workload) ** 2 for workload in crew_workloads) / len(crew_workloads)
    
    return round(variance, 2)

# Additional helper function for auto-balancing
@main_bp.route('/crew-management/auto-balance', methods=['POST'])
@login_required
@supervisor_required
def auto_balance_crews():
    """Automatically balance crews based on skills and workload"""
    try:
        # Get all active employees
        employees = Employee.query.filter_by(is_active=True).options(
            db.joinedload(Employee.position),
            db.joinedload(Employee.skills)
        ).all()
        
        # Simple auto-balance algorithm
        # In practice, this would be much more sophisticated
        employees_list = list(employees)
        crew_assignments = {'A': [], 'B': [], 'C': [], 'D': []}
        
        # Distribute employees evenly
        for i, employee in enumerate(employees_list):
            crew = ['A', 'B', 'C', 'D'][i % 4]
            crew_assignments[crew].append(employee.employee_id)
        
        return jsonify({
            'success': True,
            'assignments': crew_assignments,
            'message': f'Auto-balanced {len(employees_list)} employees across 4 crews'
        })
        
    except Exception as e:
        logger.error(f"Error in auto-balance: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
