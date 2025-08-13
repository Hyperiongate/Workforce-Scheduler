# init_communications_db.py
"""
Initialize the communications system database tables and default data
Run this after adding the models and running migrations
"""

from app import app, db
from models import MessageCategory, CommunicationMessage, Employee
from datetime import datetime, timedelta

def init_message_categories():
    """Create default message categories"""
    categories = [
        {
            'name': 'plantwide',
            'display_name': 'Plantwide Communications',
            'description': 'Company-wide announcements and updates',
            'icon': 'bi-megaphone-fill',
            'color': '#6f42c1',  # Purple
            'require_supervisor': True,
            'require_department': None,
            'require_position': None
        },
        {
            'name': 'hr',
            'display_name': 'HR Communications',
            'description': 'Benefits, policies, and employee information',
            'icon': 'bi-people-fill',
            'color': '#e83e8c',  # Pink
            'require_supervisor': False,
            'require_department': 'HR',
            'require_position': None
        },
        {
            'name': 'maintenance',
            'display_name': 'Maintenance Communications',
            'description': 'Equipment updates, maintenance schedules, and technical notices',
            'icon': 'bi-tools',
            'color': '#0dcaf0',  # Cyan/Blue
            'require_supervisor': False,
            'require_department': 'Maintenance',
            'require_position': None
        },
        {
            'name': 'hourly',
            'display_name': 'Hourly Employee Communications',
            'description': 'Updates and information for hourly workforce',
            'icon': 'bi-clock-fill',
            'color': '#198754',  # Green
            'require_supervisor': True,
            'require_department': None,
            'require_position': None
        }
    ]
    
    for cat_data in categories:
        # Check if category already exists
        existing = MessageCategory.query.filter_by(name=cat_data['name']).first()
        if not existing:
            category = MessageCategory(**cat_data)
            db.session.add(category)
            print(f"✅ Created category: {cat_data['display_name']}")
        else:
            print(f"ℹ️  Category already exists: {cat_data['display_name']}")
    
    db.session.commit()
    print("✅ Message categories initialized")

def create_sample_messages():
    """Create some sample messages for testing"""
    # Get a supervisor user
    supervisor = Employee.query.filter_by(is_supervisor=True).first()
    if not supervisor:
        print("⚠️  No supervisor found, skipping sample messages")
        return
    
    # Get an HR user (or use supervisor)
    hr_user = Employee.query.filter_by(department='HR').first() or supervisor
    
    # Get a maintenance user (or use supervisor)
    maint_user = Employee.query.filter_by(department='Maintenance').first() or supervisor
    
    sample_messages = [
        {
            'category': 'plantwide',
            'subject': 'Welcome to the New Communications System!',
            'content': '''Dear Team,

We are excited to introduce our new communications system! This platform will serve as our central hub for all company-wide announcements, department updates, and important information.

Key features include:
• Organized categories for different types of communications
• Read receipts to track message engagement
• File attachment support
• Message templates for recurring announcements
• Analytics dashboard for supervisors

Please check this portal regularly for important updates. If you have any questions, please contact your supervisor.

Best regards,
Management Team''',
            'priority': 'high',
            'sender_id': supervisor.id,
            'target_audience': 'all',
            'is_pinned': True
        },
        {
            'category': 'hr',
            'subject': 'Annual Benefits Enrollment Period Opens Next Week',
            'content': '''All Employees,

The annual benefits enrollment period will begin next Monday and run through the end of the month. This is your opportunity to:

• Review and update your health insurance coverage
• Adjust your 401(k) contributions
• Update beneficiary information
• Enroll in or change voluntary benefits

Information packets will be distributed to all employees by Friday. HR will be hosting information sessions on:
- Tuesday 10am (Conference Room A)
- Thursday 2pm (Conference Room B)
- Friday 8am (Virtual - link to follow)

Please don't hesitate to reach out with any questions.

HR Department''',
            'priority': 'high',
            'sender_id': hr_user.id,
            'target_audience': 'all',
            'expires_at': datetime.utcnow() + timedelta(days=30)
        },
        {
            'category': 'maintenance',
            'subject': 'Scheduled Maintenance: Production Line 2',
            'content': '''Attention All Shifts,

Please be advised that Production Line 2 will be undergoing scheduled maintenance this weekend:

Start: Saturday 6:00 AM
End: Sunday 6:00 PM (estimated)

Impact:
- Line 2 will be completely offline during this period
- Additional workload will be distributed to Lines 1 and 3
- Overtime may be required for affected positions

Please coordinate with your supervisors for adjusted work assignments.

Thank you for your cooperation.

Maintenance Department''',
            'priority': 'urgent',
            'sender_id': maint_user.id,
            'target_audience': 'all'
        },
        {
            'category': 'hourly',
            'subject': 'Overtime Opportunities Available This Week',
            'content': '''Hourly Team Members,

We have several overtime opportunities available for this week:

Wednesday Evening Shift:
- 3 positions in Packaging
- 2 positions in Shipping

Saturday Day Shift:
- 4 positions in Production
- 1 position in Quality Control

If interested, please notify your supervisor by end of shift today. Assignments will be made based on seniority and current overtime balance.

Thank you!''',
            'priority': 'normal',
            'sender_id': supervisor.id,
            'target_audience': 'all'
        }
    ]
    
    for msg_data in sample_messages:
        # Check if similar message exists
        existing = CommunicationMessage.query.filter_by(
            subject=msg_data['subject']
        ).first()
        
        if not existing:
            message = CommunicationMessage(**msg_data)
            db.session.add(message)
            print(f"✅ Created sample message: {msg_data['subject'][:50]}...")
        else:
            print(f"ℹ️  Message already exists: {msg_data['subject'][:50]}...")
    
    db.session.commit()
    print("✅ Sample messages created")

def main():
    """Run initialization"""
    with app.app_context():
        print("🚀 Initializing Communications System...")
        print("-" * 50)
        
        # Initialize categories
        init_message_categories()
        print()
        
        # Create sample messages
        create_sample_messages()
        print()
        
        print("-" * 50)
        print("✅ Communications system initialization complete!")
        print("🌐 Visit /communications to see the new system")

if __name__ == "__main__":
    main()
