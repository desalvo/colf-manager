"""Managed work locations.

Revision ID: 1003_locations
Revises: 1002_contract_tax_reporting
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "1003_locations"
down_revision = "1002_contract_tax_reporting"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if "location" not in inspector.get_table_names():
        op.create_table(
            "location",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("address", sa.Text()),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("name", name="uq_location_name"),
        )
        op.create_index("ix_location_name", "location", ["name"])

    inspector = inspect(bind)
    work_columns = {column["name"] for column in inspector.get_columns("work_entry")}
    foreign_keys = inspector.get_foreign_keys("work_entry")

    location_fk_present = False
    for foreign_key in foreign_keys:
        referred_table = foreign_key.get("referred_table")
        constrained_columns = foreign_key.get("constrained_columns")
        if referred_table == "location" and constrained_columns == ["location_id"]:
            location_fk_present = True
            break

    with op.batch_alter_table("work_entry") as batch:
        if "location_id" not in work_columns:
            batch.add_column(sa.Column("location_id", sa.Integer(), nullable=True))
        if not location_fk_present:
            batch.create_foreign_key(
                "fk_work_entry_location_id_location",
                "location",
                ["location_id"],
                ["id"],
                ondelete="SET NULL",
            )

    inspector = inspect(bind)
    index_names = {index["name"] for index in inspector.get_indexes("work_entry")}
    if "ix_work_entry_location_id" not in index_names:
        op.create_index("ix_work_entry_location_id", "work_entry", ["location_id"])


def downgrade():
    inspector = inspect(op.get_bind())
    index_names = {index["name"] for index in inspector.get_indexes("work_entry")}

    if "ix_work_entry_location_id" in index_names:
        op.drop_index("ix_work_entry_location_id", table_name="work_entry")

    work_columns = {column["name"] for column in inspector.get_columns("work_entry")}
    if "location_id" in work_columns:
        with op.batch_alter_table("work_entry") as batch:
            batch.drop_column("location_id")

    if "location" in inspect(op.get_bind()).get_table_names():
        op.drop_table("location")
