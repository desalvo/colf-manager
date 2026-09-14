from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, text

from . import __build__, __version__
from .models import db

SCHEMA_VERSION = 1


def _encode(value):
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "value": str(value)}
    return value


def _decode(value):
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    kind = value["__type__"]
    raw = value["value"]
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "date":
        return date.fromisoformat(raw)
    if kind == "decimal":
        return Decimal(raw)
    return raw


def _json_default(value):
    encoded = _encode(value)
    if encoded is value:
        raise TypeError(f"Unsupported backup value: {type(value)!r}")
    return encoded


def _table_snapshot():
    tables = {}
    for table in db.metadata.sorted_tables:
        rows = db.session.execute(table.select()).mappings().all()
        tables[table.name] = [dict(row) for row in rows]
    return tables


def create_full_export(app):
    work = Path(tempfile.mkdtemp(prefix="colf-manager-export-"))
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = work / f"colf-manager-export-{timestamp}.zip"
    checksums = {}
    missing = []
    database = {
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "build": __build__,
        "created_at": datetime.now(UTC).isoformat(),
        "tables": _table_snapshot(),
    }
    database_bytes = json.dumps(
        database,
        ensure_ascii=False,
        indent=2,
        default=_json_default,
    ).encode()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("database.json", database_bytes)
        checksums["database.json"] = hashlib.sha256(database_bytes).hexdigest()
        for table_name, folder_key, prefix in (
            ("document", "UPLOAD_FOLDER", "files/documents"),
            ("generated_report", "REPORT_FOLDER", "files/reports"),
        ):
            folder = Path(app.config[folder_key])
            for row in database["tables"].get(table_name, []):
                stored_name = row.get("stored_name")
                if not stored_name:
                    continue
                path = folder / stored_name
                arcname = f"{prefix}/{stored_name}"
                if not path.is_file():
                    missing.append(arcname)
                    continue
                payload = path.read_bytes()
                zf.writestr(arcname, payload)
                checksums[arcname] = hashlib.sha256(payload).hexdigest()
        manifest = {
            "format": "colf-manager-full-export",
            "schema_version": SCHEMA_VERSION,
            "app_version": __version__,
            "build": __build__,
            "checksums": checksums,
            "missing_referenced_files": missing,
        }
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        )
    return archive


def _safe_members(zf):
    for member in zf.infolist():
        path = Path(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Archivio non valido: percorso non sicuro")
        yield member


def _reset_sequences():
    if db.engine.dialect.name != "postgresql":
        return
    sequence_query = text("SELECT pg_get_serial_sequence(:table_name, 'id')")
    setval_query = text("SELECT setval(CAST(:sequence_name AS regclass), :next_value, :is_called)")
    for table in db.metadata.sorted_tables:
        if "id" not in table.c or not table.c.id.primary_key:
            continue
        sequence_name = db.session.execute(
            sequence_query,
            {"table_name": table.name},
        ).scalar_one_or_none()
        if not sequence_name:
            continue
        max_id = db.session.execute(select(func.max(table.c.id))).scalar_one_or_none()
        db.session.execute(
            setval_query,
            {
                "sequence_name": sequence_name,
                "next_value": max_id if max_id is not None else 1,
                "is_called": max_id is not None,
            },
        )


def restore_full_export(app, fileobj):
    staging = Path(tempfile.mkdtemp(prefix="colf-manager-import-"))
    try:
        with zipfile.ZipFile(fileobj) as zf:
            members = list(_safe_members(zf))
            names = {member.filename for member in members}
            if "manifest.json" not in names or "database.json" not in names:
                raise ValueError("Archivio incompleto: manifest o database mancanti")
            manifest = json.loads(zf.read("manifest.json"))
            database_raw = zf.read("database.json")
            if manifest.get("format") != "colf-manager-full-export":
                raise ValueError("Formato di export non riconosciuto")
            if manifest.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("Versione formato export non supportata")
            for name, expected in manifest.get("checksums", {}).items():
                if name not in names:
                    raise ValueError(f"File mancante nell'archivio: {name}")
                actual = hashlib.sha256(zf.read(name)).hexdigest()
                if actual != expected:
                    raise ValueError(f"Checksum non valido: {name}")
            database = json.loads(database_raw, object_hook=_decode)
            zf.extractall(staging)

        table_by_name = {table.name: table for table in db.metadata.sorted_tables}
        incoming = database.get("tables", {})
        unknown = set(incoming) - set(table_by_name)
        if unknown:
            table_names = ", ".join(sorted(unknown))
            raise ValueError(f"Tabelle non supportate nell'archivio: {table_names}")

        try:
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            for table in db.metadata.sorted_tables:
                rows = incoming.get(table.name, [])
                if rows:
                    db.session.execute(table.insert(), rows)
            db.session.commit()
            _reset_sequences()
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        for folder_key, relative in (
            ("UPLOAD_FOLDER", Path("files/documents")),
            ("REPORT_FOLDER", Path("files/reports")),
        ):
            target = Path(app.config[folder_key])
            target.mkdir(parents=True, exist_ok=True)
            for old in target.iterdir():
                if old.is_file():
                    old.unlink(missing_ok=True)
            source = staging / relative
            if source.exists():
                for item in source.iterdir():
                    if item.is_file():
                        shutil.copy2(item, target / item.name)
        return {
            "tables": {name: len(rows) for name, rows in incoming.items()},
            "source_version": database.get("app_version"),
            "source_build": database.get("build"),
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)
