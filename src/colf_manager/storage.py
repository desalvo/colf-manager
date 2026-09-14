from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import AuditLog, Document, GeneratedReport, db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def safe_unlink(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


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
            document.stored_name for document in Document.query.all()
        },
        Path(app.config["REPORT_FOLDER"]): {
            report.stored_name for report in GeneratedReport.query.all()
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
