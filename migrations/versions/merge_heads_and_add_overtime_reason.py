"""Merge heads and add overtime_reason to schedule

Revision ID: merge_heads_001
Revises: 
Create Date: 2025-07-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_heads_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Check if overtime_reason column exists before adding
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Get existing columns in schedule table
    columns = [col['name'] for col in inspector.get_columns('schedule')]
    
    # Only add column if it doesn't exist
    if 'overtime_reason' not in columns:
        op.add_column('schedule', sa.Column('overtime_reason', sa.String(length=200), nullable=True))


def downgrade():
    # Check if column exists before dropping
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('schedule')]
    
    if 'overtime_reason' in columns:
        op.drop_column('schedule', 'overtime_reason')
