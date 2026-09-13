from datetime import date, time
from decimal import Decimal
from io import BytesIO

import pytest

from colf_manager.app import create_app
from colf_manager.calculations import monthly_summary
from colf_manager.models import Absence, Expense, HourlyRate, User, WorkEntry, Worker, db
from colf_manager.reporting import payroll_pdf


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": str(tmp_path),
            "SESSION_COOKIE_SECURE": False,
            "TEST_ADMIN_PASSWORD": "Test-password-123",
        }
    )
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client):
    return client.post("/login", data={"username": "admin", "password": "Test-password-123"})


def make_worker(app):
    with app.app_context():
        worker = Worker(first_name="User", last_name="Example", employment_start=date(2026, 1, 1))
        db.session.add(worker)
        db.session.commit()
        return worker.id


def test_health(app):
    assert app.test_client().get("/healthz").json["version"] == "1.0.0"


def test_login_required(app):
    assert app.test_client().get("/").status_code == 302


def test_admin_login_and_dashboard(client):
    assert login(client).status_code == 302
    assert client.get("/").status_code == 200


def test_initial_user_is_admin(app):
    with app.app_context():
        user = User.query.filter_by(username="admin").one()
        assert user.is_admin is True


def test_invalid_work_time_rejected(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/api/work",
        json={
            "worker_id": worker_id,
            "work_date": "2026-09-01",
            "start_time": "13:00",
            "end_time": "09:00",
            "break_minutes": 0,
            "location": "Casa",
        },
    )
    assert response.status_code == 400


def test_break_longer_than_shift_rejected(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/api/work",
        json={
            "worker_id": worker_id,
            "work_date": "2026-09-01",
            "start_time": "09:00",
            "end_time": "10:00",
            "break_minutes": 60,
            "location": "Casa",
        },
    )
    assert response.status_code == 400


def test_summary_rate_history(app):
    with app.app_context():
        rates = [
            HourlyRate(valid_from=date(2026, 1, 1), amount=10),
            HourlyRate(valid_from=date(2026, 7, 1), amount=12),
        ]
        entries = [
            WorkEntry(
                work_date=date(2026, 7, 3),
                start_time=time(9),
                end_time=time(13),
                break_minutes=0,
                location="Casa",
            )
        ]
        s = monthly_summary(entries, [], [], rates, 2026, 7)
        assert s["worked_hours"] == Decimal("4.00")
        assert s["gross"] == Decimal("48.00")
        assert s["tfr_accrual"] == Decimal("3.56")


def test_expense_direction_changes_payable(app):
    with app.app_context():
        rates = [HourlyRate(valid_from=date(2026, 1, 1), amount=10)]
        entries = [
            WorkEntry(
                work_date=date(2026, 9, 1),
                start_time=time(9),
                end_time=time(10),
                break_minutes=0,
                location="Casa",
            )
        ]
        expenses = [
            Expense(
                expense_date=date(2026, 9, 2),
                amount=20,
                direction="worker_advance",
                description="Spesa",
            ),
            Expense(
                expense_date=date(2026, 9, 3),
                amount=5,
                direction="employer_advance",
                description="Anticipo",
            ),
        ]
        s = monthly_summary(entries, [], expenses, rates, 2026, 9)
        assert s["worker_advances"] == Decimal("20.00")
        assert s["employer_advances"] == Decimal("5.00")
        assert s["payable"] == Decimal("25.00")


def test_paid_absence_is_split_across_month_and_rate_change(app):
    with app.app_context():
        rates = [
            HourlyRate(valid_from=date(2026, 9, 1), amount=10),
            HourlyRate(valid_from=date(2026, 10, 1), amount=12),
        ]
        absence = Absence(
            start_date=date(2026, 9, 30),
            end_date=date(2026, 10, 1),
            paid=True,
            paid_hours=8,
            kind="vacation",
        )
        september = monthly_summary([], [absence], [], rates, 2026, 9)
        october = monthly_summary([], [absence], [], rates, 2026, 10)
        assert september["paid_absence"] == Decimal("40.00")
        assert october["paid_absence"] == Decimal("48.00")


def test_duplicate_rate_date_rejected(app, client):
    worker_id = make_worker(app)
    login(client)
    data = {"worker_id": worker_id, "valid_from": "2026-09-01", "amount": "10.00"}
    assert client.post("/rates", data=data).status_code == 302
    assert client.post("/rates", data=data).status_code == 302
    with app.app_context():
        assert HourlyRate.query.filter_by(worker_id=worker_id).count() == 1


def test_upload_rejects_fake_pdf(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/documents",
        data={
            "worker_id": str(worker_id),
            "category": "contratto",
            "file": (BytesIO(b"not a pdf"), "x.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert b"contenuto" in response.data.lower()


def test_payroll_pdf(app):
    with app.app_context():
        worker = Worker(first_name="User", last_name="Example", employment_start=date(2026, 1, 1))
        summary = {
            "worked_hours": Decimal("8.00"),
            "worked_pay": Decimal("80.00"),
            "paid_absence": Decimal("0.00"),
            "worker_advances": Decimal("10.00"),
            "employer_advances": Decimal("0.00"),
            "reimbursements": Decimal("10.00"),
            "gross": Decimal("80.00"),
            "tfr_accrual": Decimal("5.93"),
            "payable": Decimal("90.00"),
        }
        assert payroll_pdf(worker, summary, 2026, 1).read(4) == b"%PDF"
