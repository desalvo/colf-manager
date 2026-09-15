# fmt: off
from datetime import date, time
from decimal import Decimal
from io import BytesIO

import pytest

from colf_manager.app import create_app
from colf_manager.calculations import monthly_summary, vacation_balance
from colf_manager.models import (
    Absence,
    Document,
    Employer,
    Expense,
    ExpenseRecoveryAllocation,
    ExpenseSettlement,
    GeneratedReport,
    HourlyRate,
    Location,
    Setting,
    User,
    WorkEntry,
    Worker,
    db,
)
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
        worker = Worker(
            first_name="User",
            last_name="Example",
            employment_start=date(2026, 1, 1),
        )
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
        assert s["tfr_accrual"] == Decimal("3.85")


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
        worker = Worker(
            first_name="User",
            last_name="Example",
            employment_start=date(2026, 1, 1),
        )
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
        employer = Employer(first_name="Mario", last_name="Rossi", address="Roma")
        approval = {"mode": "both", "place": "Roma", "date": date(2026, 9, 14)}
        assert (
            payroll_pdf(
                worker, summary, 2026, 1, employer=employer, approval=approval
            ).read(4)
            == b"%PDF"
        )


def test_employer_and_worker_crud(app, client):
    login(client)
    response = client.post(
        "/employers",
        data={
            "first_name": "Mario",
            "last_name": "Rossi",
            "fiscal_code": "RSSMRA80A01H501U",
            "address": "Via Roma 1",
            "city": "Roma",
            "province": "RM",
            "postal_code": "00100",
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
            "city": "Roma",
            "province": "RM",
            "postal_code": "00100",
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
        assert worker.city == "Roma"
        assert worker.province == "RM"
        assert worker.postal_code == "00100"
        assert employer.city == "Roma"
        assert employer.province == "RM"
        assert employer.postal_code == "00100"
        assert worker.vacation_advance_allowed is True
    assert client.get(f"/workers/{worker_id}").status_code == 200
    assert client.post(
        f"/workers/{worker_id}/edit",
        data={
            "first_name": "Anna",
            "last_name": "Bianchi",
            "employer_id": str(employer_id),
            "employment_start": "2026-01-01",
            "weekly_hours": "16",
            "email": "anna2@example.invalid",
            "city": "Pomezia",
            "province": "RM",
            "postal_code": "00071",
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
                worker_id=worker_id,
                work_date=date(2026, 1, 5),
                start_time=time(9),
                end_time=time(13),
                break_minutes=0,
                location="Casa",
            )
        )
        db.session.commit()
        balance = vacation_balance(worker, [], 2026, date(2026, 9, 14))
        assert balance["projected"] == Decimal("26.00")
        assert balance["available_usable"] == Decimal("26.00")
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=1")
    assert response.status_code == 200
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
        data={
            "name": "Casa Roma",
            "address": "Via Roma 1",
            "notes": "Ingresso interno",
        },
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
        db.session.add(
            WorkEntry(
                worker_id=worker_id,
                work_date=date(2025, 3, 4),
                start_time=time(9),
                end_time=time(11),
                break_minutes=0,
                location="Casa",
            )
        )
        db.session.commit()
    login(client)
    response = client.get("/?year=2025&month=3")
    assert response.status_code == 200
    assert b"03/2025" in response.data
    assert "Tredicesima maturata nel mese".encode() in response.data
    assert "Tredicesima annua maturata finora".encode() in response.data
    assert "TFR annuo maturato finora".encode() in response.data
    assert "Giorni di ferie godute nel mese".encode() in response.data
    assert "Ferie residue anno".encode() in response.data
    assert "Attività del periodo".encode() in response.data
    assert b"User Example" in response.data


def test_document_manual_delete(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/documents",
        data={
            "worker_id": str(worker_id),
            "category": "altro",
            "file": (BytesIO(b"%PDF-1.4\n%%EOF"), "delete-me.pdf"),
        },
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
        db.session.add(
            WorkEntry(
                worker_id=worker_id,
                work_date=date(2026, 1, 5),
                start_time=time(9),
                end_time=time(10),
                break_minutes=0,
                location="Casa",
            )
        )
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


def test_rate_history_edit_and_delete(app, client):
    worker_id = make_worker(app)
    login(client)
    assert client.post(
        "/rates",
        data={"worker_id": worker_id, "valid_from": "2026-01-01", "amount": "11.50"},
    ).status_code == 302
    with app.app_context():
        rate_id = HourlyRate.query.one().id
    assert client.get("/rates").status_code == 200
    assert client.post(
        f"/rates/{rate_id}/edit",
        data={
            "worker_id": worker_id,
            "valid_from": "2026-01-01",
            "amount": "12.25",
            "notes": "Aggiornata",
        },
    ).status_code == 302
    with app.app_context():
        assert db.session.get(HourlyRate, rate_id).amount == Decimal("12.25")
    assert client.post(f"/rates/{rate_id}/delete").status_code == 302
    with app.app_context():
        assert HourlyRate.query.count() == 0


def test_expense_edit_delete_and_monthly_report(app, client):
    worker_id = make_worker(app)
    login(client)
    assert client.post(
        "/expenses",
        data={
            "worker_id": worker_id,
            "expense_date": "2026-09-10",
            "description": "Farmacia",
            "amount": "18.40",
            "direction": "worker_advance",
        },
    ).status_code == 302
    with app.app_context():
        expense_id = Expense.query.one().id
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 1, 1), amount=10))
        db.session.commit()
    assert client.post(
        f"/expenses/{expense_id}/edit",
        data={
            "worker_id": worker_id,
            "expense_date": "2026-09-11",
            "description": "Farmacia aggiornata",
            "amount": "20.00",
            "direction": "worker_advance",
        },
    ).status_code == 302
    response = client.get(f"/reports/payroll.pdf?worker_id={worker_id}&year=2026&month=9")
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")
    assert client.post(f"/expenses/{expense_id}/delete").status_code == 302


