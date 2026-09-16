# fmt: off
from datetime import UTC, date, datetime
from decimal import Decimal

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint


db = SQLAlchemy()


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    locale = db.Column(db.String(2), default="it", nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Employer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    fiscal_code = db.Column(db.String(16))
    birth_date = db.Column(db.Date)
    address = db.Column(db.Text)
    city = db.Column(db.String(120))
    province = db.Column(db.String(2))
    postal_code = db.Column(db.String(10))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(255))
    notes = db.Column(db.Text)
    signature_stored_name = db.Column(db.String(255))
    signature_filename = db.Column(db.String(255))
    signature_mime_type = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey("employer.id", ondelete="SET NULL"), index=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    fiscal_code = db.Column(db.String(16))
    birth_date = db.Column(db.Date)
    address = db.Column(db.Text)
    city = db.Column(db.String(120))
    province = db.Column(db.String(2))
    postal_code = db.Column(db.String(10))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(255))
    inps_number = db.Column(db.String(100))
    contract_number = db.Column(db.String(100))
    contract_type = db.Column(db.String(20), default="permanent", nullable=False)
    employer_covers_all_taxes = db.Column(db.Boolean, default=False, nullable=False)
    employment_start = db.Column(db.Date, nullable=False, default=date.today)
    employment_end = db.Column(db.Date)
    weekly_hours = db.Column(db.Numeric(6, 2), default=0)
    live_in = db.Column(db.Boolean, default=False, nullable=False)
    live_in_reduced_schedule = db.Column(db.Boolean, default=False, nullable=False)
    union_officer = db.Column(db.Boolean, default=False, nullable=False)
    vacation_advance_allowed = db.Column(db.Boolean, default=False, nullable=False)
    signature_stored_name = db.Column(db.String(255))
    signature_filename = db.Column(db.String(255))
    signature_mime_type = db.Column(db.String(120))
    notes = db.Column(db.Text)


class HourlyRate(db.Model):
    __table_args__ = (
        UniqueConstraint("worker_id", "valid_from", name="uq_hourly_rate_worker_valid_from"),
        CheckConstraint("amount >= 0", name="ck_hourly_rate_amount_nonnegative"),
    )
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True)
    valid_from = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    notes = db.Column(db.String(255))


class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), unique=True, nullable=False, index=True)
    address = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class WorkEntry(db.Model):
    __table_args__ = (
        CheckConstraint("break_minutes >= 0", name="ck_work_break_nonnegative"),
        CheckConstraint("entry_kind IN ('ordinary','overtime')", name="ck_work_entry_kind"),
        CheckConstraint("rate_override IS NULL OR rate_override >= 0", name="ck_work_rate_override_nonnegative"),
    )
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("location.id", ondelete="SET NULL"), nullable=True, index=True)
    work_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    break_minutes = db.Column(db.Integer, default=0, nullable=False)
    entry_kind = db.Column(db.String(20), default="ordinary", nullable=False, index=True)
    paid = db.Column(db.Boolean, default=True, nullable=False)
    rate_override = db.Column(db.Numeric(10, 2))
    location = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)

    @property
    def hours(self):
        start = datetime.combine(self.work_date, self.start_time)
        end = datetime.combine(self.work_date, self.end_time)
        seconds = Decimal((end - start).total_seconds())
        return max(Decimal("0"), seconds / Decimal(3600) - Decimal(self.break_minutes) / Decimal(60))


class Absence(db.Model):
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_absence_dates"),
        CheckConstraint("paid_hours >= 0", name="ck_absence_paid_hours_nonnegative"),
    )
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    kind = db.Column(db.String(20), nullable=False)
    paid = db.Column(db.Boolean, default=True, nullable=False)
    paid_hours = db.Column(db.Numeric(8, 2), default=0)
    permit_category = db.Column(db.String(40), index=True)
    paid_beyond_legal_limit = db.Column(db.Boolean, default=False, nullable=False)
    oncological = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text)


class Expense(db.Model):
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_expense_amount_nonnegative"),
        CheckConstraint("direction IN ('employer_advance','worker_advance')", name="ck_expense_direction"),
    )
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True)
    expense_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    direction = db.Column(db.String(20), default="employer_advance", nullable=False)
    reimbursed = db.Column(db.Boolean, default=False, nullable=False)
    settlements = db.relationship(
        "ExpenseSettlement",
        backref="expense",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExpenseSettlement.settlement_date, ExpenseSettlement.id",
    )
    recovery_allocations = db.relationship(
        "ExpenseRecoveryAllocation",
        backref="expense",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExpenseRecoveryAllocation.due_month, ExpenseRecoveryAllocation.id",
    )


class ExpenseSettlement(db.Model):
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_settlement_amount_positive"),
        CheckConstraint(
            "method IN ('cash','bank_transfer','card','electronic','other')",
            name="ck_expense_settlement_method",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("expense.id", ondelete="CASCADE"), nullable=False, index=True)
    settlement_date = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    method = db.Column(db.String(24), default="cash", nullable=False)
    notes = db.Column(db.Text)
    filename = db.Column(db.String(255))
    stored_name = db.Column(db.String(255), unique=True)
    mime_type = db.Column(db.String(120))
    sha256 = db.Column(db.String(64), index=True)
    size_bytes = db.Column(db.Integer)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ExpenseRecoveryAllocation(db.Model):
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_recovery_allocation_amount_positive"),
        UniqueConstraint("expense_id", "due_month", name="uq_expense_recovery_allocation_month"),
    )
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(
        db.Integer, db.ForeignKey("expense.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # First day of the month to which this quota belongs.
    due_month = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    locked_at = db.Column(db.DateTime, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    category = db.Column(db.String(80), default="other")
    mime_type = db.Column(db.String(120))
    sha256 = db.Column(db.String(64), index=True)
    size_bytes = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class GeneratedReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id", ondelete="SET NULL"), nullable=True, index=True
    )
    report_type = db.Column(db.String(80), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    mime_type = db.Column(db.String(120), default="application/pdf", nullable=False)
    sha256 = db.Column(db.String(64), index=True, nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    approval_override = db.Column(db.Boolean, nullable=True)


class Payment(db.Model):
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payment_amount_nonnegative"),
        CheckConstraint(
            "payment_type IN ('salary','inps_contributions','thirteenth','tfr','expense_refund','other')",
            name="ck_payment_type",
        ),
        CheckConstraint("status IN ('pending','paid')", name="ck_payment_status"),
        CheckConstraint(
            "payment_method IN ('bank_transfer','card_deposit','cash','other')",
            name="ck_payment_method",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True)
    employer_id = db.Column(db.Integer, db.ForeignKey("employer.id", ondelete="SET NULL"), index=True)
    source_report_id = db.Column(db.Integer, db.ForeignKey("generated_report.id", ondelete="SET NULL"), index=True)
    payment_type = db.Column(db.String(40), nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    payment_method = db.Column(db.String(20), default="bank_transfer", nullable=False, index=True)
    payment_date = db.Column(db.Date)
    period_start = db.Column(db.Date, index=True)
    period_end = db.Column(db.Date, index=True)
    description = db.Column(db.String(255))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class PaymentAttachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payment.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    mime_type = db.Column(db.String(120))
    sha256 = db.Column(db.String(64), index=True)
    size_bytes = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Setting(db.Model):
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(255), nullable=False)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    object_type = db.Column(db.String(80))
    object_id = db.Column(db.String(80))
    remote_addr = db.Column(db.String(64))
    details = db.Column(db.String(500))
