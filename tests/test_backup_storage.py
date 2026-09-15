from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path
import os
import zipfile

import pytest

from colf_manager.app import create_app
from colf_manager.backup import create_full_export, restore_full_export
from colf_manager.models import (
    AuditLog,
    Document,
    GeneratedReport,
    Payment,
    PaymentAttachment,
    WorkEntry,
    Worker,
    db,
)
from colf_manager.storage import cleanup_orphan_files, safe_unlink, store_report


@pytest.fixture()
def archive_app(tmp_path):
    app = create_app(
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
    return app


def _seed_archive_data(app):
    with app.app_context():
        worker = Worker(
            first_name="Archivio",
            last_name="Test",
            employment_start=date(2026, 1, 1),
        )
        db.session.add(worker)
        db.session.flush()

        upload_dir = Path(app.config["UPLOAD_FOLDER"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_name = "contract-test.pdf"
        payload = b"%PDF-1.4\ncontract\n%%EOF"
        (upload_dir / stored_name).write_bytes(payload)
        db.session.add(
            Document(
                worker_id=worker.id,
                filename="contract.pdf",
                stored_name=stored_name,
                category="contract",
                mime_type="application/pdf",
                sha256="0" * 64,
                size_bytes=len(payload),
            )
        )
        db.session.commit()

        report = store_report(
            app,
            worker.id,
            "monthly_payroll",
            "cedolino-2026-01.pdf",
            b"%PDF-1.4\nreport\n%%EOF",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )
        signature_dir = Path(app.config["SIGNATURE_FOLDER"])
        signature_dir.mkdir(parents=True, exist_ok=True)
        worker.signature_stored_name = "worker-signature.png"
        worker.signature_filename = "firma.png"
        worker.signature_mime_type = "image/png"
        (signature_dir / worker.signature_stored_name).write_bytes(b"signature")

        payment = Payment(
            worker_id=worker.id,
            source_report_id=report.id,
            payment_type="salary",
            amount=100,
            status="paid",
            payment_date=date(2026, 2, 1),
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )
        db.session.add(payment)
        db.session.flush()
        payment_dir = Path(app.config["PAYMENT_FOLDER"])
        payment_dir.mkdir(parents=True, exist_ok=True)
        attachment_name = "quietanza-test.pdf"
        attachment_payload = b"%PDF-1.4\nreceipt\n%%EOF"
        (payment_dir / attachment_name).write_bytes(attachment_payload)
        db.session.add(
            PaymentAttachment(
                payment_id=payment.id,
                filename="quietanza.pdf",
                stored_name=attachment_name,
                mime_type="application/pdf",
                sha256="1" * 64,
                size_bytes=len(attachment_payload),
            )
        )
        db.session.commit()
        return worker.id, report.id


def test_full_export_contains_database_documents_and_reports(archive_app):
    _seed_archive_data(archive_app)
    with archive_app.app_context():
        archive = create_full_export(archive_app)
        assert archive.is_file()
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            assert "manifest.json" in names
            assert "database.json" in names
            assert "files/documents/contract-test.pdf" in names
            assert any(name.startswith("files/reports/") for name in names)
            assert "files/signatures/worker-signature.png" in names
            assert "files/payments/quietanza-test.pdf" in names


def test_full_export_round_trip_restores_database_and_files(archive_app):
    worker_id, _ = _seed_archive_data(archive_app)
    with archive_app.app_context():
        archive = create_full_export(archive_app)
        worker = db.session.get(Worker, worker_id)
        worker.first_name = "Changed"
        db.session.commit()
        for folder_key in ("UPLOAD_FOLDER", "REPORT_FOLDER", "SIGNATURE_FOLDER", "PAYMENT_FOLDER"):
            for path in Path(archive_app.config[folder_key]).iterdir():
                if path.is_file():
                    path.unlink()

        with archive.open("rb") as stream:
            result = restore_full_export(archive_app, stream)

        restored = db.session.get(Worker, worker_id)
        assert restored.first_name == "Archivio"
        assert result["source_version"] == "1.0.0"
        assert Document.query.count() == 1
        assert GeneratedReport.query.count() == 1
        assert Payment.query.count() == 1
        assert PaymentAttachment.query.count() == 1
        document = Document.query.one()
        report = GeneratedReport.query.one()
        restored_worker = db.session.get(Worker, worker_id)
        attachment = PaymentAttachment.query.one()
        assert (Path(archive_app.config["UPLOAD_FOLDER"]) / document.stored_name).is_file()
        assert (Path(archive_app.config["REPORT_FOLDER"]) / report.stored_name).is_file()
        assert (
            Path(archive_app.config["SIGNATURE_FOLDER"]) / restored_worker.signature_stored_name
        ).is_file()
        assert (Path(archive_app.config["PAYMENT_FOLDER"]) / attachment.stored_name).is_file()


def test_full_export_round_trip_preserves_time_values(archive_app):
    worker_id, _ = _seed_archive_data(archive_app)
    with archive_app.app_context():
        entry = WorkEntry(
            worker_id=worker_id,
            work_date=date(2026, 9, 15),
            start_time=time(8, 30),
            end_time=time(12, 45),
            break_minutes=15,
            location="Casa",
        )
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

        archive = create_full_export(archive_app)
        with archive.open("rb") as stream:
            restore_full_export(archive_app, stream)

        restored = db.session.get(WorkEntry, entry_id)
        assert restored is not None
        assert restored.start_time == time(8, 30)
        assert restored.end_time == time(12, 45)


def test_restore_rejects_unsafe_archive_member(archive_app):
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("../escape.txt", b"bad")
        zf.writestr("manifest.json", b"{}")
        zf.writestr("database.json", b"{}")
    payload.seek(0)
    with archive_app.app_context(), pytest.raises(ValueError, match="percorso non sicuro"):
        restore_full_export(archive_app, payload)


def test_orphan_cleanup_preserves_referenced_files_and_audits(archive_app):
    worker_id, _ = _seed_archive_data(archive_app)
    with archive_app.app_context():
        upload_dir = Path(archive_app.config["UPLOAD_FOLDER"])
        report_dir = Path(archive_app.config["REPORT_FOLDER"])
        document = Document.query.one()
        report = GeneratedReport.query.one()
        referenced_document = upload_dir / document.stored_name
        referenced_report = report_dir / report.stored_name

        orphan = upload_dir / "orphan.bin"
        orphan.write_bytes(b"orphan")
        old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
        os.utime(orphan, (old, old))

        dry_run = cleanup_orphan_files(archive_app, retention_hours=0, dry_run=True)
        assert str(orphan) in dry_run["deleted"]
        assert orphan.exists()

        result = cleanup_orphan_files(archive_app, retention_hours=0)
        assert str(orphan) in result["deleted"]
        assert not orphan.exists()
        assert referenced_document.exists()
        assert referenced_report.exists()
        assert AuditLog.query.filter_by(action="orphan_cleanup").count() == 1
        assert db.session.get(Worker, worker_id) is not None


def test_orphan_cleanup_skips_recent_and_safe_unlink_handles_directory(archive_app):
    with archive_app.app_context():
        upload_dir = Path(archive_app.config["UPLOAD_FOLDER"])
        recent = upload_dir / "recent.tmp"
        recent.write_bytes(b"recent")
        result = cleanup_orphan_files(archive_app, retention_hours=24, dry_run=True)
        assert str(recent) in result["skipped_recent"]
        assert safe_unlink(upload_dir) is False
