# fmt: off
"""hour types, paid flags, health and permits

Revision ID: 1009_hour_types_health_permits
Revises: 1008_expense_recovery_allocations
"""

from alembic import op
import sqlalchemy as sa

revision = "1009_hour_types_health_permits"
down_revision = "1008_expense_recovery_allocations"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("work_entry") as batch:
        batch.add_column(sa.Column("entry_kind", sa.String(length=20), nullable=False, server_default="ordinary"))
        batch.add_column(sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("rate_override", sa.Numeric(10, 2), nullable=True))
        batch.create_index("ix_work_entry_entry_kind", ["entry_kind"], unique=False)
        batch.create_check_constraint("ck_work_entry_kind", "entry_kind IN ('ordinary','overtime')")
        batch.create_check_constraint("ck_work_rate_override_nonnegative", "rate_override IS NULL OR rate_override >= 0")
    op.execute("UPDATE absence SET kind='health' WHERE kind='sickness'")
    op.execute("UPDATE absence SET kind='permit', paid=TRUE WHERE kind='unpaid_leave'")
    op.alter_column("absence", "paid", server_default=sa.true())


def downgrade():
    op.execute("UPDATE absence SET kind='sickness' WHERE kind='health'")
    op.execute("UPDATE absence SET kind='unpaid_leave' WHERE kind='permit' AND paid=FALSE")
    op.alter_column("absence", "paid", server_default=sa.false())
    with op.batch_alter_table("work_entry") as batch:
        batch.drop_constraint("ck_work_rate_override_nonnegative", type_="check")
        batch.drop_constraint("ck_work_entry_kind", type_="check")
        batch.drop_index("ix_work_entry_entry_kind")
        batch.drop_column("rate_override")
        batch.drop_column("paid")
        batch.drop_column("entry_kind")