def test_calendar_work_edit_delete_and_recent_patterns(app, client):
    login(client)
    employer = Employer(first_name="Mario", last_name="Datore")
    worker = Worker(
        first_name="Anna",
        last_name="Lavoratore",
        employment_start=date(2026, 1, 1),
    )
    location = Location(name="Casa")
    with app.app_context():
        db.session.add_all([employer, worker, location])
        db.session.flush()
        worker.employer_id = employer.id
        db.session.commit()
        worker_id, location_id = worker.id, location.id
    response = client.post(
        "/api/work",
        json={
            "worker_id": worker_id,
            "location_id": location_id,
            "work_date": "2026-09-14",
            "start_time": "09:00",
            "end_time": "12:00",
            "break_minutes": 15,
        },
    )
    assert response.status_code == 201
    entry_id = response.json["id"]
    assert client.get("/calendar").status_code == 200
    events = client.get("/api/events").json
    work_event = next(item for item in events if item["id"] == f"work-{entry_id}")
    assert work_event["extendedProps"]["employer"] == "Mario Datore"
    assert client.patch(
        f"/api/work/{entry_id}",
        json={
            "worker_id": worker_id,
            "location_id": location_id,
            "work_date": "2026-09-15",
            "start_time": "10:00",
            "end_time": "13:00",
            "break_minutes": 0,
            "notes": "modificata",
        },
    ).status_code == 200
    assert client.delete(f"/api/work/{entry_id}").status_code == 200
    with app.app_context():
        assert WorkEntry.query.count() == 0


