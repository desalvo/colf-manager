"""Contract number and contribution/tax reporting options.

Revision ID: 1002_contract_tax_reporting
Revises: 1001_employers_vacation
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "1002_contract_tax_reporting"
down_revision = "1001_employers_vacation"
branch_labels = None
depends_on = None


def upgrade():
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("worker")}
    with op.batch_alter_table("worker") as batch:
        if "contract_number" not in cols:
            batch.add_column(sa.Column("contract_number", sa.String(100)))
        if "contract_type" not in cols:
            batch.add_column(
                sa.Column(
                    "contract_type",
                    sa.String(20),
                    nullable=False,
                    server_default="permanent",
                )
            )
        if "employer_covers_all_taxes" not in cols:
            batch.add_column(
                sa.Column(
                    "employer_covers_all_taxes",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade():
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("worker")}
    with op.batch_alter_table("worker") as batch:
        for name in (
            "employer_covers_all_taxes",
            "contract_type",
            "contract_number",
        ):
            if name in cols:
                batch.drop_column(name)
