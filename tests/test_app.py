# fmt: off
from datetime import date, time
from decimal import Decimal
from io import BytesIO

import pytest

from colf_manager.app import create_app
from colf_manager.calculations import monthly_summary, vacation_balance
from colf_manager.models import Absence, Document, Employer, Expense, GeneratedReport, HourlyRate, Location, User, WorkEntry, Worker, db
from colf_manager.reporting import payroll_pdf


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": str(tmp_path / "documents"),
            "REPORT_FOLDER": str(tmp_path / "reports"),
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
        rates = [HourlyRate(valid_from=date(2026, 1, 1), amount=10), HourlyRate(valid_from=date(2026, 7, 1), amount=12)]
        entries = [
            WorkEntry(work_date=date(2026, 7, 3), start_time=time(9), end_time=time(13), break_minutes=0, location="Casa")
        ]
        s = monthly_summary(entries, [], [], rates, 2026, 7)
        assert s["worked_hours"] == Decimal("4.00")
        assert s["gross"] == Decimal("48.00")
        assert s["tfr_accrual"] == Decimal("3.85")


def test_expense_direction_changes_payable(app):
    with app.app_context():
        rates = [HourlyRate(valid_from=date(2026, 1, 1), amount=10)]
        entries = [WorkEntry(work_date=date(2026, 9, 1), start_time=time(9), end_time=time(10), break_minutes=0, location="Casa")]
        expenses = [
            Expense(expense_date=date(2026, 9, 2), amount=20, direction="worker_advance", description="Spesa"),
            Expense(expense_date=date(2026, 9, 3), amount=5, direction="employer_advance", description="Anticipo"),
        ]
        s = monthly_summary(entries, [], expenses, rates, 2026, 9)
        assert s["worker_advances"] == Decimal("20.00")
        assert s["employer_advances"] == Decimal("5.00")
        assert s["payable"] == Decimal("25.00")


def test_paid_absence_is_split_across_month_and_rate_change(app):
    with app.app_context():
        rates = [HourlyRate(valid_from=date(2026, 9, 1), amount=10), HourlyRate(valid_from=date(2026, 10, 1), amount=12)]
        absence = Absence(start_date=date(2026, 9, 30), end_date=date(2026, 10, 1), paid=True, paid_hours=8, kind="vacation")
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
        data={"worker_id": str(worker_id), "category": "contratto", "file": (BytesIO(b"not a pdf"), "x.pdf")},
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
            "thirteenth_accrual": Decimal("6.67"),
            "tfr_accrual": Decimal("5.93"),
            "payable": Decimal("90.00"),
        }
        assert payroll_pdf(worker, summary, 2026, 1).read(4) == b"%PDF"


