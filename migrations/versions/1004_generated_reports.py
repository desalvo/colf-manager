"""Persist generated reports.

Revision ID: 1004_generated_reports
Revises: 1003_locations
"""

import sqlalchemy as sa
from alembic import op

revision = "1004_generated_reports"
down_revision = "1003_locations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generated_report",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "worker_id",
            sa.Integer(),
            sa.ForeignKey("worker.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("report_type", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_generated_report_worker_id", "generated_report", ["worker_id"])
    op.create_index("ix_generated_report_report_type", "generated_report", ["report_type"])
    op.create_index("ix_generated_report_sha256", "generated_report", ["sha256"])
    op.create_index("ix_generated_report_created_at", "generated_report", ["created_at"])


def downgrade():
    op.drop_table("generated_report")
