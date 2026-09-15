"""Add city, province and postal code to workers and employers.

Revision ID: 1005_person_address_fields
Revises: 1004_generated_reports
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "1005_person_address_fields"
down_revision = "1004_generated_reports"
branch_labels = None
depends_on = None


def _add_missing(table_name):
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    with op.batch_alter_table(table_name) as batch:
        if "city" not in columns:
            batch.add_column(sa.Column("city", sa.String(length=120), nullable=True))
        if "province" not in columns:
            batch.add_column(sa.Column("province", sa.String(length=2), nullable=True))
        if "postal_code" not in columns:
            batch.add_column(sa.Column("postal_code", sa.String(length=10), nullable=True))


def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "worker" in tables:
        _add_missing("worker")
    if "employer" in tables:
        _add_missing("employer")


def downgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    for table_name in ("worker", "employer"):
        if table_name not in tables:
            continue
        columns = {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}
        with op.batch_alter_table(table_name) as batch:
            if "postal_code" in columns:
                batch.drop_column("postal_code")
            if "province" in columns:
                batch.drop_column("province")
            if "city" in columns:
                batch.drop_column("city")