def test_employer_and_worker_crud(app, client):
    login(client)
    response = client.post(
        "/employers",
        data={
            "first_name": "Mario",
            "last_name": "Rossi",
            "fiscal_code": "RSSMRA80A01H501U",
            "address": "Via Roma 1",
            "phone": "+39 061234",
            "email": "mario@example.invalid",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        employer = Employer.query.one()
        employer_id = employer.id
    response = client.post(
        "/workers",
        data={
            "first_name": "Anna",
            "last_name": "Bianchi",
            "employer_id": str(employer_id),
            "employment_start": "2026-01-01",
            "weekly_hours": "12",
            "hourly_rate": "10",
            "address": "Via Milano 2",
            "phone": "+39 067777",
            "email": "anna@example.invalid",
            "vacation_advance_allowed": "on",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        worker = Worker.query.one()
        worker_id = worker.id
        assert worker.employer_id == employer_id
        assert worker.email == "anna@example.invalid"
        assert worker.vacation_advance_allowed is True
    assert client.get(f"/workers/{worker_id}").status_code == 200
    assert client.post(
        f"/workers/{worker_id}/edit",
        data={
            "first_name": "Anna", "last_name": "Bianchi",
            "employer_id": str(employer_id), "employment_start": "2026-01-01",
            "weekly_hours": "16", "email": "anna2@example.invalid",
        },
    ).status_code == 302
    assert client.post(
        f"/employers/{employer_id}/delete", data={"confirmation": "DELETE"}
    ).status_code == 302
    with app.app_context():
        assert Employer.query.count() == 0
        assert db.session.get(Worker, worker_id).employer_id is None
    assert client.post(
        f"/workers/{worker_id}/delete", data={"confirmation": "DELETE"}
    ).status_code == 302
    with app.app_context():
        assert Worker.query.count() == 0


def test_vacation_projection_and_reports(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("12")
        worker.vacation_advance_allowed = True
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 1, 1), amount=10))
        db.session.add(
            WorkEntry(
                worker_id=worker_id, work_date=date(2026, 1, 5),
                start_time=time(9), end_time=time(13), break_minutes=0, location="Casa"
            )
        )
        db.session.commit()
        balance = vacation_balance(worker, [], 2026, date(2026, 9, 14))
        assert balance["projected"] == Decimal("26.00")
        assert balance["available_usable"] == Decimal("26.00")
    login(client)
    assert client.get(f"/reports?worker_id={worker_id}&year=2026&month=1").status_code == 200
    urls = [
        f"/reports/payroll.pdf?worker_id={worker_id}&year=2026&month=1",
        f"/reports/annual-payroll.pdf?worker_id={worker_id}&year=2026",
        f"/reports/cu-courtesy.pdf?worker_id={worker_id}&year=2026",
        f"/reports/tfr.pdf?worker_id={worker_id}&year=2026",
        f"/reports/trend.pdf?worker_id={worker_id}&year=2026",
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200
        assert response.data.startswith(b"%PDF")


def test_location_crud_and_calendar_history(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/locations",
        data={"name": "Casa Roma", "address": "Via Roma 1", "notes": "Ingresso interno"},
    )
    assert response.status_code == 302
    with app.app_context():
        location = Location.query.one()
        location_id = location.id

    response = client.post(
        "/api/work",
        json={
            "worker_id": worker_id,
            "location_id": location_id,
            "work_date": "2026-09-10",
            "start_time": "09:00",
            "end_time": "11:00",
            "break_minutes": 0,
        },
    )
    assert response.status_code == 201

    assert client.get(f"/locations/{location_id}").status_code == 200
    response = client.post(
        f"/locations/{location_id}/edit",
        data={"name": "Casa Centro", "address": "Via Roma 2"},
    )
    assert response.status_code == 302

    with app.app_context():
        entry = WorkEntry.query.one()
        assert entry.location_id == location_id
        assert entry.location == "Casa Roma — Via Roma 1"

    response = client.post(
        f"/locations/{location_id}/delete",
        data={"confirmation": "DELETE"},
    )
    assert response.status_code == 302
    with app.app_context():
        assert Location.query.count() == 0
        entry = WorkEntry.query.one()
        assert entry.location_id is None
        assert entry.location == "Casa Roma — Via Roma 1"


def test_dashboard_selected_period(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2025, 1, 1), amount=10))
        db.session.add(WorkEntry(worker_id=worker_id, work_date=date(2025, 3, 4), start_time=time(9), end_time=time(11), break_minutes=0, location="Casa"))
        db.session.commit()
    login(client)
    response = client.get("/?year=2025&month=3")
    assert response.status_code == 200
    assert b"03/2025" in response.data


def test_document_manual_delete(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/documents",
        data={"worker_id": str(worker_id), "category": "altro", "file": (BytesIO(b"%PDF-1.4\n%%EOF"), "delete-me.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    with app.app_context():
        document = Document.query.one()
        document_id = document.id
    assert client.post(f"/documents/{document_id}/delete").status_code == 302
    with app.app_context():
        assert Document.query.count() == 0


def test_generated_report_is_archived(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 1, 1), amount=10))
        db.session.add(WorkEntry(worker_id=worker_id, work_date=date(2026, 1, 5), start_time=time(9), end_time=time(10), break_minutes=0, location="Casa"))
        db.session.commit()
    login(client)
    response = client.get(f"/reports/payroll.pdf?worker_id={worker_id}&year=2026&month=1")
    assert response.status_code == 200
    with app.app_context():
        report = GeneratedReport.query.one()
        assert report.report_type == "monthly_payroll"
        report_id = report.id
    assert client.post(f"/reports/archive/{report_id}/delete").status_code == 302
    with app.app_context():
        assert GeneratedReport.query.count() == 0
