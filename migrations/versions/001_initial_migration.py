"""Initial migration - consolidated

Revision ID: 001_initial
Revises: 
Create Date: 2025-07-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def table_exists(table_name):
    """Check if a table exists"""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if not table_exists(table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Apply all necessary database changes"""
    
    # Fix schedule table columns
    if table_exists('schedule'):
        if not column_exists('schedule', 'overtime_reason'):
            op.add_column('schedule', sa.Column('overtime_reason', sa.String(length=200), nullable=True))
            print("Added overtime_reason to schedule table")
            
        if not column_exists('schedule', 'is_overtime'):
            op.add_column('schedule', sa.Column('is_overtime', sa.Boolean(), nullable=True))
            op.execute("UPDATE schedule SET is_overtime = FALSE WHERE is_overtime IS NULL")
            print("Added is_overtime to schedule table")
            
        if not column_exists('schedule', 'original_employee_id'):
            op.add_column('schedule', sa.Column('original_employee_id', sa.Integer(), nullable=True))
            try:
                op.create_foreign_key('fk_schedule_original_employee', 'schedule', 'employee', ['original_employee_id'], ['id'])
            except:
                pass  # Foreign key might already exist
            print("Added original_employee_id to schedule table")
    
    # Fix employee table columns
    if table_exists('employee'):
        if not column_exists('employee', 'employee_id'):
            op.add_column('employee', sa.Column('employee_id', sa.String(length=20), nullable=True))
            # Try to create unique constraint
            try:
                op.create_unique_constraint('uq_employee_employee_id', 'employee', ['employee_id'])
            except:
                pass
            print("Added employee_id to employee table")
            
        if not column_exists('employee', 'default_shift'):
            op.add_column('employee', sa.Column('default_shift', sa.String(length=20), nullable=True))
            op.execute("UPDATE employee SET default_shift = 'day' WHERE default_shift IS NULL")
            print("Added default_shift to employee table")
            
        if not column_exists('employee', 'max_consecutive_days'):
            op.add_column('employee', sa.Column('max_consecutive_days', sa.Integer(), nullable=True))
            op.execute("UPDATE employee SET max_consecutive_days = 14 WHERE max_consecutive_days IS NULL")
            print("Added max_consecutive_days to employee table")
            
        if not column_exists('employee', 'is_on_call'):
            op.add_column('employee', sa.Column('is_on_call', sa.Boolean(), nullable=True))
            op.execute("UPDATE employee SET is_on_call = FALSE WHERE is_on_call IS NULL")
            print("Added is_on_call to employee table")
            
        if not column_exists('employee', 'is_active'):
            op.add_column('employee', sa.Column('is_active', sa.Boolean(), nullable=True))
            op.execute("UPDATE employee SET is_active = TRUE WHERE is_active IS NULL")
            print("Added is_active to employee table")
    
    # Fix position table columns
    if table_exists('position'):
        if not column_exists('position', 'skills_required'):
            op.add_column('position', sa.Column('skills_required', sa.Text(), nullable=True))
            print("Added skills_required to position table")
            
        if not column_exists('position', 'requires_coverage'):
            op.add_column('position', sa.Column('requires_coverage', sa.Boolean(), nullable=True))
            op.execute("UPDATE position SET requires_coverage = TRUE WHERE requires_coverage IS NULL")
            print("Added requires_coverage to position table")
            
        if not column_exists('position', 'critical_position'):
            op.add_column('position', sa.Column('critical_position', sa.Boolean(), nullable=True))
            op.execute("UPDATE position SET critical_position = FALSE WHERE critical_position IS NULL")
            print("Added critical_position to position table")
    
    # Fix time_off_request table columns (from your previous migration)
    if table_exists('time_off_request'):
        # Check if we need to rename columns
        columns = [col['name'] for col in op.get_bind().execute(
            sa.text("SELECT column_name FROM information_schema.columns WHERE table_name = 'time_off_request'")
        )]
        
        # Handle column renames if old columns exist
        if 'submitted_date' in columns and 'created_at' not in columns:
            op.alter_column('time_off_request', 'submitted_date', new_column_name='created_at')
            print("Renamed submitted_date to created_at")
            
        if 'reviewed_by_id' in columns and 'approved_by' not in columns:
            op.alter_column('time_off_request', 'reviewed_by_id', new_column_name='approved_by')
            print("Renamed reviewed_by_id to approved_by")
            
        if 'reviewed_date' in columns and 'approved_date' not in columns:
            op.alter_column('time_off_request', 'reviewed_date', new_column_name='approved_date')
            print("Renamed reviewed_date to approved_date")
            
        if 'reviewer_notes' in columns and 'notes' not in columns:
            op.alter_column('time_off_request', 'reviewer_notes', new_column_name='notes')
            print("Renamed reviewer_notes to notes")
            
        # Add days_requested if it doesn't exist
        if not column_exists('time_off_request', 'days_requested'):
            op.add_column('time_off_request', sa.Column('days_requested', sa.Float(), nullable=True))
            print("Added days_requested to time_off_request table")
    
    print("Migration completed successfully!")


def downgrade():
    """Downgrade not implemented - not needed for production"""
    pass
