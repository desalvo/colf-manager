from datetime import date, time
from decimal import Decimal

import pytest

from colf_manager.app import create_app
from colf_manager.calculations import monthly_summary
from colf_manager.models import HourlyRate, WorkEntry, Worker
from colf_manager.reporting import payroll_pdf


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": str(tmp_path),
        }
    )
    yield app


def test_health(app):
    assert app.test_client().get("/healthz").json["version"] == "1.0.0"


def test_login_required(app):
    assert app.test_client().get("/").status_code == 302


def test_admin_login_and_dashboard(app):
    client = app.test_client()
    response = client.post("/login", data={"username": "admin", "password": "change-me-now"})
    assert response.status_code == 302
    assert client.get("/").status_code == 200


def test_summary_rate_history(app):
    with app.app_context():
        rates = [
            HourlyRate(valid_from=date(2026, 1, 1), amount=10),
            HourlyRate(valid_from=date(2026, 7, 1), amount=12),
        ]
        entries = [
            WorkEntry(
                work_date=date(2026, 6, 3),
                start_time=time(9),
                end_time=time(13),
                break_minutes=0,
                location="Casa",
            ),
            WorkEntry(
                work_date=date(2026, 7, 3),
                start_time=time(9),
                end_time=time(13),
                break_minutes=0,
                location="Casa",
            ),
        ]
        s = monthly_summary(entries, [], [], rates, 2026, 7)
        assert s["worked_hours"] == Decimal("4.00")
        assert s["gross"] == Decimal("48.00")
        assert s["tfr_accrual"] == Decimal("3.56")


def test_payroll_pdf(app):
    with app.app_context():
        worker = Worker(first_name="User", last_name="Example", employment_start=date(2026, 1, 1))
        summary = {
            "worked_hours": Decimal("8.00"),
            "worked_pay": Decimal("80.00"),
            "paid_absence": Decimal("0.00"),
            "reimbursements": Decimal("10.00"),
            "gross": Decimal("80.00"),
            "tfr_accrual": Decimal("5.93"),
            "payable": Decimal("90.00"),
        }
        assert payroll_pdf(worker, summary, 2026, 1).read(4) == b"%PDF"
