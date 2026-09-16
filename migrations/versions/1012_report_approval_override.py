"""report approval override

Revision ID: 1012_report_approval_override
Revises: 1011_sickness_days_and_employer_override
"""

import sqlalchemy as sa
from alembic import op

revision = "1012_report_approval_override"
down_revision = "1011_sickness_days_and_employer_override"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generated_report", sa.Column("approval_override", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("generated_report", "approval_override")
