"""Fix time_off_request table columns

Revision ID: fix_time_off_request
Revises: 
Create Date: 2025-01-19 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fix_time_off_request'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # First, check if columns exist with old names and rename them
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('time_off_request')]
    
    # Rename columns if they exist with old names
    if 'submitted_date' in columns and 'created_at' not in columns:
        op.alter_column('time_off_request', 'submitted_date', new_column_name='created_at')
    elif 'created_at' not in columns:
        # Add created_at if it doesn't exist
        op.add_column('time_off_request', sa.Column('created_at', sa.DateTime(), nullable=True))
        op.execute("UPDATE time_off_request SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    
    if 'reviewed_by_id' in columns and 'approved_by' not in columns:
        op.alter_column('time_off_request', 'reviewed_by_id', new_column_name='approved_by')
    elif 'approved_by' not in columns:
        # Add approved_by if it doesn't exist
        op.add_column('time_off_request', sa.Column('approved_by', sa.Integer(), nullable=True))
        op.create_foreign_key(None, 'time_off_request', 'employee', ['approved_by'], ['id'])
    
    if 'reviewed_date' in columns and 'approved_date' not in columns:
        op.alter_column('time_off_request', 'reviewed_date', new_column_name='approved_date')
    elif 'approved_date' not in columns:
        # Add approved_date if it doesn't exist
        op.add_column('time_off_request', sa.Column('approved_date', sa.DateTime(), nullable=True))
    
    if 'reviewer_notes' in columns and 'notes' not in columns:
        op.alter_column('time_off_request', 'reviewer_notes', new_column_name='notes')
    elif 'notes' not in columns:
        # Add notes if it doesn't exist
        op.add_column('time_off_request', sa.Column('notes', sa.Text(), nullable=True))


def downgrade():
    # Rename columns back to original names
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('time_off_request')]
    
    if 'created_at' in columns:
        op.alter_column('time_off_request', 'created_at', new_column_name='submitted_date')
    
    if 'approved_by' in columns:
        op.alter_column('time_off_request', 'approved_by', new_column_name='reviewed_by_id')
    
    if 'approved_date' in columns:
        op.alter_column('time_off_request', 'approved_date', new_column_name='reviewed_date')
    
    if 'notes' in columns:
        op.alter_column('time_off_request', 'notes', new_column_name='reviewer_notes')
