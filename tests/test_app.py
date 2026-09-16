# fmt: off
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest

from colf_manager.app import create_app
from colf_manager.calculations import (
    annual_summary,
    money,
    monthly_summary,
    vacation_balance,
    vacation_hours_per_day,
    vacation_working_days,
)
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
    Payment,
    Setting,
    User,
    WorkEntry,
    Worker,
    db,
)
from colf_manager.reporting import _signature_image, payroll_pdf


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


def test_continuous_vacation_is_charged_to_end_month_across_rate_change(app):
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
        assert september["paid_absence"] == Decimal("0.00")
        assert october["paid_absence"] == Decimal("88.00")


def test_paid_permit_is_still_split_across_month_and_rate_change(app):
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
            kind="permit",
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


def test_dashboard_permit_indicators_show_used_and_remaining(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("40")
        db.session.add(
            Absence(
                worker_id=worker_id,
                kind="permit",
                permit_category="medical",
                start_date=date(2026, 9, 10),
                end_date=date(2026, 9, 10),
                start_time=time(9),
                end_time=time(11),
                paid=True,
                paid_hours=Decimal("2"),
            )
        )
        db.session.add(
            Absence(
                worker_id=worker_id,
                kind="permit",
                permit_category="other",
                start_date=date(2026, 9, 11),
                end_date=date(2026, 9, 11),
                start_time=time(12),
                end_time=time(13),
                paid=False,
                paid_hours=Decimal("0"),
            )
        )
        db.session.commit()
    login(client)
    response = client.get("/?year=2026&month=9")
    assert response.status_code == 200
    assert b'data-metric="permit-medical-paid-year">2.00 h' in response.data
    assert b'data-metric="permit-medical-accrued">12.00 h' in response.data
    assert b'data-metric="permit-medical-annual-total">12.00 h' in response.data
    assert b'data-metric="permit-medical-remaining">10.00 h' in response.data
    assert b'data-metric="permit-other-unpaid-year">1.00 h' in response.data
    assert b'data-metric="permit-other-remaining">N/D' in response.data


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


def test_calendar_dialog_has_one_paid_choice_and_type_specific_sections(app, client):
    login(client)
    response = client.get("/calendar")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    dialog = html.split('<dialog id="workDialog"', 1)[1].split('</dialog>', 1)[0]
    assert dialog.count('id="paidEntry"') == 1
    assert 'id="paidWork"' not in dialog
    assert 'id="paidAbsence"' not in dialog
    assert 'id="workOnlyFields"' in dialog
    assert 'id="permitOnlyFields"' in dialog
    assert 'id="sicknessOnlyFields"' in dialog
    assert 'id="vacationOnlyFields"' in dialog
    assert dialog.count('id="paidBeyondLegalLimit"') == 1
    assert dialog.count("Trattamento di miglior favore") == 1
    assert 'name="sickness_paid_beyond_legal_limit"' not in dialog
    assert 'name="paid_hours"' not in dialog
    assert 'id="permitOnlyFields" class="hidden" hidden' in dialog
    assert 'id="sicknessOnlyFields" class="hidden" hidden' in dialog
    assert 'id="vacationOnlyFields" class="hidden" hidden' in dialog
    assert 'id="favorableTreatmentField" hidden' in dialog

    javascript = (Path(__file__).parents[1] / "src/colf_manager/static/calendar.js").read_text()
    assert "paidEntry.checked = props.paid !== false" in javascript
    assert "paidEntry.checked = Boolean(props.paid)" in javascript
    assert "paidEntry.checked = Boolean(data.paid)" in javascript
    sync_body = javascript.split("function syncEntryKind() {", 1)[1].split("function resetWorkForm()", 1)[0]
    assert "paidEntry.checked = true" not in sync_body
    assert "setVisible(workOnlyFields, isWork)" in sync_body
    assert "setVisible(permitOnlyFields, isPermit)" in sync_body
    assert "setVisible(sicknessOnlyFields, isSickness)" in sync_body
    assert "setVisible(favorableTreatmentField, isPermit || isSickness)" in sync_body
    assert "setVisible(overtimeRateField, kind === 'overtime')" in sync_body
    assert "setVisible(document.getElementById('paidEntryField'), !isVacation)" in sync_body
    css = (Path(__file__).parents[1] / "src/colf_manager/static/style.css").read_text()
    assert ".hidden{display:none!important}" in css


def test_permit_hours_are_always_derived_from_start_and_end(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = 40
        db.session.commit()
    login(client)
    response = client.post(
        "/api/absence",
        json={
            "worker_id": worker_id,
            "kind": "permit",
            "start_date": "2026-09-15",
            "end_date": "2026-09-15",
            "start_time": "09:00",
            "end_time": "10:30",
            "permit_category": "medical",
            "paid": True,
            "paid_hours": "99",
        },
    )
    assert response.status_code == 201
    with app.app_context():
        absence = Absence.query.order_by(Absence.id.desc()).first()
        assert Decimal(absence.paid_hours) == Decimal("1.50")


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
    assert len(vacation_events) == 1
    assert vacation_events[0]["start"] == "2026-09-14"
    assert vacation_events[0]["end"] == "2026-09-16"
    assert vacation_events[0]["allDay"] is True
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
    assert sickness_events[0]["start"] == "2026-09-16"
    assert sickness_events[0]["allDay"] is True

    assert client.delete(f"/api/absence/{absence_id}").status_code == 200
    with app.app_context():
        assert Absence.query.count() == 0
        assert WorkEntry.query.count() == 1



def test_hour_types_paid_flags_and_overtime_rate(app):
    with app.app_context():
        rates = [HourlyRate(valid_from=date(2026, 1, 1), amount=Decimal("10.00"))]
        entries = [
            WorkEntry(work_date=date(2026, 9, 1), start_time=time(9), end_time=time(11), break_minutes=0, location="Casa", entry_kind="ordinary", paid=True),
            WorkEntry(work_date=date(2026, 9, 2), start_time=time(9), end_time=time(11), break_minutes=0, location="Casa", entry_kind="overtime", paid=True, rate_override=Decimal("15.00")),
            WorkEntry(work_date=date(2026, 9, 3), start_time=time(9), end_time=time(10), break_minutes=0, location="Casa", entry_kind="ordinary", paid=False),
        ]
        summary = monthly_summary(entries, [], [], rates, 2026, 9)
        assert summary["worked_hours"] == Decimal("5.00")
        assert summary["ordinary_hours"] == Decimal("3.00")
        assert summary["overtime_hours"] == Decimal("2.00")
        assert summary["unpaid_work_hours"] == Decimal("1.00")
        assert summary["worked_pay"] == Decimal("50.00")


def test_sickness_and_permit_default_to_paid_and_vacation_is_days(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("40")
        db.session.commit()
    login(client)
    sickness = client.post(
        "/api/absence",
        json={
            "worker_id": worker_id,
            "kind": "sickness",
            "start_date": "2026-09-10",
            "end_date": "2026-09-10",
        },
    )
    permit = client.post(
        "/api/absence",
        json={
            "worker_id": worker_id,
            "kind": "permit",
            "permit_category": "medical",
            "start_date": "2026-09-11",
            "end_date": "2026-09-11",
            "start_time": "09:00",
            "end_time": "10:00",
        },
    )
    assert sickness.status_code == 201
    assert permit.status_code == 201
    with app.app_context():
        records = Absence.query.order_by(Absence.id).all()
        assert records[0].kind == "sickness" and records[0].paid is True
        assert records[0].start_time is None and records[0].end_time is None
        assert records[1].kind == "permit" and records[1].paid is True

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


def test_legacy_work_entry_schema_is_upgraded_on_startup(tmp_path, monkeypatch):
    import sqlite3
    from sqlalchemy import inspect as sa_inspect

    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE work_entry (
                id INTEGER PRIMARY KEY,
                worker_id INTEGER,
                work_date DATE,
                start_time TIME,
                end_time TIME,
                break_minutes INTEGER NOT NULL DEFAULT 0,
                location VARCHAR(200)
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    legacy_app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "UPLOAD_FOLDER": str(tmp_path / "documents-legacy"),
            "REPORT_FOLDER": str(tmp_path / "reports-legacy"),
            "SESSION_COOKIE_SECURE": False,
            "TEST_ADMIN_PASSWORD": "Test-password-123",
        }
    )

    with legacy_app.app_context():
        columns = {column["name"] for column in sa_inspect(db.engine).get_columns("work_entry")}
        assert {"entry_kind", "paid", "rate_override", "location_id"} <= columns


def test_unlock_payroll_expense_allocation_reopens_quota(app, client):
    worker_id = make_worker(app)
    login(client)
    with app.app_context():
        expense = Expense(
            worker_id=worker_id,
            expense_date=date(2026, 9, 10),
            description="Quota cedolino",
            amount=Decimal("50.00"),
            direction="worker_advance",
            reimbursed=False,
        )
        db.session.add(expense)
        db.session.flush()
        allocation = ExpenseRecoveryAllocation(
            expense_id=expense.id,
            due_month=date(2026, 9, 1),
            amount=Decimal("50.00"),
            locked_at=datetime(2026, 9, 30, 12, 0),
        )
        db.session.add(allocation)
        db.session.commit()
        expense_id, allocation_id = expense.id, allocation.id
    response = client.post(
        f"/expenses/{expense_id}/recovery-allocations/{allocation_id}/unlock",
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        allocation = db.session.get(ExpenseRecoveryAllocation, allocation_id)
        assert allocation.locked_at is None


def test_deleted_paid_payment_no_longer_counts_as_paid(app, client):
    worker_id = make_worker(app)
    login(client)
    with app.app_context():
        payment = Payment(
            worker_id=worker_id,
            payment_type="salary",
            amount=Decimal("123.45"),
            status="paid",
            payment_date=date(2026, 9, 15),
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )
        db.session.add(payment)
        db.session.commit()
        payment_id = payment.id
    response = client.post(f"/payments/{payment_id}/delete", follow_redirects=False)
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Payment, payment_id) is None
        assert Payment.query.filter_by(status="paid").count() == 0


def test_reports_show_permit_values_and_annual_payment_totals(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("40")
        db.session.add(
            Absence(
                worker_id=worker_id,
                start_date=date(2026, 9, 10),
                end_date=date(2026, 9, 10),
                start_time=time(9),
                end_time=time(11),
                kind="permit",
                paid=True,
                paid_hours=Decimal("2"),
                permit_category="medical_visit",
            )
        )
        db.session.add(
            Payment(
                worker_id=worker_id,
                payment_type="salary",
                amount=Decimal("100.00"),
                status="paid",
                payment_date=date(2026, 9, 15),
                period_start=date(2026, 9, 1),
                period_end=date(2026, 9, 30),
            )
        )
        db.session.commit()
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=9")
    assert response.status_code == 200
    assert b"Retribuiti mese" in response.data
    assert b"Maturato" in response.data
    assert b"Totale annuo" in response.data
    assert b"Totale pagamenti effettuati" in response.data
    assert b"100,00" in response.data
    assert b"100.00" in response.data


def test_annual_payments_report_includes_only_paid_entries(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add_all([
            Payment(
                worker_id=worker_id,
                payment_type="salary",
                amount=Decimal("80.00"),
                status="paid",
                payment_date=date(2026, 5, 10),
            ),
            Payment(
                worker_id=worker_id,
                payment_type="tfr",
                amount=Decimal("90.00"),
                status="pending",
            ),
        ])
        db.session.commit()
    login(client)
    response = client.get("/reports/payments-annual.pdf?year=2026")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_mail_compose_default_body_uses_real_newlines(app, client):
    login(client)
    response = client.get("/mail/compose")
    assert response.status_code == 200
    assert b"Buongiorno,\n\nin allegato/in questa comunicazione trova il documento richiesto.\n\nCordiali saluti." in response.data
    assert b"Buongiorno,\\n\\nin allegato/in questa comunicazione" not in response.data


def test_expense_history_is_collapsed_paginated_and_searches_all_records(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("40")
        for index in range(12):
            db.session.add(
                Expense(
                    worker_id=worker_id,
                    expense_date=date(2026, 1, min(index + 1, 28)),
                    description=("Needle expense" if index == 0 else f"Expense {index:02d}"),
                    amount=Decimal("10.00") + index,
                    direction="worker_advance",
                    reimbursed=False,
                )
            )
        db.session.commit()

    login(client)
    first_page = client.get("/expenses")
    assert first_page.status_code == 200
    assert first_page.data.count(b'class="expense-history-item collapsible-card"') == 10
    assert b"Pagina 1 di 2" in first_page.data
    assert b"Needle expense" not in first_page.data

    second_page = client.get("/expenses?page=2")
    assert second_page.data.count(b'class="expense-history-item collapsible-card"') == 2
    assert b"Needle expense" in second_page.data

    search = client.get("/expenses?q=Needle")
    assert search.status_code == 200
    assert b"Needle expense" in search.data
    assert b"1 risultati su 12 movimenti" in search.data
    assert search.data.count(b'class="expense-history-item collapsible-card"') == 1


def test_payment_detail_does_not_depend_on_report_permit_aggregates(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        payment = Payment(
            worker_id=worker_id,
            payment_type="salary",
            amount=Decimal("10.00"),
            status="paid",
            payment_date=date(2026, 9, 15),
        )
        db.session.add(payment)
        db.session.commit()
        payment_id = payment.id

    login(client)
    response = client.get(f"/payments/{payment_id}")
    assert response.status_code == 200


def test_reports_show_annual_paid_and_unpaid_permit_hours_and_category_values(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("40")
        db.session.add_all(
            [
                Absence(
                    worker_id=worker_id,
                    start_date=date(2026, 3, 2),
                    end_date=date(2026, 3, 2),
                    start_time=time(9),
                    end_time=time(11),
                    kind="permit",
                    permit_category="medical_visit",
                    paid=True,
                    paid_hours=Decimal("2"),
                ),
                Absence(
                    worker_id=worker_id,
                    start_date=date(2026, 3, 3),
                    end_date=date(2026, 3, 3),
                    start_time=time(9),
                    end_time=time(10),
                    kind="permit",
                    permit_category="other",
                    paid=False,
                    paid_hours=Decimal("1"),
                ),
            ]
        )
        db.session.commit()

    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=3")
    assert response.status_code == 200
    assert b"Ore permesso retribuite" in response.data
    assert b"Ore permesso non retribuite" in response.data
    assert b'data-metric="report-permit-medical_visit-paid-year">2.00 h' in response.data
    assert b'data-metric="report-permit-other-unpaid-year">1.00 h' in response.data
    assert b"Residuo annuale" in response.data


def test_signature_image_crops_transparent_margins_before_centering(tmp_path):
    from PIL import Image, ImageDraw

    path = tmp_path / "signature.png"
    source = Image.new("RGB", (600, 180), "white")
    draw = ImageDraw.Draw(source)
    draw.line((40, 90, 180, 70), fill="black", width=8)
    source.save(path)

    signature = _signature_image(path)
    assert signature is not None
    assert signature.imageWidth < 200
    assert signature.hAlign == "CENTER"


def test_reports_show_monthly_compensation_breakdown_and_vacation_days(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("40")
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 1, 1), amount=Decimal("10.00")))
        db.session.add_all([
            WorkEntry(worker_id=worker_id, work_date=date(2026, 9, 1), start_time=time(9), end_time=time(11), break_minutes=0, entry_kind="ordinary", paid=True, location="Casa"),
            WorkEntry(worker_id=worker_id, work_date=date(2026, 9, 2), start_time=time(9), end_time=time(10), break_minutes=0, entry_kind="overtime", paid=True, rate_override=Decimal("15.00"), location="Casa"),
            Absence(worker_id=worker_id, start_date=date(2026, 9, 3), end_date=date(2026, 9, 3), start_time=time(9), end_time=time(10), kind="permit", permit_category="medical", paid=True, paid_hours=Decimal("1")),
            Absence(worker_id=worker_id, start_date=date(2026, 9, 4), end_date=date(2026, 9, 4), kind="sickness", paid=True, paid_hours=Decimal("1")),
            Absence(worker_id=worker_id, start_date=date(2026, 9, 7), end_date=date(2026, 9, 7), kind="vacation", paid=True, paid_hours=Decimal("1")),
        ])
        db.session.commit()
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=9")
    assert response.status_code == 200
    assert b"Dettaglio costo retribuzione mensile" in response.data
    assert b"Ore ordinarie" in response.data
    assert b"Ore straordinarie" in response.data
    assert b"Permessi retribuiti" in response.data
    assert b"Malattia" in response.data
    assert b"Ferie" in response.data
    assert b'data-metric="vacation-days-used-month">1.00' in response.data


def test_calendar_date_jump_controls_and_goto_date(app, client):
    login(client)
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b'id="calendarJumpDay"' in response.data
    assert b'id="calendarJumpMonth"' in response.data
    assert b'id="calendarJumpYear"' in response.data
    assert b'id="calendarJumpButton"' in response.data
    script = (Path(__file__).resolve().parents[1] / "src" / "colf_manager" / "static" / "calendar.js").read_text()
    assert "jumpToCalendarDate" in script
    assert "calendar.gotoDate(target)" in script


def test_calendar_quick_patterns_are_ranked_by_usage_then_recency(app, client):
    login(client)
    employer = Employer(first_name="Mario", last_name="Datore")
    worker = Worker(first_name="Anna", last_name="Lavoratore", employment_start=date(2026, 1, 1))
    location = Location(name="Casa")
    with app.app_context():
        db.session.add_all([employer, worker, location])
        db.session.flush()
        worker.employer_id = employer.id
        db.session.add_all([
            WorkEntry(worker_id=worker.id, location_id=location.id, location="Casa", work_date=date(2026, 9, 1), start_time=time(8), end_time=time(10), break_minutes=0, entry_kind="ordinary", paid=True),
            WorkEntry(worker_id=worker.id, location_id=location.id, location="Casa", work_date=date(2026, 9, 2), start_time=time(8), end_time=time(10), break_minutes=0, entry_kind="ordinary", paid=True),
            WorkEntry(worker_id=worker.id, location_id=location.id, location="Casa", work_date=date(2026, 9, 3), start_time=time(8), end_time=time(10), break_minutes=0, entry_kind="ordinary", paid=True),
            WorkEntry(worker_id=worker.id, location_id=location.id, location="Casa", work_date=date(2026, 9, 10), start_time=time(15), end_time=time(17), break_minutes=0, entry_kind="ordinary", paid=True),
        ])
        db.session.commit()
    response = client.get("/calendar")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    first = html.index('data-start="08:00"')
    second = html.index('data-start="15:00"')
    assert first < second
    assert 'data-usage-count="3"' in html


def test_calendar_exposes_quick_delete_without_opening_edit_dialog(app, client):
    login(client)
    response = client.get("/calendar")
    assert response.status_code == 200
    script = (Path(__file__).resolve().parents[1] / "src" / "colf_manager" / "static" / "calendar.js").read_text()
    assert "quickDeleteCalendarEvent" in script
    assert "calendar-quick-delete" in script
    assert "Elimina senza aprire" in script


def test_signature_story_centres_signature_with_nested_table(tmp_path):
    from PIL import Image, ImageDraw
    from colf_manager.reporting import _signature_story, _styles

    path = tmp_path / "signature-offset.png"
    source = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(source)
    draw.line((20, 110, 180, 80), fill="black", width=8)
    source.save(path)

    class Person:
        first_name = "Mario"
        last_name = "Rossi"

    story = _signature_story(
        Person(),
        Person(),
        _styles(),
        {
            "mode": "employer",
            "place": "Roma",
            "date": date(2026, 9, 16),
            "employer_signature": str(path),
        },
    )
    outer = story[-1]
    cell_flowables = outer._cellvalues[0][0]
    nested_tables = [item for item in cell_flowables if item.__class__.__name__ == "Table"]
    assert nested_tables, "La firma deve essere centrata tramite una tabella interna"


def test_continuous_vacation_pay_is_charged_in_end_month(app):
    with app.app_context():
        worker = Worker(
            first_name="Anna",
            last_name="Ferie",
            employment_start=date(2026, 1, 1),
            weekly_hours=Decimal("20"),
        )
        rates = [HourlyRate(valid_from=date(2026, 1, 1), amount=Decimal("9.00"))]
        paid_hours = vacation_hours_per_day(worker) * Decimal(
            vacation_working_days(date(2026, 7, 31), date(2026, 8, 31))
        )
        absence = Absence(
            start_date=date(2026, 7, 31),
            end_date=date(2026, 8, 31),
            kind="vacation",
            paid=True,
            paid_hours=paid_hours,
        )

        july = monthly_summary([], [absence], [], rates, 2026, 7, worker=worker)
        august = monthly_summary([], [absence], [], rates, 2026, 8, worker=worker)
        annual = annual_summary([], [absence], [], rates, 2026, worker=worker)

        assert vacation_working_days(date(2026, 7, 31), date(2026, 8, 31)) == 26
        assert july["vacation_days_used_month"] == Decimal("1.00")
        assert august["vacation_days_used_month"] == Decimal("25.00")
        # Fruition remains attributed to the actual months, while the entire
        # economic value of one continuous vacation period is charged in its
        # ending month.
        assert july["vacation_pay"] == Decimal("0.00")
        assert august["vacation_pay"] == Decimal("779.94")
        assert annual["vacation_pay"] == Decimal("779.94")


def test_vacation_daily_value_for_20_hours_week_at_9_euro(app):
    with app.app_context():
        worker = Worker(
            first_name="Anna",
            last_name="Ferie",
            employment_start=date(2026, 1, 1),
            weekly_hours=Decimal("20"),
        )
        hours = vacation_hours_per_day(worker)
        assert hours.quantize(Decimal("0.0001")) == Decimal("3.3331")
        assert money(hours * Decimal("9.00")) == Decimal("30.00")


def test_vacation_legacy_paid_hours_are_recomputed_and_carry_is_reported(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.weekly_hours = Decimal("20")
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 1, 1), amount=Decimal("9.00")))
        # Simulate a legacy event saved with only 25 days worth of paid_hours.
        stale_paid_hours = vacation_hours_per_day(worker) * Decimal("25")
        db.session.add(
            Absence(
                worker_id=worker_id,
                start_date=date(2026, 7, 31),
                end_date=date(2026, 8, 31),
                kind="vacation",
                paid=True,
                paid_hours=stale_paid_hours,
            )
        )
        db.session.commit()

        rates = HourlyRate.query.filter_by(worker_id=worker_id).all()
        absences = Absence.query.filter_by(worker_id=worker_id).all()
        july = monthly_summary([], absences, [], rates, 2026, 7, worker=worker)
        august = monthly_summary([], absences, [], rates, 2026, 8, worker=worker)

        assert july["vacation_pay"] == Decimal("0.00")
        assert july["vacation_pay_deferred"] == Decimal("779.94")
        assert august["vacation_pay"] == Decimal("779.94")
        assert august["vacation_pay_carry_in"] == Decimal("779.94")
        assert "riportata a 08/2026" in july["vacation_payroll_notes"][0]
        assert "mesi precedenti" in august["vacation_payroll_notes"][0]

    login(client)
    july_page = client.get(f"/reports?worker_id={worker_id}&year=2026&month=7")
    assert july_page.status_code == 200
    assert b"Riporto retribuzione ferie" in july_page.data
    assert b"Retribuzione ferie rinviata" in july_page.data
    assert b"779.94" in july_page.data

    august_page = client.get(f"/reports?worker_id={worker_id}&year=2026&month=8")
    assert august_page.status_code == 200
    assert b"Riporto ferie incluso nel mese" in august_page.data
    assert b"779.94" in august_page.data


def test_vacation_more_than_three_days_in_start_month_stays_in_each_month(app):
    with app.app_context():
        worker = Worker(
            first_name="Anna",
            last_name="Ferie",
            employment_start=date(2026, 1, 1),
            weekly_hours=Decimal("20"),
        )
        rates = [HourlyRate(valid_from=date(2026, 1, 1), amount=Decimal("9.00"))]
        absence = Absence(
            start_date=date(2026, 7, 28),
            end_date=date(2026, 8, 31),
            kind="vacation",
            paid=True,
            paid_hours=Decimal("999"),  # legacy value must not drive the calculation
        )

        july = monthly_summary([], [absence], [], rates, 2026, 7, worker=worker)
        august = monthly_summary([], [absence], [], rates, 2026, 8, worker=worker)

        assert july["vacation_days_used_month"] == Decimal("4.00")
        assert july["vacation_pay"] == Decimal("119.99")
        assert august["vacation_days_used_month"] == Decimal("25.00")
        assert august["vacation_pay"] == Decimal("749.94")
        assert july["vacation_pay_deferred"] == Decimal("0.00")
        assert august["vacation_pay_carry_in"] == Decimal("0.00")


def test_payment_receipt_is_available_only_for_paid_payments(app, client):
    with app.app_context():
        employer = Employer(first_name="Mario", last_name="Datore", city="Roma")
        db.session.add(employer)
        db.session.flush()
        worker = Worker(
            employer_id=employer.id,
            first_name="Anna",
            last_name="Lavoratrice",
            employment_start=date(2026, 1, 1),
            weekly_hours=Decimal("20"),
        )
        db.session.add(worker)
        db.session.flush()
        paid = Payment(
            worker_id=worker.id,
            employer_id=employer.id,
            payment_type="other",
            amount=Decimal("123.45"),
            status="paid",
            payment_date=date(2026, 9, 16),
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )
        pending = Payment(
            worker_id=worker.id,
            employer_id=employer.id,
            payment_type="other",
            amount=Decimal("50.00"),
            status="pending",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )
        db.session.add_all([paid, pending])
        db.session.commit()
        paid_id, pending_id = paid.id, pending.id

    login(client)
    response = client.get(f"/payments/{paid_id}/receipt.pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert "quietanza-pagamento" in response.headers.get("Content-Disposition", "")

    assert client.get(f"/payments/{pending_id}/receipt.pdf").status_code == 404
    detail = client.get(f"/payments/{paid_id}")
    assert b"Scarica quietanza PDF" in detail.data


def test_vacation_exactly_three_days_in_start_month_is_deferred(app):
    with app.app_context():
        worker = Worker(
            first_name="Anna",
            last_name="Ferie",
            employment_start=date(2026, 1, 1),
            weekly_hours=Decimal("20"),
        )
        rates = [HourlyRate(valid_from=date(2026, 1, 1), amount=Decimal("9.00"))]
        absence = Absence(
            start_date=date(2026, 7, 29),
            end_date=date(2026, 8, 31),
            kind="vacation",
            paid=True,
            paid_hours=Decimal("999"),
        )
        july = monthly_summary([], [absence], [], rates, 2026, 7, worker=worker)
        august = monthly_summary([], [absence], [], rates, 2026, 8, worker=worker)

        assert july["vacation_days_used_month"] == Decimal("3.00")
        assert july["vacation_pay"] == Decimal("0.00")
        assert july["vacation_pay_deferred"] == Decimal("839.94")
        assert august["vacation_pay"] == Decimal("839.94")
        assert august["vacation_pay_carry_in"] == Decimal("839.94")


def test_marking_payment_paid_replaces_existing_monthly_payroll(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 9, 1), amount=Decimal("10.00")))
        db.session.add(
            WorkEntry(
                worker_id=worker_id,
                work_date=date(2026, 9, 7),
                start_time=time(9),
                end_time=time(11),
                break_minutes=0,
                location="Casa",
            )
        )
        db.session.commit()

    login(client)
    generated = client.get(f"/reports/payroll.pdf?worker_id={worker_id}&year=2026&month=9")
    assert generated.status_code == 200

    with app.app_context():
        report = GeneratedReport.query.filter_by(worker_id=worker_id, report_type="monthly_payroll").one()
        payment = Payment.query.filter_by(
            worker_id=worker_id,
            payment_type="salary",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        ).one()
        assert payment.status == "pending"
        assert payment.source_report_id == report.id
        report_id = report.id
        old_hash = report.sha256
        old_stored = report.stored_name
        payment_id = payment.id
        amount = str(payment.amount)
        old_path = Path(app.config["REPORT_FOLDER"]) / old_stored
        assert old_path.exists()

    response = client.post(
        f"/payments/{payment_id}/edit",
        data={
            "worker_id": str(worker_id),
            "payment_type": "salary",
            "amount": amount,
            "status": "paid",
            "payment_date": "2026-09-30",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
            "description": "Retribuzione settembre",
            "notes": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        assert GeneratedReport.query.filter_by(worker_id=worker_id, report_type="monthly_payroll").count() == 1
        refreshed = db.session.get(GeneratedReport, report_id)
        updated_payment = db.session.get(Payment, payment_id)
        assert refreshed is not None
        assert refreshed.sha256 != old_hash
        assert refreshed.stored_name != old_stored
        assert updated_payment.status == "paid"
        assert updated_payment.source_report_id == report_id
        assert not (Path(app.config["REPORT_FOLDER"]) / old_stored).exists()
        assert (Path(app.config["REPORT_FOLDER"]) / refreshed.stored_name).exists()


def test_deleting_paid_payment_replaces_existing_monthly_payroll(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 10, 1), amount=Decimal("10.00")))
        db.session.add(
            WorkEntry(
                worker_id=worker_id,
                work_date=date(2026, 10, 5),
                start_time=time(9),
                end_time=time(11),
                break_minutes=0,
                location="Casa",
            )
        )
        db.session.commit()

    login(client)
    assert client.get(f"/reports/payroll.pdf?worker_id={worker_id}&year=2026&month=10").status_code == 200
    with app.app_context():
        report = GeneratedReport.query.filter_by(worker_id=worker_id, report_type="monthly_payroll").one()
        payment = Payment.query.filter_by(worker_id=worker_id, payment_type="salary").one()
        payment.status = "paid"
        payment.payment_date = date(2026, 10, 31)
        db.session.commit()
        report_id = report.id
        payment_id = payment.id

    # First force the archived payroll to reflect the paid status through the edit path.
    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        amount = str(payment.amount)
    assert client.post(
        f"/payments/{payment_id}/edit",
        data={
            "worker_id": str(worker_id),
            "payment_type": "salary",
            "amount": amount,
            "status": "paid",
            "payment_date": "2026-10-31",
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            "description": "Retribuzione ottobre",
            "notes": "",
        },
    ).status_code == 302

    with app.app_context():
        before_delete = db.session.get(GeneratedReport, report_id)
        paid_hash = before_delete.sha256

    assert client.post(f"/payments/{payment_id}/delete", follow_redirects=False).status_code == 302

    with app.app_context():
        refreshed = db.session.get(GeneratedReport, report_id)
        assert refreshed is not None
        assert refreshed.sha256 != paid_hash
        assert db.session.get(Payment, payment_id) is None
        assert GeneratedReport.query.filter_by(worker_id=worker_id, report_type="monthly_payroll").count() == 1


def test_reports_archive_search_paginates_all_rows_and_uses_descriptions(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        worker = db.session.get(Worker, worker_id)
        worker.fiscal_code = "RSSMRA80A01H501U"
        folder = Path(app.config["REPORT_FOLDER"])
        folder.mkdir(parents=True, exist_ok=True)
        for idx in range(12):
            filename = f"RSSMRA80A01H501U_report-{idx:02d}.pdf"
            stored = f"stored-{idx:02d}-{filename}"
            (folder / stored).write_bytes(b"%PDF-1.4\n%%EOF")
            db.session.add(
                GeneratedReport(
                    worker_id=worker_id,
                    report_type="monthly_payroll" if idx == 11 else "trend",
                    filename=filename,
                    stored_name=stored,
                    sha256=f"{idx:064x}"[-64:],
                    size_bytes=14,
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 31),
                )
            )
        db.session.commit()
    login(client)
    page = client.get(f"/reports?worker_id={worker_id}&year=2026&month=1")
    assert page.status_code == 200
    assert page.data.count(b"/reports/archive/") >= 10
    assert b"massimo 10 per pagina" in page.data
    found = client.get(
        f"/reports?worker_id={worker_id}&year=2026&month=1&archive_q=report-11"
    )
    assert found.status_code == 200
    assert b"report-11.pdf" in found.data
    assert b"Cedolino mensile" in found.data


def test_report_manual_approval_override(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        report = GeneratedReport(
            worker_id=worker_id,
            report_type="trend",
            filename="SENZA-CF-test.pdf",
            stored_name="approval-test.pdf",
            sha256="a" * 64,
            size_bytes=10,
        )
        Path(app.config["REPORT_FOLDER"], report.stored_name).write_bytes(b"%PDF-1.4")
        db.session.add(report)
        db.session.commit()
        report_id = report.id
    login(client)
    assert client.post(
        f"/reports/archive/{report_id}/approval", data={"action": "approve"}
    ).status_code == 302
    with app.app_context():
        assert db.session.get(GeneratedReport, report_id).approval_override is True
    assert client.post(
        f"/reports/archive/{report_id}/approval", data={"action": "unapprove"}
    ).status_code == 302
    with app.app_context():
        assert db.session.get(GeneratedReport, report_id).approval_override is False
    assert client.post(
        f"/reports/archive/{report_id}/approval", data={"action": "auto"}
    ).status_code == 302
    with app.app_context():
        assert db.session.get(GeneratedReport, report_id).approval_override is None


def test_reports_total_hours_include_paid_and_unpaid_permits(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(HourlyRate(worker_id=worker_id, valid_from=date(2026, 1, 1), amount=10))
        db.session.add(WorkEntry(worker_id=worker_id, work_date=date(2026, 1, 5), start_time=time(9), end_time=time(11), break_minutes=0, location="Casa"))
        db.session.add(Absence(worker_id=worker_id, kind="permit", start_date=date(2026, 1, 6), end_date=date(2026, 1, 6), start_time=time(9), end_time=time(10), paid=True, permit_category="medical"))
        db.session.add(Absence(worker_id=worker_id, kind="permit", start_date=date(2026, 1, 7), end_date=date(2026, 1, 7), start_time=time(9), end_time=time(10, 30), paid=False, permit_category="other"))
        db.session.commit()
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=1")
    assert response.status_code == 200
    assert b'data-metric="monthly-total-hours">4.50 h' in response.data
    assert b'data-metric="annual-total-hours">4.50 h' in response.data


def test_currency_formatter_always_uses_two_decimal_digits():
    from colf_manager.formatting import currency

    assert currency(10) == "€ 10,00"
    assert currency("125.5") == "€ 125,50"
    assert currency(0) == "€ 0,00"
    assert currency("12.345") == "€ 12,35"


def test_reports_currency_values_have_two_decimal_digits(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(
            HourlyRate(
                worker_id=worker_id,
                valid_from=date(2026, 1, 1),
                amount=10,
            )
        )
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
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=1")
    assert response.status_code == 200
    assert "€ 10,00".encode() in response.data
    assert "€ 10.0<".encode() not in response.data


def test_payment_method_defaults_to_bank_transfer_and_can_be_changed(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/payments",
        data={
            "worker_id": worker_id,
            "payment_type": "salary",
            "amount": "100.00",
            "status": "pending",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        payment = Payment.query.order_by(Payment.id.desc()).first()
        assert payment.payment_method == "bank_transfer"
        payment_id = payment.id

    response = client.post(
        f"/payments/{payment_id}/edit",
        data={
            "worker_id": worker_id,
            "payment_type": "salary",
            "payment_method": "cash",
            "amount": "100.00",
            "status": "paid",
            "payment_date": "2026-09-16",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        assert payment.payment_method == "cash"

    detail = client.get(f"/payments/{payment_id}")
    assert b"Modalit" in detail.data
    assert b"Contanti" in detail.data


def test_payment_method_rejects_invalid_value(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.post(
        "/payments",
        data={
            "worker_id": worker_id,
            "payment_type": "salary",
            "payment_method": "crypto",
            "amount": "10.00",
            "status": "pending",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Modalità di pagamento non valida".encode() in response.data
    with app.app_context():
        assert Payment.query.count() == 0


def test_payments_default_order_is_most_recent_period_first(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        db.session.add(
            Payment(
                worker_id=worker_id,
                payment_type="salary",
                amount=111.11,
                status="pending",
                period_start=date(2026, 12, 1),
                period_end=date(2026, 12, 31),
                description="Periodo recente",
            )
        )
        db.session.flush()
        db.session.add(
            Payment(
                worker_id=worker_id,
                payment_type="salary",
                amount=222.22,
                status="pending",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                description="Periodo vecchio",
            )
        )
        db.session.commit()
    login(client)
    response = client.get(f"/payments?worker_id={worker_id}")
    assert response.status_code == 200
    recent = response.data.find(b"2026-12-01")
    old = response.data.find(b"2026-01-01")
    assert recent >= 0 and old >= 0
    assert recent < old


def test_archived_reports_default_order_is_most_recent_period_first(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        folder = Path(app.config["REPORT_FOLDER"])
        folder.mkdir(parents=True, exist_ok=True)
        for filename, stored, start, end in [
            ("SENZA-CF-report-recente.pdf", "sort-period-recent.pdf", date(2026, 12, 1), date(2026, 12, 31)),
            ("SENZA-CF-report-vecchio.pdf", "sort-period-old.pdf", date(2026, 1, 1), date(2026, 1, 31)),
        ]:
            (folder / stored).write_bytes(b"%PDF-1.4\n%%EOF")
            db.session.add(
                GeneratedReport(
                    worker_id=worker_id,
                    report_type="trend",
                    filename=filename,
                    stored_name=stored,
                    sha256=("a" if "recente" in filename else "b") * 64,
                    size_bytes=14,
                    period_start=start,
                    period_end=end,
                )
            )
        db.session.commit()
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=12")
    assert response.status_code == 200
    assert b"archive_sort=period" in response.data
    recent = response.data.find(b"report-recente.pdf")
    old = response.data.find(b"report-vecchio.pdf")
    assert recent >= 0 and old >= 0
    assert recent < old


def test_archived_reports_show_liquidated_amount_and_graphical_approval(app, client):
    worker_id = make_worker(app)
    with app.app_context():
        folder = Path(app.config["REPORT_FOLDER"])
        folder.mkdir(parents=True, exist_ok=True)
        stored = "r95-liquidated-test.pdf"
        (folder / stored).write_bytes(b"%PDF-1.4\n%%EOF")
        report = GeneratedReport(
            worker_id=worker_id,
            report_type="monthly_payroll",
            filename="SENZA-CF-cedolino-2026-08.pdf",
            stored_name=stored,
            sha256="c" * 64,
            size_bytes=14,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            approval_override=True,
        )
        db.session.add(report)
        db.session.flush()
        db.session.add(
            Payment(
                worker_id=worker_id,
                source_report_id=report.id,
                payment_type="salary",
                amount=Decimal("123.45"),
                status="paid",
                payment_date=date(2026, 9, 1),
                period_start=date(2026, 8, 1),
                period_end=date(2026, 8, 31),
            )
        )
        db.session.commit()
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=8")
    assert response.status_code == 200
    assert b"archive-liquidated" in response.data
    assert "€ 123,45".encode() in response.data
    assert b"approval-status-icon approved" in response.data
    assert b"archive-actions" in response.data
    assert b"archive_sort=liquidated" in response.data


def test_report_sections_are_collapsed_by_default_and_collapsible_state_uses_cookie(app, client):
    worker_id = make_worker(app)
    login(client)
    response = client.get(f"/reports?worker_id={worker_id}&year=2026&month=1")
    assert response.status_code == 200
    assert b'data-collapse-key="reports-annual-summary"' in response.data
    assert b'data-collapse-key="reports-archive"' in response.data
    assert b"cm_collapsible_state" in response.data
    assert b"Max-Age=${maxAge}" in response.data
    assert b"SameSite=Lax" in response.data


def test_all_current_collapsible_templates_have_persistent_keys():
    root = Path(__file__).resolve().parents[1] / "src" / "colf_manager" / "templates"
    dashboard = (root / "dashboard.html").read_text()
    expenses = (root / "expenses.html").read_text()
    reports = (root / "reports.html").read_text()
    assert 'data-collapse-key="dashboard-hours-pay"' in dashboard
    assert 'data-collapse-key="dashboard-vacation-sickness"' in dashboard
    assert 'data-collapse-key="dashboard-permits"' in dashboard
    assert 'data-collapse-key="dashboard-activity"' in dashboard
    assert 'data-collapse-key="expense-history-{{e.id}}"' in expenses
    assert 'data-collapse-key="reports-annual-summary"' in reports
    assert 'data-collapse-key="reports-permits"' in reports
    assert 'data-collapse-key="reports-archive"' in reports
