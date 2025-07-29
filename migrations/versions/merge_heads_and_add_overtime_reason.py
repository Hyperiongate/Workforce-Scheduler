"""Merge heads and add overtime_reason to schedule

Revision ID: merge_heads_001
Revises: 
Create Date: 2025-07-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'merge_heads_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add missing columns to schedule table"""
    # Get database connection and inspector
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Check if schedule table exists
    tables = inspector.get_table_names()
    if 'schedule' not in tables:
        print("Schedule table doesn't exist, skipping column additions")
        return
    
    # Get existing columns in schedule table
    columns = [col['name'] for col in inspector.get_columns('schedule')]
    print(f"Existing columns in schedule table: {columns}")
    
    # Add overtime_reason column if it doesn't exist
    if 'overtime_reason' not in columns:
        print("Adding overtime_reason column...")
        op.add_column('schedule', sa.Column('overtime_reason', sa.String(length=200), nullable=True))
    else:
        print("overtime_reason column already exists")
    
    # Add is_overtime column if it doesn't exist
    if 'is_overtime' not in columns:
        print("Adding is_overtime column...")
        op.add_column('schedule', sa.Column('is_overtime', sa.Boolean(), nullable=True, default=False))
        # Set default value for existing rows
        op.execute("UPDATE schedule SET is_overtime = FALSE WHERE is_overtime IS NULL")
    else:
        print("is_overtime column already exists")
    
    # Add original_employee_id column if it doesn't exist
    if 'original_employee_id' not in columns:
        print("Adding original_employee_id column...")
        op.add_column('schedule', sa.Column('original_employee_id', sa.Integer(), nullable=True))
        # Add foreign key constraint
        try:
            op.create_foreign_key(
                'fk_schedule_original_employee', 
                'schedule', 
                'employee', 
                ['original_employee_id'], 
                ['id']
            )
        except Exception as e:
            print(f"Could not create foreign key: {e}")
    else:
        print("original_employee_id column already exists")
    
    print("Migration completed successfully!")


def downgrade():
    """Remove added columns from schedule table"""
    # Get database connection and inspector
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Check if schedule table exists
    tables = inspector.get_table_names()
    if 'schedule' not in tables:
        print("Schedule table doesn't exist, skipping column removals")
        return
    
    # Get existing columns
    columns = [col['name'] for col in inspector.get_columns('schedule')]
    
    # Drop foreign key first if it exists
    try:
        op.drop_constraint('fk_schedule_original_employee', 'schedule', type_='foreignkey')
    except:
        pass
    
    # Drop columns if they exist
    if 'overtime_reason' in columns:
        op.drop_column('schedule', 'overtime_reason')
        
    if 'is_overtime' in columns:
        op.drop_column('schedule', 'is_overtime')
        
    if 'original_employee_id' in columns:
        op.drop_column('schedule', 'original_employee_id')