def test_settings_and_mail_notification(app, client, monkeypatch):
    login(client)
    assert client.post(
        "/settings",
        data={
            "calendar_recent_limit": "12",
            "smtp_host": "smtp.example.invalid",
            "smtp_port": "465",
            "smtp_security": "ssl",
            "smtp_username": "user",
            "smtp_password": "secret",
            "smtp_from_email": "sender@example.invalid",
            "smtp_from_name": "Colf Manager",
        },
    ).status_code == 302
    sent = {}

    def fake_send(settings, to_address, subject, body, attachments=None):
        sent.update({"settings": settings, "to": to_address, "subject": subject, "body": body})

    monkeypatch.setattr("colf_manager.app.send_smtp_message", fake_send)
    assert client.post(
        "/mail/compose",
        data={
            "artifact_type": "notification",
            "to": "recipient@example.invalid",
            "subject": "Avviso",
            "body": "Test",
        },
    ).status_code == 302
    assert sent["settings"]["security"] == "ssl"
    assert sent["to"] == "recipient@example.invalid"


def test_calendar_vacation_sickness_crud_and_work_coexist(app, client):
    login(client)
    with app.app_context():
        employer = Employer(first_name="Mario", last_name="Datore")
        location = Location(name="Casa")
        worker = Worker(
            first_name="Anna",
            last_name="Lavoratore",
            employment_start=date(2026, 1, 1),
            weekly_hours=24,
            vacation_advance_allowed=True,
        )
        db.session.add_all([employer, location, worker])
        db.session.flush()
        worker.employer_id = employer.id
        db.session.commit()
        worker_id, location_id = worker.id, location.id

    vacation = client.post(
        "/api/absence",
        json={
            "worker_id": worker_id,
            "kind": "vacation",
            "start_date": "2026-09-14",
            "end_date": "2026-09-15",
            "start_time": "09:00",
            "end_time": "13:00",
            "notes": "Ferie programmate",
        },
    )
    assert vacation.status_code == 201
    absence_id = vacation.json["id"]

    work = client.post(
        "/api/work",
        json={
            "worker_id": worker_id,
            "location_id": location_id,
            "work_date": "2026-09-14",
            "start_time": "14:00",
            "end_time": "17:00",
            "break_minutes": 0,
        },
    )
    assert work.status_code == 201

    events = client.get("/api/events").json
    vacation_events = [
        event
        for event in events
        if event["extendedProps"].get("absence_id") == absence_id
    ]
    assert len(vacation_events) == 2
    assert {e["start"][:10] for e in vacation_events} == {"2026-09-14", "2026-09-15"}
    assert all(e["extendedProps"]["entry_kind"] == "vacation" for e in vacation_events)
    assert any(
        e["id"].startswith("work-") and e["start"].startswith("2026-09-14T14:00")
        for e in events
    )

    detail = client.get(f"/api/absence/{absence_id}")
    assert detail.status_code == 200
    assert detail.json["start_date"] == "2026-09-14"
    assert detail.json["end_date"] == "2026-09-15"

    updated = client.patch(
        f"/api/absence/{absence_id}",
        json={
            "kind": "sickness",
            "worker_id": worker_id,
            "start_date": "2026-09-16",
            "end_date": "2026-09-16",
            "start_time": "08:00",
            "end_time": "12:00",
            "paid": True,
        },
    )
    assert updated.status_code == 200
    events = client.get("/api/events").json
    sickness_events = [
        event
        for event in events
        if event["extendedProps"].get("absence_id") == absence_id
    ]
    assert len(sickness_events) == 1
    assert sickness_events[0]["extendedProps"]["entry_kind"] == "sickness"
    assert sickness_events[0]["start"].startswith("2026-09-16T08:00")

    assert client.delete(f"/api/absence/{absence_id}").status_code == 200
    with app.app_context():
        assert Absence.query.count() == 0
        assert WorkEntry.query.count() == 1


def test_reports_default_signature_place_is_employer_city(app, client):
    with app.app_context():
        employer = Employer(first_name="Mario", last_name="Rossi", city="Roma")
        db.session.add(employer)
        db.session.flush()
        worker = Worker(
            first_name="Anna",
            last_name="Bianchi",
            employer_id=employer.id,
            employment_start=date(2026, 1, 1),
        )
        db.session.add(worker)
        db.session.commit()
        worker_id = worker.id
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=9")
    assert response.status_code == 200
    assert b'name="signature_place" value="Roma"' in response.data


