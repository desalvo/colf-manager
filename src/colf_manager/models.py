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


class Worker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    fiscal_code = db.Column(db.String(16))
    birth_date = db.Column(db.Date)
    address = db.Column(db.Text)
    phone = db.Column(db.String(40))
    email = db.Column(db.String(255))
    inps_number = db.Column(db.String(100))
    employment_start = db.Column(db.Date, nullable=False, default=date.today)
    employment_end = db.Column(db.Date)
    weekly_hours = db.Column(db.Numeric(6, 2), default=0)
    notes = db.Column(db.Text)


class HourlyRate(db.Model):
    __table_args__ = (
        UniqueConstraint("worker_id", "valid_from", name="uq_hourly_rate_worker_valid_from"),
        CheckConstraint("amount >= 0", name="ck_hourly_rate_amount_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True
    )
    valid_from = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    notes = db.Column(db.String(255))


class WorkEntry(db.Model):
    __table_args__ = (CheckConstraint("break_minutes >= 0", name="ck_work_break_nonnegative"),)

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    break_minutes = db.Column(db.Integer, default=0, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)

    @property
    def hours(self):
        start = datetime.combine(self.work_date, self.start_time)
        end = datetime.combine(self.work_date, self.end_time)
        seconds = Decimal((end - start).total_seconds())
        return max(
            Decimal("0"), seconds / Decimal(3600) - Decimal(self.break_minutes) / Decimal(60)
        )


class Absence(db.Model):
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_absence_dates"),
        CheckConstraint("paid_hours >= 0", name="ck_absence_paid_hours_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    paid = db.Column(db.Boolean, default=False, nullable=False)
    paid_hours = db.Column(db.Numeric(8, 2), default=0)
    notes = db.Column(db.Text)


class Expense(db.Model):
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_expense_amount_nonnegative"),
        CheckConstraint(
            "direction IN ('employer_advance','worker_advance')", name="ck_expense_direction"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expense_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    direction = db.Column(db.String(20), default="employer_advance", nullable=False)
    reimbursed = db.Column(db.Boolean, default=False, nullable=False)


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(
        db.Integer, db.ForeignKey("worker.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    category = db.Column(db.String(80), default="other")
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
