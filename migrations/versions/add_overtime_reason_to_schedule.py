"""Add overtime_reason to schedule table

Revision ID: add_overtime_reason
Revises: 
Create Date: 2025-07-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_overtime_reason'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add overtime_reason column to schedule table
    op.add_column('schedule', sa.Column('overtime_reason', sa.String(length=200), nullable=True))


def downgrade():
    # Remove overtime_reason column from schedule table
    op.drop_column('schedule', 'overtime_reason')
