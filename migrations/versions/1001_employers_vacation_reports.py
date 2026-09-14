# fmt: off
"""Employers, worker contacts and vacation policy.

Revision ID: 1001_employers_vacation
Revises: 1000_hardened_baseline
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "1001_employers_vacation"
down_revision = "1000_hardened_baseline"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if "employer" not in inspector.get_table_names():
        op.create_table(
            "employer",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("first_name", sa.String(120), nullable=False),
            sa.Column("last_name", sa.String(120), nullable=False),
            sa.Column("fiscal_code", sa.String(16)),
            sa.Column("birth_date", sa.Date()),
            sa.Column("address", sa.Text()),
            sa.Column("phone", sa.String(40)),
            sa.Column("email", sa.String(255)),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    inspector = inspect(bind)
    worker_columns = {c["name"] for c in inspector.get_columns("worker")}
    with op.batch_alter_table("worker") as batch:
        if "employer_id" not in worker_columns:
            batch.add_column(sa.Column("employer_id", sa.Integer(), nullable=True))
        if "vacation_advance_allowed" not in worker_columns:
            batch.add_column(sa.Column("vacation_advance_allowed", sa.Boolean(), nullable=False, server_default=sa.false()))
    inspector = inspect(bind)
    index_names = {i["name"] for i in inspector.get_indexes("worker")}
    if "ix_worker_employer_id" not in index_names:
        op.create_index("ix_worker_employer_id", "worker", ["employer_id"])


def downgrade():
    inspector = inspect(op.get_bind())
    index_names = {i["name"] for i in inspector.get_indexes("worker")}
    if "ix_worker_employer_id" in index_names:
        op.drop_index("ix_worker_employer_id", table_name="worker")
    worker_columns = {c["name"] for c in inspector.get_columns("worker")}
    with op.batch_alter_table("worker") as batch:
        if "vacation_advance_allowed" in worker_columns:
            batch.drop_column("vacation_advance_allowed")
        if "employer_id" in worker_columns:
            batch.drop_column("employer_id")
    if "employer" in inspect(op.get_bind()).get_table_names():
        op.drop_table("employer")
