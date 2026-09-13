"""Hardened 1.0.0 baseline.

Revision ID: 1000_hardened_baseline
Revises: None
"""

revision = "1000_hardened_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Existing original-1.0.0 databases are upgraded by the compatibility shim
    # before this baseline is stamped. New hardened databases are created from
    # current SQLAlchemy metadata. Future revisions are fully Alembic-managed.
    pass


def downgrade():
    pass
