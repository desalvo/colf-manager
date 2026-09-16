"""payment method

Revision ID: 1013_payment_method
Revises: 1012_report_approval_override
"""

import sqlalchemy as sa
from alembic import op

revision = "1013_payment_method"
down_revision = "1012_report_approval_override"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "payment",
        sa.Column(
            "payment_method",
            sa.String(length=20),
            nullable=False,
            server_default="bank_transfer",
        ),
    )
    op.create_index("ix_payment_payment_method", "payment", ["payment_method"], unique=False)
    op.create_check_constraint(
        "ck_payment_method",
        "payment",
        "payment_method IN ('bank_transfer','card_deposit','cash','other')",
    )


def downgrade():
    op.drop_constraint("ck_payment_method", "payment", type_="check")
    op.drop_index("ix_payment_payment_method", table_name="payment")
    op.drop_column("payment", "payment_method")
