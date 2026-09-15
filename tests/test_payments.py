from datetime import date, time
from decimal import Decimal

import pytest

from colf_manager.app import create_app
from colf_manager.models import HourlyRate, Payment, WorkEntry, Worker, db


@pytest.fixture()
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": str(tmp_path / "documents"),
            "REPORT_FOLDER": str(tmp_path / "reports"),
            "SIGNATURE_FOLDER": str(tmp_path / "signatures"),
            "PAYMENT_FOLDER": str(tmp_path / "payments"),
            "SESSION_COOKIE_SECURE": False,
            "TEST_ADMIN_PASSWORD": "Test-password-123",
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client):
    return client.post("/login", data={"username": "admin", "password": "Test-password-123"})


def seed_worker(app):
    with app.app_context():
        worker = Worker(
            first_name="Anna",
            last_name="Bianchi",
            employment_start=date(2026, 1, 1),
            weekly_hours=Decimal("20"),
            inps_number="INPS-TEST",
        )
        db.session.add(worker)
        db.session.flush()
        db.session.add(HourlyRate(worker_id=worker.id, valid_from=date(2026, 1, 1), amount=10))
        db.session.add(
            WorkEntry(
                worker_id=worker.id,
                work_date=date(2026, 9, 1),
                start_time=time(9),
                end_time=time(13),
                break_minutes=0,
                location="Casa",
            )
        )
        db.session.commit()
        return worker.id


def test_monthly_report_creates_pending_salary_and_inps_without_duplicates(app, client):
    worker_id = seed_worker(app)
    login(client)
    url = f"/reports/payroll.pdf?worker_id={worker_id}&year=2026&month=9"
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 200
    with app.app_context():
        salary = Payment.query.filter_by(worker_id=worker_id, payment_type="salary").all()
        inps = Payment.query.filter_by(worker_id=worker_id, payment_type="inps_contributions").all()
        assert len(salary) == 1
        assert len(inps) == 1
        assert salary[0].status == "pending"
        assert inps[0].status == "pending"


def test_manual_inps_payment_requires_inps_position(app, client):
    with app.app_context():
        worker = Worker(first_name="No", last_name="INPS", employment_start=date(2026, 1, 1))
        db.session.add(worker)
        db.session.commit()
        worker_id = worker.id
    login(client)
    response = client.post(
        "/payments",
        data={
            "worker_id": worker_id,
            "payment_type": "inps_contributions",
            "amount": "50.00",
            "status": "paid",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        assert Payment.query.count() == 0
