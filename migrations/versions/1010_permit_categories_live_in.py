# fmt: off
"""permit categories and worker live-in status

Revision ID: 1010_permit_categories_live_in
Revises: 1009_hour_types_health_permits
"""
from alembic import op
import sqlalchemy as sa

revision = "1010_permit_categories_live_in"
down_revision = "1009_hour_types_health_permits"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("worker") as batch:
        batch.add_column(
            sa.Column("live_in", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column(
                "live_in_reduced_schedule",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column("union_officer", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("absence") as batch:
        batch.add_column(sa.Column("permit_category", sa.String(length=40), nullable=True))
        batch.create_index("ix_absence_permit_category", ["permit_category"], unique=False)
    op.execute(
        "UPDATE absence SET permit_category='other' "
        "WHERE kind='permit' AND permit_category IS NULL"
    )


def downgrade():
    with op.batch_alter_table("absence") as batch:
        batch.drop_index("ix_absence_permit_category")
        batch.drop_column("permit_category")
    with op.batch_alter_table("worker") as batch:
        batch.drop_column("union_officer")
        batch.drop_column("live_in_reduced_schedule")
        batch.drop_column("live_in")
