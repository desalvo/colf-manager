"""sickness days and employer-paid override

Revision ID: 1011_sickness_days_and_employer_override
Revises: 1010_permit_categories_live_in
"""

from alembic import op
import sqlalchemy as sa

revision = "1011_sickness_days_and_employer_override"
down_revision = "1010_permit_categories_live_in"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("absence") as batch:
        batch.add_column(
            sa.Column(
                "paid_beyond_legal_limit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "oncological",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    op.execute("UPDATE absence SET kind = 'sickness' WHERE kind = 'health'")
    op.execute("UPDATE absence SET start_time = NULL, end_time = NULL WHERE kind = 'sickness'")


def downgrade():
    op.execute("UPDATE absence SET kind = 'health' WHERE kind = 'sickness'")
    with op.batch_alter_table("absence") as batch:
        batch.drop_column("oncological")
        batch.drop_column("paid_beyond_legal_limit")
