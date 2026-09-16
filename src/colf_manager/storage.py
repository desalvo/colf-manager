from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import (
    AuditLog,
    Document,
    Employer,
    ExpenseSettlement,
    GeneratedReport,
    PaymentAttachment,
    Worker,
    db,
)


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def safe_unlink(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _report_cf_prefix(worker_id):
    if worker_id is None:
        return "MULTI-CF"
    worker = db.session.get(Worker, worker_id)
    if worker is None:
        return f"SENZA-CF-{worker_id}"
    fiscal_code = "".join(ch for ch in (worker.fiscal_code or "").upper() if ch.isalnum())
    return fiscal_code or f"SENZA-CF-{worker.id}"


def prefixed_report_filename(worker_id, filename):
    prefix = _report_cf_prefix(worker_id)
    safe_name = Path(filename).name
    if safe_name.upper().startswith(prefix.upper() + "_"):
        return safe_name
    # Replace a previous fallback/CF prefix rather than stacking prefixes when
    # the worker fiscal code is populated or corrected later.
    if re.match(r"^SENZA-CF-\d+_", safe_name, flags=re.IGNORECASE):
        safe_name = safe_name.split("_", 1)[1]
    elif worker_id is not None and re.match(r"^[A-Z0-9]{16}_", safe_name, flags=re.IGNORECASE):
        safe_name = safe_name.split("_", 1)[1]
    elif worker_id is None and safe_name.upper().startswith("MULTI-CF_"):
        safe_name = safe_name.split("_", 1)[1]
    return f"{prefix}_{safe_name}"


def normalize_archived_report_filenames(app):
    """Prefix archived report filenames with worker fiscal codes and migrate files in place."""
    report_dir = Path(app.config["REPORT_FOLDER"])
    report_dir.mkdir(parents=True, exist_ok=True)
    changed = 0
    for report in GeneratedReport.query.order_by(GeneratedReport.id).all():
        wanted_filename = prefixed_report_filename(report.worker_id, report.filename)
        if wanted_filename == report.filename:
            continue
        old_path = report_dir / report.stored_name
        # Preserve the storage uniqueness prefix while replacing only the user-facing suffix.
        marker = report.filename
        if report.stored_name.endswith(marker):
            new_stored = report.stored_name[: -len(marker)] + wanted_filename
        else:
            new_stored = f"migrated-{report.id}-{wanted_filename}"
        target = report_dir / new_stored
        if old_path.exists() and old_path != target:
            if target.exists():
                target = report_dir / f"migrated-{report.id}-{wanted_filename}"
                new_stored = target.name
            old_path.replace(target)
        report.filename = wanted_filename
        report.stored_name = new_stored
        changed += 1
    if changed:
        db.session.commit()
    return changed


def store_report(
    app,
    worker_id,
    report_type,
    filename,
    payload,
    period_start=None,
    period_end=None,
):
    report_dir = Path(app.config["REPORT_FOLDER"])
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = prefixed_report_filename(worker_id, filename)
    digest = hashlib.sha256(payload).hexdigest()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stored_name = f"{timestamp}-{digest[:16]}-{filename}"
    destination = report_dir / stored_name
    destination.write_bytes(payload)
    report = GeneratedReport(
        worker_id=worker_id,
        report_type=report_type,
        filename=filename,
        stored_name=stored_name,
        mime_type="application/pdf",
        sha256=digest,
        size_bytes=len(payload),
        period_start=period_start,
        period_end=period_end,
    )
    db.session.add(report)
    db.session.commit()
    return report


def cleanup_orphan_files(app, retention_hours=None, dry_run=False):
    retention_hours = int(
        retention_hours
        if retention_hours is not None
        else os.getenv("COLF_MANAGER_ORPHAN_RETENTION_HOURS", "24")
    )
    cutoff = _utcnow() - timedelta(hours=max(retention_hours, 0))
    referenced = {
        Path(app.config["UPLOAD_FOLDER"]): {
            stored_name
            for stored_name in [
                *[document.stored_name for document in Document.query.all()],
                *[
                    settlement.stored_name
                    for settlement in ExpenseSettlement.query.all()
                    if settlement.stored_name
                ],
            ]
            if stored_name
        },
        Path(app.config["REPORT_FOLDER"]): {
            report.stored_name for report in GeneratedReport.query.all()
        },
        Path(app.config["SIGNATURE_FOLDER"]): {
            stored
            for stored in [
                *[worker.signature_stored_name for worker in Worker.query.all()],
                *[employer.signature_stored_name for employer in Employer.query.all()],
            ]
            if stored
        },
        Path(app.config["PAYMENT_FOLDER"]): {
            attachment.stored_name for attachment in PaymentAttachment.query.all()
        },
    }
    deleted = []
    skipped = []
    for folder, names in referenced.items():
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.iterdir():
            if not path.is_file() or path.name in names:
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(tzinfo=None)
            if modified > cutoff:
                skipped.append(str(path))
                continue
            if dry_run or safe_unlink(path):
                deleted.append(str(path))
    if not dry_run:
        db.session.add(
            AuditLog(
                action="orphan_cleanup",
                object_type="storage",
                details=(
                    f"deleted={len(deleted)} skipped_recent={len(skipped)} "
                    f"retention_hours={retention_hours}"
                ),
            )
        )
        db.session.commit()
    return {
        "deleted": deleted,
        "skipped_recent": skipped,
        "retention_hours": retention_hours,
    }
