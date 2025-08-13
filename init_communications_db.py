# init_communications_db.py
from app import app, db
from models import CommunicationCategory, CommunicationMessage, Employee
from datetime import datetime, timedelta

def init_communications_system():
    """Initialize the communications system with categories and sample messages"""
    with app.app_context():
        try:
            print("Initializing Communications System...")
            print("=" * 50)
            
            # Check if categories already exist
            existing = CommunicationCategory.query.first()
            if existing:
                print("✓ Communications system already initialized")
                return
            
            # Create default categories
            categories = [
                {
                    'name': 'Plant-wide Announcements',
                    'description': 'Important announcements affecting all employees',
                    'icon': 'bi-megaphone',
                    'color': 'danger'
                },
                {
                    'name': 'HR Updates',
                    'description': 'Human resources updates, policies, and benefits information',
                    'icon': 'bi-people',
                    'color': 'primary'
                },
                {
                    'name': 'Maintenance Notices',
                    'description': 'Equipment maintenance schedules and facility updates',
                    'icon': 'bi-tools',
                    'color': 'warning'
                },
                {
                    'name': 'Hourly Employee Announcements',
                    'description': 'Information specific to hourly workforce',
                    'icon': 'bi-clock',
                    'color': 'info'
                }
            ]
            
            created_categories = {}
            for cat_data in categories:
                category = CommunicationCategory(**cat_data)
                db.session.add(category)
                db.session.flush()  # Get the ID
                created_categories[cat_data['name']] = category
                print(f"✓ Created category: {cat_data['name']}")
            
            # Create sample messages
            admin = Employee.query.filter_by(is_supervisor=True).first()
            if admin:
                # Plant-wide announcement
                msg1 = CommunicationMessage(
                    category_id=created_categories['Plant-wide Announcements'].id,
                    author_id=admin.id,
                    title='Welcome to the New Communications System',
                    content="""
                    <p>We are excited to launch our new communications system!</p>
                    <p>This system will help us share important information more effectively:</p>
                    <ul>
                        <li>Plant-wide announcements</li>
                        <li>HR updates and policy changes</li>
                        <li>Maintenance schedules</li>
                        <li>Crew-specific information</li>
                    </ul>
                    <p>Please check this system regularly for important updates.</p>
                    """,
                    priority='high',
                    is_pinned=True,
                    target_all=True
                )
                db.session.add(msg1)
                
                # HR Update
                msg2 = CommunicationMessage(
                    category_id=created_categories['HR Updates'].id,
                    author_id=admin.id,
                    title='Updated Overtime Policy - Effective Immediately',
                    content="""
                    <p>Please note the following updates to our overtime policy:</p>
                    <ol>
                        <li>All overtime must be pre-approved by your supervisor</li>
                        <li>Maximum weekly overtime is capped at 20 hours</li>
                        <li>Overtime rates have been updated per the new contract</li>
                    </ol>
                    <p>For questions, please contact HR.</p>
                    """,
                    priority='normal',
                    requires_acknowledgment=True,
                    target_all=True
                )
                db.session.add(msg2)
                
                # Maintenance Notice
                msg3 = CommunicationMessage(
                    category_id=created_categories['Maintenance Notices'].id,
                    author_id=admin.id,
                    title='Scheduled Maintenance - Production Line A',
                    content="""
                    <p><strong>Date:</strong> Next Tuesday, 2:00 AM - 6:00 AM</p>
                    <p><strong>Affected Area:</strong> Production Line A</p>
                    <p>Regular preventive maintenance will be performed. Please plan accordingly.</p>
                    """,
                    priority='normal',
                    target_crews=['A', 'B'],  # Only affects these crews
                    expires_at=datetime.utcnow() + timedelta(days=7)
                )
                db.session.add(msg3)
                
                # Hourly Employee Announcement
                msg4 = CommunicationMessage(
                    category_id=created_categories['Hourly Employee Announcements'].id,
                    author_id=admin.id,
                    title='Shift Differential Rate Increase',
                    content="""
                    <p>Good news! Effective next pay period:</p>
                    <ul>
                        <li>Evening shift differential: +$2.00/hour</li>
                        <li>Night shift differential: +$3.00/hour</li>
                        <li>Weekend differential: +$1.50/hour</li>
                    </ul>
                    <p>Thank you for your continued dedication!</p>
                    """,
                    priority='normal',
                    target_all=True
                )
                db.session.add(msg4)
                
                print("✓ Created sample messages")
            
            db.session.commit()
            print("\n✅ Communications system initialized successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ Error initializing communications: {str(e)}")
            raise

if __name__ == "__main__":
    init_communications_system()
