"""Carry-forward and installment schedules for expense residuals."""

from alembic import op
import sqlalchemy as sa

revision = "1008_expense_recovery_allocations"
down_revision = "1007_expense_settlements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "expense_recovery_allocation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "expense_id",
            sa.Integer(),
            sa.ForeignKey("expense.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("due_month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("locked_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_expense_recovery_allocation_amount_positive",
        ),
        sa.UniqueConstraint(
            "expense_id",
            "due_month",
            name="uq_expense_recovery_allocation_month",
        ),
    )
    op.create_index(
        "ix_expense_recovery_allocation_expense_id",
        "expense_recovery_allocation",
        ["expense_id"],
    )
    op.create_index(
        "ix_expense_recovery_allocation_due_month",
        "expense_recovery_allocation",
        ["due_month"],
    )
    op.create_index(
        "ix_expense_recovery_allocation_locked_at",
        "expense_recovery_allocation",
        ["locked_at"],
    )
    op.create_index(
        "ix_expense_recovery_allocation_created_at",
        "expense_recovery_allocation",
        ["created_at"],
    )


def downgrade():
    op.drop_table("expense_recovery_allocation")
