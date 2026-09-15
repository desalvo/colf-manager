"""Signatures, payments and payment attachments."""

from alembic import op
import sqlalchemy as sa

revision = "1006_signatures_payments"
down_revision = "1005_person_address_fields"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("worker", "employer"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("signature_stored_name", sa.String(length=255), nullable=True)
            )
            batch.add_column(sa.Column("signature_filename", sa.String(length=255), nullable=True))
            batch.add_column(sa.Column("signature_mime_type", sa.String(length=120), nullable=True))

    op.create_table(
        "payment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "worker_id",
            sa.Integer(),
            sa.ForeignKey("worker.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employer_id",
            sa.Integer(),
            sa.ForeignKey("employer.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_report_id",
            sa.Integer(),
            sa.ForeignKey("generated_report.id", ondelete="SET NULL"),
        ),
        sa.Column("payment_type", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("payment_date", sa.Date()),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("description", sa.String(length=255)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_payment_amount_nonnegative"),
        sa.CheckConstraint(
            "payment_type IN ('salary','inps_contributions','thirteenth','tfr',"
            "'expense_refund','other')",
            name="ck_payment_type",
        ),
        sa.CheckConstraint("status IN ('pending','paid')", name="ck_payment_status"),
    )
    op.create_index("ix_payment_worker_id", "payment", ["worker_id"])
    op.create_index("ix_payment_employer_id", "payment", ["employer_id"])
    op.create_index("ix_payment_source_report_id", "payment", ["source_report_id"])
    op.create_index("ix_payment_payment_type", "payment", ["payment_type"])
    op.create_index("ix_payment_status", "payment", ["status"])
    op.create_index("ix_payment_period_start", "payment", ["period_start"])
    op.create_index("ix_payment_period_end", "payment", ["period_end"])
    op.create_index("ix_payment_created_at", "payment", ["created_at"])

    op.create_table(
        "payment_attachment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "payment_id",
            sa.Integer(),
            sa.ForeignKey("payment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(length=120)),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_payment_attachment_payment_id", "payment_attachment", ["payment_id"])
    op.create_index("ix_payment_attachment_sha256", "payment_attachment", ["sha256"])


def downgrade():
    op.drop_table("payment_attachment")
    op.drop_table("payment")
    for table in ("worker", "employer"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("signature_mime_type")
            batch.drop_column("signature_filename")
            batch.drop_column("signature_stored_name")
