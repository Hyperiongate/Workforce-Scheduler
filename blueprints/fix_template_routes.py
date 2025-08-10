# fix_template_routes.py - Fix incorrect route references in templates
"""
Fixes route references in templates that don't match actual blueprint routes
"""

import os
import re

def fix_dashboard_template():
    """Fix route references in dashboard.html"""
    dashboard_path = 'templates/dashboard.html'
    
    if not os.path.exists(dashboard_path):
        print(f"✗ {dashboard_path} not found")
        return
    
    # Read the current content
    with open(dashboard_path, 'r') as f:
        content = f.read()
    
    # Define replacements
    replacements = [
        # Fix vacation_calendar route
        (r"url_for\('vacation_calendar'\)", "url_for('supervisor.vacation_calendar')"),
        
        # Fix other common route issues
        (r"url_for\('overtime_management'\)", "url_for('supervisor.overtime_management')"),
        (r"url_for\('schedule_view'\)", "url_for('supervisor.schedule_view')"),
        (r"url_for\('employee_management'\)", "url_for('supervisor.employee_management')"),
        
        # If routes don't exist, comment them out
        (r'<a href="{{ url_for\(\'supervisor\.vacation_calendar\'\) }}"', 
         '<!-- Vacation Calendar not implemented yet\n<a href="#"'),
        (r'</a>(\s*<!-- Vacation Calendar button -->)', 
         '</a>\n-->')
    ]
    
    # Apply replacements
    original = content
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    # Check if vacation_calendar route exists, if not, comment out the link
    if "url_for('supervisor.vacation_calendar')" in content:
        # Check if the route actually exists by looking for it in supervisor.py
        supervisor_path = 'blueprints/supervisor.py'
        if os.path.exists(supervisor_path):
            with open(supervisor_path, 'r') as f:
                supervisor_content = f.read()
            
            if 'def vacation_calendar' not in supervisor_content:
                # Route doesn't exist, comment out the link
                content = re.sub(
                    r'<a href="{{ url_for\(\'supervisor\.vacation_calendar\'\) }}"[^>]*>.*?</a>',
                    '<!-- Vacation Calendar not implemented yet -->',
                    content,
                    flags=re.DOTALL
                )
    
    # Write back if changes were made
    if content != original:
        with open(dashboard_path, 'w') as f:
            f.write(content)
        print(f"✓ Fixed route references in {dashboard_path}")
    else:
        print(f"✓ No changes needed in {dashboard_path}")

def add_vacation_calendar_route():
    """Add the missing vacation_calendar route to supervisor.py"""
    supervisor_path = 'blueprints/supervisor.py'
    
    if not os.path.exists(supervisor_path):
        print(f"✗ {supervisor_path} not found")
        return
    
    with open(supervisor_path, 'r') as f:
        content = f.read()
    
    # Check if route already exists
    if 'def vacation_calendar' in content:
        print("✓ vacation_calendar route already exists")
        return
    
    # Add the route before the last line or at the end
    vacation_calendar_route = '''
@supervisor_bp.route('/supervisor/vacation-calendar')
@login_required
@supervisor_required
def vacation_calendar():
    """Display vacation calendar view"""
    try:
        # Get all approved time off requests
        time_off_requests = TimeOffRequest.query.filter_by(
            status='approved'
        ).all()
        
        # Get current month data
        today = date.today()
        
        return render_template('vacation_calendar.html',
                             time_off_requests=time_off_requests,
                             today=today)
    except Exception as e:
        logger.error(f"Error loading vacation calendar: {e}")
        flash('Error loading vacation calendar', 'danger')
        return redirect(url_for('supervisor.dashboard'))
'''
    
    # Insert before the last few lines
    lines = content.split('\n')
    
    # Find a good place to insert (before any closing code)
    insert_index = len(lines) - 1
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].strip() and not lines[i].startswith('#'):
            insert_index = i + 1
            break
    
    # Insert the new route
    lines.insert(insert_index, vacation_calendar_route)
    
    # Write back
    with open(supervisor_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"✓ Added vacation_calendar route to {supervisor_path}")

def main():
    """Run all fixes"""
    print("Fixing template route references...\n")
    
    # Fix dashboard template
    fix_dashboard_template()
    
    # Add missing route
    add_vacation_calendar_route()
    
    print("\n✓ Template fixes complete!")
    print("\nNote: If vacation_calendar.html doesn't exist, create it or comment out the link in dashboard.html")

if __name__ == "__main__":
    main()