def test_calendar_subscription_uses_external_url(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/settings",
        data={
            "action": "save_settings",
            "calendar_recent_limit": "10",
            "external_url": "https://colf.example.test/base",
            "smtp_port": "587",
            "smtp_security": "starttls",
        },
    )
    assert response.status_code == 302
    response = client.post(
        "/settings",
        data={"action": "calendar_select", "calendar_target": f"worker:{worker_id}"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"https://colf.example.test/base/calendar-subscriptions/worker/" in response.data
    assert b"https://colf.example.test/base/caldav/worker/" in response.data


def test_calendar_subscription_ics_contains_work_and_absence(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(
            WorkEntry(
                worker_id=worker_id,
                work_date=date(2026, 9, 15),
                start_time=time(9),
                end_time=time(12),
                break_minutes=0,
                location="Casa",
            )
        )
        db.session.add(
            Absence(
                worker_id=worker_id,
                start_date=date(2026, 9, 16),
                end_date=date(2026, 9, 16),
                start_time=time(9),
                end_time=time(13),
                kind="vacation",
                paid=True,
                paid_hours=4,
            )
        )
        db.session.commit()
    login(client)
    client.post(
        "/settings",
        data={"action": "calendar_select", "calendar_target": f"worker:{worker_id}"},
    )
    with app.app_context():
        setting = db.session.get(Setting, f"calendar_subscription_worker_{worker_id}")
        token = setting.value
    response = client.get(f"/calendar-subscriptions/worker/{worker_id}/{token}/calendar.ics")
    assert response.status_code == 200
    assert b"BEGIN:VCALENDAR" in response.data
    assert b"Ore" in response.data
    assert b"Ferie" in response.data
    assert b"LOCATION:Casa" in response.data


def test_password_can_be_changed_from_settings(app, client):
    login(client)
    response = client.post(
        "/settings",
        data={
            "action": "change_password",
            "current_password": "Test-password-123",
            "new_password": "Another-strong-password-456",
            "confirm_password": "Another-strong-password-456",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(username="admin").one()
        assert user.must_change_password is False


def test_expense_partial_manual_settlements_reduce_payroll_residual(app, client):
    worker_id = make_worker(app)
    login(client)
    assert client.post(
        "/expenses",
        data={
            "worker_id": worker_id,
            "expense_date": "2026-09-02",
            "description": "Spesa anticipata",
            "amount": "120.00",
            "direction": "worker_advance",
        },
    ).status_code == 302
    with app.app_context():
        expense = Expense.query.one()
        expense_id = expense.id
    for day, amount, method in [(3, "40.00", "cash"), (12, "30.00", "bank_transfer")]:
        assert client.post(
            f"/expenses/{expense_id}/settlements",
            data={
                "settlement_date": f"2026-09-{day:02d}",
                "amount": amount,
                "method": method,
                "notes": "compensazione parziale",
            },
        ).status_code == 302
    with app.app_context():
        expense = db.session.get(Expense, expense_id)
        assert len(expense.settlements) == 2
        summary = monthly_summary([], [], [expense], [], 2026, 9)
        assert summary["worker_advances"] == Decimal("50.00")
        assert summary["reimbursements"] == Decimal("50.00")
        assert ExpenseSettlement.query.count() == 2


def test_expense_settlement_rejects_overpayment_without_carry_plan(app, client):
    worker_id = make_worker(app)
    login(client)
    client.post(
        "/expenses",
        data={
            "worker_id": worker_id,
            "expense_date": "2026-09-20",
            "description": "Acquisto",
            "amount": "20.00",
            "direction": "employer_advance",
        },
    )
    with app.app_context():
        expense_id = Expense.query.one().id
    client.post(
        f"/expenses/{expense_id}/settlements",
        data={"settlement_date": "2026-09-21", "amount": "15.00", "method": "cash"},
    )
    client.post(
        f"/expenses/{expense_id}/settlements",
        data={"settlement_date": "2026-09-22", "amount": "10.00", "method": "cash"},
    )
    client.post(
        f"/expenses/{expense_id}/settlements",
        data={"settlement_date": "2026-10-01", "amount": "5.00", "method": "cash"},
    )
    with app.app_context():
        assert ExpenseSettlement.query.count() == 1
        expense = db.session.get(Expense, expense_id)
        summary = monthly_summary([], [], [expense], [], 2026, 9)
        assert summary["employer_advances"] == Decimal("5.00")


def test_expense_carry_forward_moves_residual_to_next_month(app, client):
    worker_id = make_worker(app)
    login(client)
    client.post(
        "/expenses",
        data={
            "worker_id": worker_id,
            "expense_date": "2026-09-10",
            "description": "Spesa riportata",
            "amount": "90.00",
            "direction": "worker_advance",
        },
    )
    with app.app_context():
        expense_id = Expense.query.one().id
    response = client.post(
        f"/expenses/{expense_id}/recovery-plan",
        data={"mode": "carry_forward", "start_month": "2026-10"},
    )
    assert response.status_code == 302
    with app.app_context():
        expense = db.session.get(Expense, expense_id)
        assert ExpenseRecoveryAllocation.query.count() == 1
        assert monthly_summary([], [], [expense], [], 2026, 9)["worker_advances"] == Decimal("0.00")
        assert monthly_summary([], [], [expense], [], 2026, 10)["worker_advances"] == Decimal("90.00")


def test_expense_installments_and_later_manual_settlement_reduce_future_quota(app, client):
    worker_id = make_worker(app)
    login(client)
    client.post(
        "/expenses",
        data={
            "worker_id": worker_id,
            "expense_date": "2026-09-10",
            "description": "Spesa rateizzata",
            "amount": "180.00",
            "direction": "worker_advance",
        },
    )
    with app.app_context():
        expense_id = Expense.query.one().id
    client.post(
        f"/expenses/{expense_id}/recovery-plan",
        data={
            "mode": "installments",
            "start_month": "2026-10",
            "installment_count": "3",
        },
    )
    client.post(
        f"/expenses/{expense_id}/settlements",
        data={"settlement_date": "2026-11-05", "amount": "30.00", "method": "cash"},
    )
    with app.app_context():
        expense = db.session.get(Expense, expense_id)
        assert [Decimal(x.amount) for x in expense.recovery_allocations] == [
            Decimal("60.00"), Decimal("60.00"), Decimal("60.00")
        ]
        assert monthly_summary([], [], [expense], [], 2026, 10)["worker_advances"] == Decimal("60.00")
        assert monthly_summary([], [], [expense], [], 2026, 11)["worker_advances"] == Decimal("60.00")
        assert monthly_summary([], [], [expense], [], 2026, 12)["worker_advances"] == Decimal("30.00")


def test_expense_installments_by_amount_create_final_remainder(app, client):
    worker_id = make_worker(app)
    login(client)
    client.post(
        "/expenses",
        data={
            "worker_id": worker_id,
            "expense_date": "2026-09-10",
            "description": "Rate importo fisso",
            "amount": "125.00",
            "direction": "employer_advance",
        },
    )
    with app.app_context():
        expense_id = Expense.query.one().id
    client.post(
        f"/expenses/{expense_id}/recovery-plan",
        data={
            "mode": "installments",
            "start_month": "2026-10",
            "installment_amount": "50.00",
        },
    )
    with app.app_context():
        amounts = [Decimal(x.amount) for x in ExpenseRecoveryAllocation.query.order_by(ExpenseRecoveryAllocation.due_month)]
        assert amounts == [Decimal("50.00"), Decimal("50.00"), Decimal("25.00")]
