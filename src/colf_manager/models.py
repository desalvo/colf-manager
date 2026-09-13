from datetime import date, datetime
from decimal import Decimal

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    locale = db.Column(db.String(2), default="it", nullable=False)


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
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=False, index=True)
    valid_from = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    notes = db.Column(db.String(255))


class WorkEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=False, index=True)
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
        return max(
            Decimal("0"),
            Decimal(str((end - start).total_seconds() / 3600))
            - Decimal(self.break_minutes) / Decimal(60),
        )


class Absence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # vacation, unpaid_leave, sickness
    paid = db.Column(db.Boolean, default=False, nullable=False)
    paid_hours = db.Column(db.Numeric(8, 2), default=0)
    notes = db.Column(db.Text)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=False, index=True)
    expense_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    direction = db.Column(db.String(20), default="employer_advance", nullable=False)
    reimbursed = db.Column(db.Boolean, default=False, nullable=False)


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    worker_id = db.Column(db.Integer, db.ForeignKey("worker.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    category = db.Column(db.String(80), default="other")
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Setting(db.Model):
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
