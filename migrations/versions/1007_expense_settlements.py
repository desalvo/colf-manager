"""Multiple partial manual settlements for expenses."""

from alembic import op
import sqlalchemy as sa

revision = "1007_expense_settlements"
down_revision = "1006_signatures_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "expense_settlement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "expense_id",
            sa.Integer(),
            sa.ForeignKey("expense.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "method",
            sa.String(length=24),
            nullable=False,
            server_default="cash",
        ),
        sa.Column("notes", sa.Text()),
        sa.Column("filename", sa.String(length=255)),
        sa.Column("stored_name", sa.String(length=255), unique=True),
        sa.Column("mime_type", sa.String(length=120)),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_expense_settlement_amount_positive",
        ),
        sa.CheckConstraint(
            "method IN ('cash','bank_transfer','card','electronic','other')",
            name="ck_expense_settlement_method",
        ),
    )
    op.create_index("ix_expense_settlement_expense_id", "expense_settlement", ["expense_id"])
    op.create_index(
        "ix_expense_settlement_settlement_date",
        "expense_settlement",
        ["settlement_date"],
    )
    op.create_index("ix_expense_settlement_sha256", "expense_settlement", ["sha256"])
    op.create_index(
        "ix_expense_settlement_created_by_user_id",
        "expense_settlement",
        ["created_by_user_id"],
    )
    op.create_index("ix_expense_settlement_created_at", "expense_settlement", ["created_at"])


def downgrade():
    op.drop_table("expense_settlement")
