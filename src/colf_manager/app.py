# fmt: off
import hashlib
import os
import secrets
import zipfile
from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from io import BytesIO
from decimal import Decimal
from functools import wraps
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
from html import escape as html_escape

from flask import (
    Response,
    Flask,
    current_app,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image as PILImage, UnidentifiedImageError

from .calculations import (
    annual_summary,
    monthly_summary,
    tfr_year_summary,
    thirteenth_year_summary,
    combined_thirteenth_tfr_summary,
    inps_contribution_summary,
    estimated_irpef_summary,
    vacation_balance,
    vacation_hours_per_day,
    vacation_working_days,
)
from . import __author__, __build__, __version__
from .backup import create_full_export, restore_full_export
from .models import (
    Absence,
    AuditLog,
    Document,
    GeneratedReport,
    Expense,
    ExpenseRecoveryAllocation,
    ExpenseSettlement,
    Employer,
    HourlyRate,
    Location,
    Payment,
    PaymentAttachment,
    Setting,
    User,
    WorkEntry,
    Worker,
    db,
)
from .sickness_rules import sickness_metrics, sickness_rule, sickness_days_in_period
from .permit_rules import (
    PERMIT_CATEGORIES,
    permit_metrics,
    validate_paid_permit,
)
from .reporting import (
    annual_payroll_pdf,
    courtesy_cu_pdf,
    payroll_pdf,
    tfr_annual_pdf,
    trend_pdf,
    location_trend_pdf,
    thirteenth_payroll_pdf,
    combined_thirteenth_tfr_pdf,
)
from .storage import cleanup_orphan_files, safe_unlink, store_report
from .mailer import send_smtp_message
from .validation import (
    nonnegative_decimal,
    nonnegative_int,
    parse_date,
    parse_time,
    validate_password,
    validate_work_times,
)

ALLOWED_UPLOADS = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
    ".bmp": {"image/bmp"},
}


def _is_placeholder(value):
    lowered = (value or "").strip().lower().replace("-", "_")
    return not lowered or lowered.startswith(("change_me", "replace_with"))


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _setting(key, default=None):
    row = db.session.get(Setting, key)
    return row.value if row else default


def _save_setting(key, value):
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=str(value))
        db.session.add(row)
    else:
        row.value = str(value)


def _calendar_color(worker_id, employer_id, location_id):
    token = f"{worker_id}:{employer_id or 0}:{location_id or 0}".encode()
    hue = int(hashlib.sha256(token).hexdigest()[:6], 16) % 360
    return f"hsl({hue} 52% 39%)"


def _calendar_token_key(kind, object_id):
    if kind not in {"worker", "employer"}:
        raise ValueError("Tipo calendario non valido")
    return f"calendar_subscription_{kind}_{int(object_id)}"


def _calendar_escape(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _calendar_fold(line, limit=73):
    chunks = []
    current = line
    while len(current.encode("utf-8")) > limit:
        cut = min(len(current), limit)
        while len(current[:cut].encode("utf-8")) > limit and cut > 1:
            cut -= 1
        chunks.append(current[:cut])
        current = " " + current[cut:]
    chunks.append(current)
    return "\r\n".join(chunks)


def _external_base_url():
    configured = (_setting("external_url", "") or "").strip().rstrip("/")
    return configured or request.url_root.rstrip("/")


# Stable, application-specific PostgreSQL advisory lock key. The lock is
# session scoped and therefore also serializes bootstrap across replicas.
DATABASE_BOOTSTRAP_LOCK_ID = 1129270342


def _initialize_database(admin_password, testing):
    """Serialize schema/bootstrap work across Gunicorn workers."""
    lock_connection = None
    try:
        if db.engine.dialect.name == "postgresql":
            lock_connection = db.engine.connect()
            lock_connection.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": DATABASE_BOOTSTRAP_LOCK_ID},
            )

        db.metadata.create_all(bind=lock_connection or db.engine)
        # PostgreSQL DDL is transactional. When create_all() runs on the
        # dedicated advisory-lock connection, commit it before the legacy
        # compatibility checks and ORM queries use other pooled connections.
        # Session-level advisory locks survive COMMIT and continue to serialize
        # the entire bootstrap sequence until explicitly released below.
        if lock_connection is not None:
            lock_connection.commit()

        _ensure_legacy_schema_compatibility()

        if not User.query.first():
            password = (
                admin_password
                or current_app.config.get("TEST_ADMIN_PASSWORD")
                or secrets.token_urlsafe(24)
            )
            if not testing:
                validate_password(password)
            db.session.add(
                User(
                    username=os.getenv("COLF_MANAGER_ADMIN_USER", "admin"),
                    password_hash=generate_password_hash(password),
                    is_admin=True,
                    must_change_password=not testing,
                )
            )
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        db.session.remove()
        if lock_connection is not None:
            try:
                lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": DATABASE_BOOTSTRAP_LOCK_ID},
                )
            finally:
                lock_connection.close()


def _ensure_legacy_schema_compatibility():
    """Upgrade the original 1.0.0 schema enough to boot before Alembic takes over."""
    inspector = inspect(db.engine)
    if "user" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("user")}
        statements = []
        if "is_admin" not in columns:
            statements.append('ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE')
        if "must_change_password" not in columns:
            statements.append(
                'ALTER TABLE "user" ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT TRUE'
            )
        if "is_active" not in columns:
            statements.append('ALTER TABLE "user" ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE')
        if "created_at" not in columns:
            statements.append('ALTER TABLE "user" ADD COLUMN created_at TIMESTAMP')
        for statement in statements:
            db.session.execute(text(statement))
        if statements:
            db.session.commit()
            db.session.execute(text('UPDATE "user" SET is_admin=TRUE WHERE id=(SELECT MIN(id) FROM "user")'))
            db.session.commit()

    inspector = inspect(db.engine)
    if "document" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("document")}
        statements = []
        if "mime_type" not in columns:
            statements.append("ALTER TABLE document ADD COLUMN mime_type VARCHAR(120)")
        if "sha256" not in columns:
            statements.append("ALTER TABLE document ADD COLUMN sha256 VARCHAR(64)")
        if "size_bytes" not in columns:
            statements.append("ALTER TABLE document ADD COLUMN size_bytes INTEGER")
        for statement in statements:
            db.session.execute(text(statement))
        if statements:
            db.session.commit()

    inspector = inspect(db.engine)
    if "employer" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("employer")}
        statements = []
        additions = {
            "city": "VARCHAR(120)",
            "province": "VARCHAR(2)",
            "postal_code": "VARCHAR(10)",
            "signature_stored_name": "VARCHAR(255)",
            "signature_filename": "VARCHAR(255)",
            "signature_mime_type": "VARCHAR(120)",
        }
        for column, ddl in additions.items():
            if column not in columns:
                statements.append(f"ALTER TABLE employer ADD COLUMN {column} {ddl}")
        for statement in statements:
            db.session.execute(text(statement))
        if statements:
            db.session.commit()

    inspector = inspect(db.engine)
    if "worker" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("worker")}
        statements = []
        additions = {
            "employer_id": "INTEGER",
            "birth_date": "DATE",
            "address": "TEXT",
            "city": "VARCHAR(120)",
            "province": "VARCHAR(2)",
            "postal_code": "VARCHAR(10)",
            "phone": "VARCHAR(40)",
            "email": "VARCHAR(255)",
            "employment_end": "DATE",
            "vacation_advance_allowed": "BOOLEAN NOT NULL DEFAULT FALSE",
            "live_in": "BOOLEAN NOT NULL DEFAULT FALSE",
            "live_in_reduced_schedule": "BOOLEAN NOT NULL DEFAULT FALSE",
            "union_officer": "BOOLEAN NOT NULL DEFAULT FALSE",
            "contract_number": "VARCHAR(100)",
            "contract_type": "VARCHAR(20) NOT NULL DEFAULT 'permanent'",
            "employer_covers_all_taxes": "BOOLEAN NOT NULL DEFAULT FALSE",
            "signature_stored_name": "VARCHAR(255)",
            "signature_filename": "VARCHAR(255)",
            "signature_mime_type": "VARCHAR(120)",
            "notes": "TEXT",
        }
        for column, ddl in additions.items():
            if column not in columns:
                statements.append(f"ALTER TABLE worker ADD COLUMN {column} {ddl}")
        for statement in statements:
            db.session.execute(text(statement))
        if statements:
            db.session.commit()

    inspector = inspect(db.engine)
    if "work_entry" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("work_entry")}
        if "location_id" not in columns:
            db.session.execute(text("ALTER TABLE work_entry ADD COLUMN location_id INTEGER"))
            db.session.commit()
        try:
            db.session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_work_entry_location_id "
                    "ON work_entry(location_id)"
                )
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()

    inspector = inspect(db.engine)
    if "work_entry" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("work_entry")}
        if "entry_kind" not in columns:
            statements.append("ALTER TABLE work_entry ADD COLUMN entry_kind VARCHAR(20) NOT NULL DEFAULT 'ordinary'")
        if "paid" not in columns:
            statements.append("ALTER TABLE work_entry ADD COLUMN paid BOOLEAN NOT NULL DEFAULT TRUE")
        if "rate_override" not in columns:
            statements.append("ALTER TABLE work_entry ADD COLUMN rate_override NUMERIC(10,2)")

    if "absence" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("absence")}
        statements = []
        if "start_time" not in columns:
            statements.append("ALTER TABLE absence ADD COLUMN start_time TIME")
        if "end_time" not in columns:
            statements.append("ALTER TABLE absence ADD COLUMN end_time TIME")
        if "permit_category" not in columns:
            statements.append("ALTER TABLE absence ADD COLUMN permit_category VARCHAR(40)")
        if "paid_beyond_legal_limit" not in columns:
            statements.append("ALTER TABLE absence ADD COLUMN paid_beyond_legal_limit BOOLEAN NOT NULL DEFAULT FALSE")
        if "oncological" not in columns:
            statements.append("ALTER TABLE absence ADD COLUMN oncological BOOLEAN NOT NULL DEFAULT FALSE")
        for statement in statements:
            db.session.execute(text(statement))
        if statements:
            db.session.commit()

    try:
        db.session.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_hourly_rate_worker_valid_from "
                "ON hourly_rate(worker_id, valid_from)"
            )
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def create_app(test_config=None):
    testing = bool(test_config and test_config.get("TESTING"))
    production = _bool_env("COLF_MANAGER_PRODUCTION", not testing)
    secret = os.getenv("COLF_MANAGER_SECRET_KEY")
    admin_password = os.getenv("COLF_MANAGER_ADMIN_PASSWORD")
    if not testing and production:
        if _is_placeholder(secret) or len(secret) < 32:
            raise RuntimeError("COLF_MANAGER_SECRET_KEY must be a non-placeholder value of at least 32 characters")
        if _is_placeholder(admin_password):
            raise RuntimeError("COLF_MANAGER_ADMIN_PASSWORD must be set to a non-placeholder password")
        validate_password(admin_password)

    app = Flask(__name__)
    data_dir = Path(os.getenv("COLF_MANAGER_DATA", "/data" if production else "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    app.config.update(
        SECRET_KEY=secret or "test-only-secret-key-not-for-production",
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL", f"sqlite:///{data_dir / 'colf-manager.db'}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.getenv("COLF_MANAGER_MAX_BACKUP_BYTES", str(512 * 1024 * 1024))),
        DOCUMENT_MAX_BYTES=int(os.getenv("COLF_MANAGER_MAX_UPLOAD_BYTES", str(16 * 1024 * 1024))),
        UPLOAD_FOLDER=str(data_dir / "documents"),
        REPORT_FOLDER=str(data_dir / "reports"),
        SIGNATURE_FOLDER=str(data_dir / "signatures"),
        PAYMENT_FOLDER=str(data_dir / "payments"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_bool_env("COLF_MANAGER_SECURE_COOKIES", production),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=_bool_env("COLF_MANAGER_SECURE_COOKIES", production),
        PERMANENT_SESSION_LIFETIME=int(os.getenv("COLF_MANAGER_SESSION_MINUTES", "60")) * 60,
        WTF_CSRF_TIME_LIMIT=3600,
    )
    if test_config:
        app.config.update(test_config)
    if _bool_env("COLF_MANAGER_PROXY_FIX", production):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["REPORT_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["SIGNATURE_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PAYMENT_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    Migrate(app, db)
    CSRFProtect(app)
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=os.getenv("COLF_MANAGER_RATELIMIT_STORAGE", "memory://"),
    )
    limiter.init_app(app)

    login = LoginManager(app)
    login.login_view = "login"
    login.session_protection = "strong"

    @app.context_processor
    def application_metadata():
        return {
            "app_version": __version__,
            "app_build": __build__,
            "app_author": __author__,
        }

    @login.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    def _validated_upload(file_storage, *, images_only=False):
        if not file_storage or not file_storage.filename:
            raise ValueError("Selezionare un file")
        safe = secure_filename(file_storage.filename)
        suffix = Path(safe).suffix.lower()
        allowed = {k: v for k, v in ALLOWED_UPLOADS.items() if not images_only or k != ".pdf"}
        if suffix not in allowed:
            raise ValueError("Tipo file non consentito")
        payload = file_storage.read()
        if not payload:
            raise ValueError("Il file è vuoto")
        if len(payload) > app.config["DOCUMENT_MAX_BYTES"]:
            raise ValueError("Il file supera la dimensione massima consentita")
        mime = file_storage.mimetype or "application/octet-stream"
        if mime not in allowed[suffix]:
            raise ValueError("MIME type non consentito")
        if suffix == ".pdf":
            if not payload.startswith(b"%PDF-"):
                raise ValueError("Il contenuto del file non corrisponde all'estensione")
        else:
            try:
                image = PILImage.open(BytesIO(payload))
                image.verify()
            except (UnidentifiedImageError, OSError, ValueError) as exc:
                raise ValueError("Immagine non valida") from exc
        return safe, suffix, mime, payload

    def _update_signature(person, kind):
        remove = request.form.get("remove_signature") == "1"
        uploaded = request.files.get("signature")
        old_stored = getattr(person, "signature_stored_name", None)
        if remove:
            person.signature_stored_name = None
            person.signature_filename = None
            person.signature_mime_type = None
            if old_stored:
                safe_unlink(Path(app.config["SIGNATURE_FOLDER"]) / old_stored)
            return
        if not uploaded or not uploaded.filename:
            return
        safe, _, mime, payload = _validated_upload(uploaded, images_only=True)
        stored = f"{kind}-{uuid4().hex}-{safe}"
        (Path(app.config["SIGNATURE_FOLDER"]) / stored).write_bytes(payload)
        person.signature_stored_name = stored
        person.signature_filename = safe
        person.signature_mime_type = mime
        if old_stored and old_stored != stored:
            safe_unlink(Path(app.config["SIGNATURE_FOLDER"]) / old_stored)

    def _signature_path(person):
        stored = getattr(person, "signature_stored_name", None) if person else None
        if not stored:
            return None
        path = Path(app.config["SIGNATURE_FOLDER"]) / stored
        return str(path) if path.is_file() else None

    def audit(action, object_type=None, object_id=None, details=None, user_id=None):
        try:
            db.session.add(
                AuditLog(
                    user_id=user_id if user_id is not None else (current_user.id if current_user.is_authenticated else None),
                    action=action,
                    object_type=object_type,
                    object_id=str(object_id) if object_id is not None else None,
                    remote_addr=request.headers.get("X-Forwarded-For", request.remote_addr),
                    details=(details or "")[:500] or None,
                )
            )
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()

    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.is_admin:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    @app.before_request
    def force_password_change():
        if (
            current_user.is_authenticated
            and current_user.must_change_password
            and request.endpoint not in {"settings", "change_password", "logout", "static", "health"}
        ):
            return redirect(url_for("change_password"))
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; connect-src 'self'",
        )
        return response

    with app.app_context():
        _initialize_database(admin_password, testing)

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": __version__, "build": __build__}

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"])
    def login_view():
        if request.method == "POST":
            username = request.form.get("username", "")[:80]
            user = User.query.filter_by(username=username).first()
            if user and user.is_active and check_password_hash(
                user.password_hash, request.form.get("password", "")
            ):
                login_user(user)
                audit("login", "user", user.id, user_id=user.id)
                return redirect(url_for("settings" if user.must_change_password else "dashboard"))
            audit("login_failed", details=f"username={username}")
            flash("Credenziali non valide", "error")
        return render_template("login.html")

    app.add_url_rule("/login", "login", login_view, methods=["GET", "POST"])

    @app.post("/logout")
    @login_required
    def logout():
        user_id = current_user.id
        audit("logout", "user", user_id)
        logout_user()
        return redirect(url_for("login"))

    @app.route("/account/password", methods=["GET", "POST"])
    @login_required
    def change_password():
        if request.method == "POST":
            if not check_password_hash(current_user.password_hash, request.form.get("current_password", "")):
                flash("Password attuale non valida", "error")
                return render_template("change_password.html")
            new_password = request.form.get("new_password", "")
            if new_password != request.form.get("confirm_password", ""):
                flash("Le nuove password non coincidono", "error")
                return render_template("change_password.html")
            try:
                validate_password(new_password)
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("change_password.html")
            current_user.password_hash = generate_password_hash(new_password)
            current_user.must_change_password = False
            db.session.commit()
            audit("password_changed", "user", current_user.id)
            flash("Password aggiornata", "success")
            return redirect(url_for("dashboard"))
        return render_template("change_password.html")

    @app.route("/admin/users", methods=["GET", "POST"])
    @admin_required
    def users_admin():
        if request.method == "POST":
            try:
                username = request.form.get("username", "").strip()
                if len(username) < 3:
                    raise ValueError("Il nome utente deve contenere almeno 3 caratteri")
                password = request.form.get("password", "")
                validate_password(password)
                db.session.add(
                    User(
                        username=username,
                        password_hash=generate_password_hash(password),
                        is_admin="is_admin" in request.form,
                        must_change_password=True,
                    )
                )
                db.session.commit()
                audit("user_created", "user", username)
                flash("Utente creato", "success")
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                flash(str(exc) if isinstance(exc, ValueError) else "Nome utente già esistente", "error")
        return render_template("users.html", users=User.query.order_by(User.username).all())

    @app.get("/")
    @login_required
    def dashboard():
        today = date.today()
        year = request.args.get("year", today.year, type=int)
        month = request.args.get("month", today.month, type=int)
        if year < 1990 or year > 2200 or month not in range(1, 13):
            year, month = today.year, today.month
            flash("Periodo non valido: ripristinato il mese corrente", "error")
        workers = Worker.query.order_by(Worker.last_name).all()
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])
        stats = {
            "workers": len(workers),
            "hours": 0,
            "ordinary_hours": 0,
            "overtime_hours": 0,
            "unpaid_work_hours": 0,
            "pay": 0,
            "tfr": 0,
            "thirteenth_month": 0,
            "thirteenth_ytd": 0,
            "tfr_ytd": 0,
            "vacation_used_month": 0,
            "vacation_remaining_year": 0,
            "vacation_annual_limit": 0,
            "sickness_paid_month": 0,
            "sickness_unpaid_month": 0,
            "sickness_paid_year": 0,
            "sickness_unpaid_year": 0,
            "sickness_extra_paid_year": 0,
            "sickness_paid_limit": 0,
            "sickness_paid_remaining_year": 0,
            "sickness_job_protection_days": 0,
            "sickness_job_protection_used": 0,
            "sickness_job_protection_remaining": 0,
            "sickness_rule_known": True,
            "permit_categories": {},
        }
        for worker in workers:
            worker_obj, entries, absences_list, expenses_list, rates_list = _worker_data(worker.id)
            summary = monthly_summary(
                entries, absences_list, expenses_list, rates_list, year, month, _tfr_factor(), worker_obj
            )
            stats["hours"] += float(summary["worked_hours"])
            stats["ordinary_hours"] += float(summary["ordinary_hours"])
            stats["overtime_hours"] += float(summary["overtime_hours"])
            stats["unpaid_work_hours"] += float(summary["unpaid_work_hours"])
            stats["pay"] += float(summary["payable"])
            stats["tfr"] += float(summary["tfr_accrual"])
            stats["thirteenth_month"] += float(summary["thirteenth_accrual"])

            ytd_thirteenth = Decimal("0")
            ytd_tfr = Decimal("0")
            for ytd_month in range(1, month + 1):
                ytd_summary = monthly_summary(
                    entries,
                    absences_list,
                    expenses_list,
                    rates_list,
                    year,
                    ytd_month,
                    _tfr_factor(),
                    worker_obj,
                )
                ytd_thirteenth += Decimal(ytd_summary["thirteenth_accrual"])
                ytd_tfr += Decimal(ytd_summary["tfr_accrual"])
            stats["thirteenth_ytd"] += float(ytd_thirteenth)
            stats["tfr_ytd"] += float(ytd_tfr)

            for absence in absences_list:
                if absence.kind != "vacation":
                    continue
                overlap_start = max(absence.start_date, period_start)
                overlap_end = min(absence.end_date, period_end)
                if overlap_start <= overlap_end:
                    stats["vacation_used_month"] += float(
                        vacation_working_days(overlap_start, overlap_end)
                    )

            permit_cutoff = min(period_end, date.today()) if year == date.today().year and month == date.today().month else period_end
            for metric in permit_metrics(worker_obj, absences_list, year, permit_cutoff):
                bucket = stats["permit_categories"].setdefault(
                    metric["category"],
                    {
                        "label": metric["label"],
                        "basis": metric["basis"],
                        "unit": metric["unit"],
                        "paid_month": 0.0,
                        "paid_year": 0.0,
                        "unpaid_month": 0.0,
                        "unpaid_year": 0.0,
                        "extra_paid_month": 0.0,
                        "extra_paid_year": 0.0,
                        "accrued_to_date": 0.0,
                        "annual_total": 0.0,
                        "remaining": 0.0,
                        "non_numeric_entitlement": False,
                    },
                )
                bucket["paid_month"] += float(metric["paid_month"])
                bucket["paid_year"] += float(metric["paid_year"])
                bucket["unpaid_month"] += float(metric["unpaid_month"])
                bucket["unpaid_year"] += float(metric["unpaid_year"])
                bucket["extra_paid_month"] += float(metric.get("extra_paid_month", 0))
                bucket["extra_paid_year"] += float(metric.get("extra_paid_year", 0))
                if metric["accrued_to_date"] is None:
                    bucket["non_numeric_entitlement"] = True
                else:
                    bucket["accrued_to_date"] += float(metric["accrued_to_date"])
                if metric["annual_total"] is None:
                    bucket["non_numeric_entitlement"] = True
                else:
                    annual_value = metric["annual_total"]
                    if metric["unit"] == "days":
                        from .permit_rules import daily_hours
                        annual_value = annual_value * daily_hours(worker_obj)
                    bucket["annual_total"] += float(annual_value)
                if metric["remaining"] is not None:
                    bucket["remaining"] += float(metric["remaining"])

            balance = vacation_balance(
                worker_obj, absences_list, year, date(year, 12, 31)
            )
            stats["vacation_remaining_year"] += float(
                balance["projected"] - balance["used_scheduled"]
            )
            stats["vacation_annual_limit"] += float(balance["projected"])

            sickness = sickness_metrics(worker_obj, absences_list, year, period_end)
            stats["sickness_paid_month"] += float(sickness["paid_month"])
            stats["sickness_unpaid_month"] += float(sickness["total_month"] - sickness["paid_month"])
            stats["sickness_paid_year"] += float(sickness["paid_year"])
            stats["sickness_unpaid_year"] += float(sickness["total_year"] - sickness["paid_year"])
            stats["sickness_extra_paid_year"] += float(sickness["extra_paid_year"])
            if sickness["known"]:
                stats["sickness_paid_limit"] += float(sickness["paid_days_limit"])
                stats["sickness_paid_remaining_year"] += float(sickness["legal_paid_remaining"])
                stats["sickness_job_protection_days"] += float(sickness["job_protection_days"])
                stats["sickness_job_protection_used"] += float(sickness["job_protection_used_365"])
                stats["sickness_job_protection_remaining"] += float(sickness["job_protection_remaining_365"])
            else:
                stats["sickness_rule_known"] = False
        recent = (
            WorkEntry.query.filter(
                WorkEntry.work_date >= period_start,
                WorkEntry.work_date <= period_end,
            )
            .order_by(WorkEntry.work_date.desc(), WorkEntry.start_time.desc())
            .limit(8)
            .all()
        )
        return render_template(
            "dashboard.html",
            workers=workers,
            stats=stats,
            recent=recent,
            worker_map={worker.id: worker for worker in workers},
            today=today,
            selected_year=year,
            selected_month=month,
        )

    def _optional_date(value, label):
        return parse_date(value, label) if value else None

    def _worker_from_form(worker=None):
        worker = worker or Worker()
        worker.first_name = request.form["first_name"].strip()
        worker.last_name = request.form["last_name"].strip()
        if not worker.first_name or not worker.last_name:
            raise ValueError("Nome e cognome sono obbligatori")
        employer_id = request.form.get("employer_id", type=int)
        if employer_id and not db.session.get(Employer, employer_id):
            raise ValueError("Datore di lavoro non valido")
        worker.employer_id = employer_id
        worker.fiscal_code = (request.form.get("fiscal_code") or "").strip() or None
        worker.birth_date = _optional_date(request.form.get("birth_date"), "Data di nascita")
        worker.address = (request.form.get("address") or "").strip() or None
        worker.city = (request.form.get("city") or "").strip()[:120] or None
        worker.province = (request.form.get("province") or "").strip().upper()[:2] or None
        worker.postal_code = (request.form.get("postal_code") or "").strip()[:10] or None
        worker.phone = (request.form.get("phone") or "").strip()[:40] or None
        worker.email = (request.form.get("email") or "").strip()[:255] or None
        worker.inps_number = (request.form.get("inps_number") or "").strip() or None
        worker.contract_number = (request.form.get("contract_number") or "").strip() or None
        worker.contract_type = request.form.get("contract_type") if request.form.get("contract_type") in {"permanent", "fixed_term"} else "permanent"
        worker.employer_covers_all_taxes = "employer_covers_all_taxes" in request.form
        worker.employment_start = parse_date(request.form["employment_start"], "Data assunzione")
        worker.employment_end = _optional_date(request.form.get("employment_end"), "Data fine rapporto")
        if worker.employment_end and worker.employment_end < worker.employment_start:
            raise ValueError("La data di fine rapporto non può precedere l'assunzione")
        worker.weekly_hours = nonnegative_decimal(request.form.get("weekly_hours"), "Ore settimanali")
        worker.live_in = "live_in" in request.form
        worker.live_in_reduced_schedule = worker.live_in and "live_in_reduced_schedule" in request.form
        worker.union_officer = "union_officer" in request.form
        worker.vacation_advance_allowed = "vacation_advance_allowed" in request.form
        worker.notes = (request.form.get("notes") or "").strip() or None
        return worker

    @app.route("/workers", methods=["GET", "POST"])
    @login_required
    def workers():
        if request.method == "POST":
            try:
                w = _worker_from_form()
                _update_signature(w, "worker")
                db.session.add(w)
                db.session.flush()
                if request.form.get("hourly_rate"):
                    db.session.add(HourlyRate(worker_id=w.id, valid_from=w.employment_start, amount=nonnegative_decimal(request.form["hourly_rate"], "Tariffa")))
                db.session.commit()
                audit("worker_created", "worker", w.id)
                flash("Lavoratore registrato", "success")
                return redirect(url_for("worker_detail", worker_id=w.id))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                flash(str(exc) if isinstance(exc, ValueError) else "Dati duplicati o non validi", "error")
        return render_template("workers.html", workers=Worker.query.order_by(Worker.last_name).all(), employers=Employer.query.order_by(Employer.last_name).all())

    @app.get("/workers/<int:worker_id>")
    @login_required
    def worker_detail(worker_id):
        worker = db.get_or_404(Worker, worker_id)
        employer = db.session.get(Employer, worker.employer_id) if worker.employer_id else None
        rates = HourlyRate.query.filter_by(worker_id=worker.id).order_by(HourlyRate.valid_from.desc()).all()
        absences = Absence.query.filter_by(worker_id=worker.id).all()
        balances = {year: vacation_balance(worker, absences, year) for year in {date.today().year, worker.employment_start.year}}
        return render_template("worker_detail.html", worker=worker, employer=employer, rates=rates, balances=balances)

    @app.route("/workers/<int:worker_id>/edit", methods=["GET", "POST"])
    @login_required
    def worker_edit(worker_id):
        worker = db.get_or_404(Worker, worker_id)
        if request.method == "POST":
            try:
                _worker_from_form(worker)
                _update_signature(worker, "worker")
                db.session.commit()
                audit("worker_updated", "worker", worker.id)
                flash("Dati del lavoratore aggiornati", "success")
                return redirect(url_for("worker_detail", worker_id=worker.id))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                flash(str(exc) if isinstance(exc, ValueError) else "Dati non validi", "error")
        return render_template("worker_edit.html", worker=worker, employers=Employer.query.order_by(Employer.last_name).all())

    @app.get("/workers/<int:worker_id>/signature")
    @login_required
    def worker_signature(worker_id):
        worker = db.get_or_404(Worker, worker_id)
        if not worker.signature_stored_name:
            abort(404)
        return send_from_directory(
            app.config["SIGNATURE_FOLDER"],
            worker.signature_stored_name,
            as_attachment=False,
            download_name=worker.signature_filename or worker.signature_stored_name,
            mimetype=worker.signature_mime_type,
        )

    @app.post("/workers/<int:worker_id>/delete")
    @login_required
    def worker_delete(worker_id):
        worker = db.get_or_404(Worker, worker_id)
        if request.form.get("confirmation") != "DELETE":
            flash("Digitare DELETE per confermare la cancellazione totale", "error")
            return redirect(url_for("worker_detail", worker_id=worker.id))
        documents = Document.query.filter_by(worker_id=worker.id).all()
        reports = GeneratedReport.query.filter_by(worker_id=worker.id).all()
        expenses_to_delete = Expense.query.filter_by(worker_id=worker.id).all()
        settlement_files = [
            settlement.stored_name
            for expense in expenses_to_delete
            for settlement in expense.settlements
            if settlement.stored_name
        ]
        payments = Payment.query.filter_by(worker_id=worker.id).all()
        payment_ids = [payment.id for payment in payments]
        attachments = PaymentAttachment.query.filter(PaymentAttachment.payment_id.in_(payment_ids)).all() if payment_ids else []
        for document in documents:
            safe_unlink(Path(app.config["UPLOAD_FOLDER"]) / document.stored_name)
        for report in reports:
            safe_unlink(Path(app.config["REPORT_FOLDER"]) / report.stored_name)
        for stored_name in settlement_files:
            safe_unlink(Path(app.config["UPLOAD_FOLDER"]) / stored_name)
        for attachment in attachments:
            safe_unlink(Path(app.config["PAYMENT_FOLDER"]) / attachment.stored_name)
        if worker.signature_stored_name:
            safe_unlink(Path(app.config["SIGNATURE_FOLDER"]) / worker.signature_stored_name)
        if payment_ids:
            PaymentAttachment.query.filter(PaymentAttachment.payment_id.in_(payment_ids)).delete(synchronize_session=False)
        for model in (WorkEntry, Absence, Expense, Document, GeneratedReport, Payment, HourlyRate):
            model.query.filter_by(worker_id=worker.id).delete(synchronize_session=False)
        db.session.delete(worker)
        db.session.commit()
        audit("worker_deleted", "worker", worker_id)
        flash("Lavoratore e dati collegati eliminati definitivamente", "success")
        return redirect(url_for("workers"))

    def _employer_from_form(employer=None):
        employer = employer or Employer()
        employer.first_name = request.form["first_name"].strip()
        employer.last_name = request.form["last_name"].strip()
        if not employer.first_name or not employer.last_name:
            raise ValueError("Nome e cognome sono obbligatori")
        employer.fiscal_code = (request.form.get("fiscal_code") or "").strip() or None
        employer.birth_date = _optional_date(request.form.get("birth_date"), "Data di nascita")
        employer.address = (request.form.get("address") or "").strip() or None
        employer.city = (request.form.get("city") or "").strip()[:120] or None
        employer.province = (request.form.get("province") or "").strip().upper()[:2] or None
        employer.postal_code = (request.form.get("postal_code") or "").strip()[:10] or None
        employer.phone = (request.form.get("phone") or "").strip()[:40] or None
        employer.email = (request.form.get("email") or "").strip()[:255] or None
        employer.notes = (request.form.get("notes") or "").strip() or None
        return employer

    @app.route("/employers", methods=["GET", "POST"])
    @login_required
    def employers():
        if request.method == "POST":
            try:
                employer = _employer_from_form()
                _update_signature(employer, "employer")
                db.session.add(employer)
                db.session.commit()
                audit("employer_created", "employer", employer.id)
                flash("Datore di lavoro registrato", "success")
                return redirect(url_for("employer_detail", employer_id=employer.id))
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template("employers.html", employers=Employer.query.order_by(Employer.last_name).all())

    @app.get("/employers/<int:employer_id>")
    @login_required
    def employer_detail(employer_id):
        employer = db.get_or_404(Employer, employer_id)
        return render_template("employer_detail.html", employer=employer, workers=Worker.query.filter_by(employer_id=employer.id).order_by(Worker.last_name).all())

    @app.route("/employers/<int:employer_id>/edit", methods=["GET", "POST"])
    @login_required
    def employer_edit(employer_id):
        employer = db.get_or_404(Employer, employer_id)
        if request.method == "POST":
            try:
                _employer_from_form(employer)
                _update_signature(employer, "employer")
                db.session.commit()
                audit("employer_updated", "employer", employer.id)
                flash("Dati del datore di lavoro aggiornati", "success")
                return redirect(url_for("employer_detail", employer_id=employer.id))
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template("employer_edit.html", employer=employer)

    @app.get("/employers/<int:employer_id>/signature")
    @login_required
    def employer_signature(employer_id):
        employer = db.get_or_404(Employer, employer_id)
        if not employer.signature_stored_name:
            abort(404)
        return send_from_directory(
            app.config["SIGNATURE_FOLDER"],
            employer.signature_stored_name,
            as_attachment=False,
            download_name=employer.signature_filename or employer.signature_stored_name,
            mimetype=employer.signature_mime_type,
        )

    @app.post("/employers/<int:employer_id>/delete")
    @login_required
    def employer_delete(employer_id):
        employer = db.get_or_404(Employer, employer_id)
        if request.form.get("confirmation") != "DELETE":
            flash("Digitare DELETE per confermare la cancellazione totale", "error")
            return redirect(url_for("employer_detail", employer_id=employer.id))
        Worker.query.filter_by(employer_id=employer.id).update({"employer_id": None}, synchronize_session=False)
        Payment.query.filter_by(employer_id=employer.id).update({"employer_id": None}, synchronize_session=False)
        if employer.signature_stored_name:
            safe_unlink(Path(app.config["SIGNATURE_FOLDER"]) / employer.signature_stored_name)
        db.session.delete(employer)
        db.session.commit()
        audit("employer_deleted", "employer", employer_id)
        flash("Datore di lavoro eliminato definitivamente; i lavoratori restano archiviati e non associati", "success")
        return redirect(url_for("employers"))

    def _location_from_form(location=None):
        location = location or Location()
        location.name = (request.form.get("name") or "").strip()[:160]
        if not location.name:
            raise ValueError("Il nome del luogo è obbligatorio")
        location.address = (request.form.get("address") or "").strip() or None
        location.notes = (request.form.get("notes") or "").strip() or None
        return location

    @app.route("/locations", methods=["GET", "POST"])
    @login_required
    def locations():
        if request.method == "POST":
            try:
                location = _location_from_form()
                db.session.add(location)
                db.session.commit()
                audit("location_created", "location", location.id)
                flash("Luogo registrato", "success")
                return redirect(url_for("location_detail", location_id=location.id))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                message = str(exc) if isinstance(exc, ValueError) else "Esiste già un luogo con questo nome"
                flash(message, "error")
        return render_template(
            "locations.html",
            locations=Location.query.order_by(Location.name).all(),
        )

    @app.get("/locations/<int:location_id>")
    @login_required
    def location_detail(location_id):
        location = db.get_or_404(Location, location_id)
        entries = (
            WorkEntry.query.filter_by(location_id=location.id)
            .order_by(WorkEntry.work_date.desc(), WorkEntry.start_time.desc())
            .limit(25)
            .all()
        )
        return render_template(
            "location_detail.html",
            location=location,
            entries=entries,
            usage_count=WorkEntry.query.filter_by(location_id=location.id).count(),
        )

    @app.route("/locations/<int:location_id>/edit", methods=["GET", "POST"])
    @login_required
    def location_edit(location_id):
        location = db.get_or_404(Location, location_id)
        if request.method == "POST":
            try:
                _location_from_form(location)
                db.session.commit()
                audit("location_updated", "location", location.id)
                flash("Luogo aggiornato", "success")
                return redirect(url_for("location_detail", location_id=location.id))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                message = str(exc) if isinstance(exc, ValueError) else "Esiste già un luogo con questo nome"
                flash(message, "error")
        return render_template("location_edit.html", location=location)

    @app.post("/locations/<int:location_id>/delete")
    @login_required
    def location_delete(location_id):
        location = db.get_or_404(Location, location_id)
        if request.form.get("confirmation") != "DELETE":
            flash("Digitare DELETE per confermare la cancellazione", "error")
            return redirect(url_for("location_detail", location_id=location.id))
        WorkEntry.query.filter_by(location_id=location.id).update(
            {"location_id": None}, synchronize_session=False
        )
        db.session.delete(location)
        db.session.commit()
        audit("location_deleted", "location", location_id)
        flash(
            "Luogo eliminato. Le registrazioni storiche mantengono il nome del luogo usato.",
            "success",
        )
        return redirect(url_for("locations"))

    @app.route("/rates", methods=["GET", "POST"])
    @login_required
    def rates():
        if request.method == "POST":
            try:
                rate = HourlyRate(
                    worker_id=int(request.form["worker_id"]),
                    valid_from=parse_date(request.form["valid_from"], "Decorrenza"),
                    amount=nonnegative_decimal(request.form["amount"], "Tariffa"),
                    notes=request.form.get("notes") or None,
                )
                db.session.add(rate)
                db.session.commit()
                audit("rate_created", "hourly_rate", rate.id)
                flash("Tariffa registrata", "success")
                return redirect(url_for("rates"))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                message = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Esiste già una tariffa con questa decorrenza"
                )
                flash(message, "error")
                return redirect(url_for("rates"))
        return render_template(
            "rates.html",
            workers=Worker.query.order_by(Worker.last_name, Worker.first_name).all(),
            rates=HourlyRate.query.order_by(HourlyRate.valid_from.desc()).all(),
        )

    @app.route("/rates/<int:rate_id>/edit", methods=["GET", "POST"])
    @login_required
    def rate_edit(rate_id):
        rate = db.get_or_404(HourlyRate, rate_id)
        if request.method == "POST":
            try:
                rate.worker_id = int(request.form["worker_id"])
                rate.valid_from = parse_date(request.form["valid_from"], "Decorrenza")
                rate.amount = nonnegative_decimal(request.form["amount"], "Tariffa")
                rate.notes = request.form.get("notes") or None
                db.session.commit()
                audit("rate_updated", "hourly_rate", rate.id)
                flash("Tariffa aggiornata", "success")
                return redirect(url_for("rates"))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                flash(str(exc) if isinstance(exc, ValueError) else "Decorrenza già presente", "error")
        return render_template(
            "rate_edit.html",
            rate=rate,
            workers=Worker.query.order_by(Worker.last_name, Worker.first_name).all(),
        )

    @app.post("/rates/<int:rate_id>/delete")
    @login_required
    def rate_delete(rate_id):
        rate = db.get_or_404(HourlyRate, rate_id)
        db.session.delete(rate)
        db.session.commit()
        audit("rate_deleted", "hourly_rate", rate_id)
        flash("Tariffa eliminata", "success")
        return redirect(url_for("rates"))

    @app.route("/calendar")
    @login_required
    def calendar():
        workers = Worker.query.order_by(Worker.last_name, Worker.first_name).all()
        locations = Location.query.order_by(Location.name).all()
        try:
            recent_limit = max(1, min(50, int(_setting("calendar_recent_limit", "10"))))
        except ValueError:
            recent_limit = 10
        seen = set()
        recent_patterns = []
        candidates = []
        for entry in WorkEntry.query.order_by(WorkEntry.work_date.desc(), WorkEntry.start_time.desc()).limit(250).all():
            candidates.append((entry.work_date, entry.start_time, entry.entry_kind or "ordinary", entry))
        for absence in Absence.query.order_by(Absence.start_date.desc(), Absence.id.desc()).limit(250).all():
            candidates.append((absence.start_date, absence.start_time or time(9, 0), absence.kind, absence))
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        for _, _, kind, record in candidates:
            worker = db.session.get(Worker, record.worker_id)
            if not worker:
                continue
            employer = db.session.get(Employer, worker.employer_id) if worker.employer_id else None
            employer_name = f"{employer.first_name} {employer.last_name}" if employer else "Datore non associato"
            if kind in {"ordinary", "overtime"}:
                location_obj = db.session.get(Location, record.location_id) if record.location_id else None
                if location_obj is None:
                    continue
                key = (kind, record.worker_id, worker.employer_id, record.location_id, record.start_time, record.end_time, record.break_minutes, bool(record.paid), str(record.rate_override or ""))
                start_minutes = record.start_time.hour * 60 + record.start_time.minute
                end_minutes = record.end_time.hour * 60 + record.end_time.minute
                recent = {
                    "entry_kind": kind,
                    "kind_label": "Ore straordinarie" if kind == "overtime" else "Ore ordinarie",
                    "worker_id": worker.id,
                    "worker_name": f"{worker.first_name} {worker.last_name}",
                    "employer_name": employer_name,
                    "location_id": record.location_id,
                    "location_name": location_obj.name + (f" — {location_obj.address}" if location_obj.address else ""),
                    "start_time": record.start_time.strftime("%H:%M"),
                    "end_time": record.end_time.strftime("%H:%M"),
                    "duration_minutes": max(1, end_minutes - start_minutes),
                    "break_minutes": record.break_minutes,
                    "paid": bool(record.paid),
                    "paid_hours": "",
                    "rate_override": str(record.rate_override or ""),
                    "color": _calendar_color(worker.id, worker.employer_id, record.location_id),
                }
            else:
                start_clock = record.start_time or time(9, 0)
                end_clock = record.end_time or time(17, 0)
                key = (kind, record.worker_id, worker.employer_id, start_clock, end_clock, bool(record.paid), str(record.paid_hours or ""))
                start_minutes = start_clock.hour * 60 + start_clock.minute
                end_minutes = end_clock.hour * 60 + end_clock.minute
                recent = {
                    "entry_kind": kind,
                    "kind_label": "Ferie" if kind == "vacation" else "Malattia" if kind in {"health", "sickness"} else "Permesso",
                    "worker_id": worker.id,
                    "worker_name": f"{worker.first_name} {worker.last_name}",
                    "employer_name": employer_name,
                    "location_id": "",
                    "location_name": "—",
                    "start_time": start_clock.strftime("%H:%M"),
                    "end_time": end_clock.strftime("%H:%M"),
                    "duration_minutes": max(1, end_minutes - start_minutes),
                    "break_minutes": 0,
                    "paid": bool(record.paid),
                    "paid_hours": str(record.paid_hours or ""),
                    "permit_category": getattr(record, "permit_category", None) or "",
                    "color": "#d39a26" if kind == "vacation" else "#b84d55" if kind in {"health", "sickness"} else "#68777b",
                }
            if key in seen:
                continue
            seen.add(key)
            recent_patterns.append(recent)
            if len(recent_patterns) >= recent_limit:
                break
        recent_absences = []
        for absence in Absence.query.order_by(Absence.start_date.desc(), Absence.id.desc()).limit(12).all():
            worker = db.session.get(Worker, absence.worker_id)
            if not worker:
                continue
            recent_absences.append({
                "id": absence.id,
                "worker_id": absence.worker_id,
                "worker_name": f"{worker.first_name} {worker.last_name}",
                "kind": absence.kind,
                "kind_label": "Ferie" if absence.kind == "vacation" else "Malattia" if absence.kind in {"health", "sickness"} else "Permesso",
                "start_date": absence.start_date,
                "end_date": absence.end_date,
                "start_time": "" if absence.kind in {"vacation", "sickness", "health"} else (absence.start_time or time(9, 0)).strftime("%H:%M"),
                "end_time": "" if absence.kind in {"vacation", "sickness", "health"} else (absence.end_time or time(17, 0)).strftime("%H:%M"),
                "days": vacation_working_days(absence.start_date, absence.end_date) if absence.kind == "vacation" else ((absence.end_date - absence.start_date).days + 1 if absence.kind in {"sickness", "health"} else None),
                "paid": absence.paid,
                "paid_hours": "" if absence.kind in {"vacation", "sickness", "health"} else absence.paid_hours,
                "permit_category": absence.permit_category or "",
                "paid_beyond_legal_limit": bool(absence.paid_beyond_legal_limit),
                "oncological": bool(absence.oncological),
                "notes": absence.notes or "",
            })
        return render_template(
            "calendar.html",
            workers=workers,
            permit_categories=PERMIT_CATEGORIES,
            locations=locations,
            recent_patterns=recent_patterns,
            recent_limit=recent_limit,
            recent_absences=recent_absences,
        )

    @app.get("/api/events")
    @login_required
    def events():
        worker_id = request.args.get("worker_id", type=int)
        q = WorkEntry.query
        if worker_id:
            q = q.filter_by(worker_id=worker_id)
        result = []
        for entry in q.order_by(WorkEntry.work_date, WorkEntry.start_time).all():
            worker = db.session.get(Worker, entry.worker_id)
            employer = db.session.get(Employer, worker.employer_id) if worker and worker.employer_id else None
            color = _calendar_color(entry.worker_id, worker.employer_id if worker else None, entry.location_id)
            result.append({
                "id": f"work-{entry.id}",
                "title": f"{worker.first_name if worker else ''} · {entry.location}",
                "start": f"{entry.work_date}T{entry.start_time}",
                "end": f"{entry.work_date}T{entry.end_time}",
                "backgroundColor": color,
                "borderColor": color,
                "textColor": "#ffffff",
                "extendedProps": {
                    "type": "work",
                    "entry_kind": entry.entry_kind or "ordinary",
                    "kind_label": "Ore straordinarie" if entry.entry_kind == "overtime" else "Ore ordinarie",
                    "paid": bool(entry.paid),
                    "rate_override": str(entry.rate_override or ""),
                    "worker_id": entry.worker_id,
                    "worker": f"{worker.first_name} {worker.last_name}" if worker else "",
                    "employer": f"{employer.first_name} {employer.last_name}" if employer else "Datore non associato",
                    "location_id": entry.location_id,
                    "location": entry.location,
                    "break_minutes": entry.break_minutes,
                    "notes": entry.notes or "",
                },
            })
        aq = Absence.query
        if worker_id:
            aq = aq.filter_by(worker_id=worker_id)
        colors = {"vacation": "#d39a26", "health": "#b84d55", "sickness": "#b84d55", "permit": "#68777b", "unpaid_leave": "#68777b"}
        labels = {"vacation": "Ferie", "health": "Malattia", "sickness": "Malattia", "permit": "Permesso", "unpaid_leave": "Permesso"}
        for absence in aq.order_by(Absence.start_date).all():
            worker = db.session.get(Worker, absence.worker_id)
            employer = db.session.get(Employer, worker.employer_id) if worker and worker.employer_id else None
            common_props = {
                "type": "absence",
                "entry_kind": absence.kind,
                "absence_id": absence.id,
                "worker_id": absence.worker_id,
                "worker": f"{worker.first_name} {worker.last_name}" if worker else "",
                "employer": f"{employer.first_name} {employer.last_name}" if employer else "Datore non associato",
                "start_date": str(absence.start_date),
                "end_date": str(absence.end_date),
                "paid": bool(absence.paid),
                "paid_hours": "" if absence.kind in {"vacation", "sickness", "health"} else str(absence.paid_hours or 0),
                "permit_category": absence.permit_category or "",
                "paid_beyond_legal_limit": bool(absence.paid_beyond_legal_limit),
                "oncological": bool(absence.oncological),
                "notes": absence.notes or "",
                "kind_label": PERMIT_CATEGORIES.get(absence.permit_category, "Permesso") if absence.kind == "permit" else labels.get(absence.kind, "Assenza"),
            }
            if absence.kind == "vacation":
                result.append({
                    "id": f"absence-{absence.id}",
                    "title": "Ferie",
                    "start": str(absence.start_date),
                    "end": str(absence.end_date + timedelta(days=1)),
                    "allDay": True,
                    "backgroundColor": colors["vacation"],
                    "borderColor": colors["vacation"],
                    "textColor": "#ffffff",
                    "editable": False,
                    "extendedProps": {
                        **common_props,
                        "start_time": "",
                        "end_time": "",
                        "vacation_days": vacation_working_days(absence.start_date, absence.end_date),
                    },
                })
                continue
            if absence.kind in {"sickness", "health"}:
                result.append({
                    "id": f"absence-{absence.id}",
                    "title": "Malattia",
                    "start": str(absence.start_date),
                    "end": str(absence.end_date + timedelta(days=1)),
                    "allDay": True,
                    "backgroundColor": colors["sickness"],
                    "borderColor": colors["sickness"],
                    "textColor": "#ffffff",
                    "editable": False,
                    "extendedProps": {
                        **common_props,
                        "entry_kind": "sickness",
                        "start_time": "",
                        "end_time": "",
                        "sickness_days": (absence.end_date - absence.start_date).days + 1,
                    },
                })
                continue
            start_clock = absence.start_time or time(9, 0)
            end_clock = absence.end_time or time(17, 0)
            day = absence.start_date
            while day <= absence.end_date:
                result.append({
                    "id": f"absence-{absence.id}-{day.isoformat()}",
                    "title": labels.get(absence.kind, "Assenza"),
                    "start": f"{day}T{start_clock.strftime('%H:%M:%S')}",
                    "end": f"{day}T{end_clock.strftime('%H:%M:%S')}",
                    "backgroundColor": colors.get(absence.kind, "#68777b"),
                    "borderColor": colors.get(absence.kind, "#68777b"),
                    "textColor": "#ffffff",
                    "editable": False,
                    "extendedProps": {
                        **common_props,
                        "start_time": start_clock.strftime("%H:%M"),
                        "end_time": end_clock.strftime("%H:%M"),
                    },
                })
                day += timedelta(days=1)
        return jsonify(result)

    @app.post("/api/work")
    @login_required
    def add_work():
        try:
            payload = request.get_json(silent=True) if request.is_json else request.form
            if not payload:
                raise ValueError("Payload mancante")
            start_time = parse_time(payload["start_time"], "Inizio")
            end_time = parse_time(payload["end_time"], "Fine")
            break_minutes = nonnegative_int(payload.get("break_minutes", 0), "Pausa")
            validate_work_times(start_time, end_time, break_minutes)
            worker_id = int(payload["worker_id"])
            if db.session.get(Worker, worker_id) is None:
                raise ValueError("Lavoratore non valido")
            location = None
            location_id = payload.get("location_id")
            if location_id not in (None, ""):
                location = db.session.get(Location, int(location_id))
                if location is None:
                    raise ValueError("Luogo non valido")
                location_snapshot = location.name
                if location.address:
                    location_snapshot = f"{location.name} — {location.address}"
            else:
                location_snapshot = str(payload.get("location") or "").strip()[:255]
            if not location_snapshot:
                raise ValueError("Il luogo è obbligatorio")
            entry_kind = str(payload.get("entry_kind") or "ordinary")
            if entry_kind not in {"ordinary", "overtime"}:
                raise ValueError("Tipologia ore non valida")
            paid_raw = payload.get("paid", True)
            paid = paid_raw.lower() in {"1", "true", "on", "yes"} if isinstance(paid_raw, str) else bool(paid_raw)
            rate_override_raw = payload.get("rate_override")
            rate_override = None
            if entry_kind == "overtime" and rate_override_raw not in (None, ""):
                rate_override = nonnegative_decimal(rate_override_raw, "Tariffa straordinaria")
            entry = WorkEntry(
                worker_id=worker_id,
                location_id=location.id if location else None,
                work_date=parse_date(payload["work_date"], "Data"),
                start_time=start_time,
                end_time=end_time,
                break_minutes=break_minutes,
                entry_kind=entry_kind,
                paid=paid,
                rate_override=rate_override,
                location=location_snapshot[:255],
                notes=payload.get("notes") or None,
            )
            db.session.add(entry)
            db.session.commit()
            audit("work_created", "work_entry", entry.id)
            return jsonify({"id": entry.id}), 201
        except (ValueError, KeyError, TypeError) as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400

    @app.patch("/api/work/<int:entry_id>")
    @login_required
    def move_work(entry_id):
        entry = db.get_or_404(WorkEntry, entry_id)
        payload = request.get_json(silent=True) or {}
        try:
            work_date = parse_date(payload.get("work_date", str(entry.work_date)), "Data")
            start_time = parse_time(payload["start_time"], "Inizio") if payload.get("start_time") else entry.start_time
            end_time = parse_time(payload["end_time"], "Fine") if payload.get("end_time") else entry.end_time
            break_minutes = nonnegative_int(payload.get("break_minutes", entry.break_minutes), "Pausa")
            validate_work_times(start_time, end_time, break_minutes)
            worker_id = int(payload.get("worker_id", entry.worker_id))
            if db.session.get(Worker, worker_id) is None:
                raise ValueError("Lavoratore non valido")
            location_id = payload.get("location_id", entry.location_id)
            if location_id in (None, ""):
                location = None
                location_snapshot = str(payload.get("location") or entry.location).strip()
            else:
                location = db.session.get(Location, int(location_id))
                if location is None:
                    raise ValueError("Luogo non valido")
                location_snapshot = location.name + (f" — {location.address}" if location.address else "")
            entry.worker_id = worker_id
            entry.location_id = location.id if location else None
            entry.location = location_snapshot[:255]
            entry.work_date = work_date
            entry.start_time = start_time
            entry.end_time = end_time
            entry.break_minutes = break_minutes
            entry_kind = str(payload.get("entry_kind", entry.entry_kind or "ordinary"))
            if entry_kind not in {"ordinary", "overtime"}:
                raise ValueError("Tipologia ore non valida")
            entry.entry_kind = entry_kind
            if "paid" in payload:
                paid_raw = payload.get("paid")
                entry.paid = paid_raw.lower() in {"1", "true", "on", "yes"} if isinstance(paid_raw, str) else bool(paid_raw)
            if entry_kind == "overtime":
                rate_override_raw = payload.get("rate_override", entry.rate_override)
                entry.rate_override = (
                    None
                    if rate_override_raw in (None, "")
                    else nonnegative_decimal(rate_override_raw, "Tariffa straordinaria")
                )
            else:
                entry.rate_override = None
            if "notes" in payload:
                entry.notes = (payload.get("notes") or "").strip() or None
            db.session.commit()
            audit("work_updated", "work_entry", entry.id)
            return {"ok": True}
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/work/<int:entry_id>")
    @login_required
    def delete_work(entry_id):
        entry = db.get_or_404(WorkEntry, entry_id)
        db.session.delete(entry)
        db.session.commit()
        audit("work_deleted", "work_entry", entry_id)
        return {"ok": True}

    def _absence_values(payload, existing=None):
        worker_id = int(payload.get("worker_id", existing.worker_id if existing else 0))
        worker = db.session.get(Worker, worker_id)
        if worker is None:
            raise ValueError("Lavoratore non valido")
        kind = str(payload.get("kind", existing.kind if existing else "vacation"))
        if kind not in {"vacation", "health", "permit", "sickness", "unpaid_leave"}:
            raise ValueError("Tipo assenza non valido")
        start_date = parse_date(payload.get("start_date", str(existing.start_date) if existing else ""), "Data iniziale")
        end_date = parse_date(payload.get("end_date", str(existing.end_date) if existing else str(start_date)), "Data finale")
        if end_date < start_date:
            raise ValueError("La data finale deve essere successiva o uguale a quella iniziale")
        if kind in {"vacation", "health", "sickness"}:
            start_clock = None
            end_clock = None
            duration = Decimal((end_date - start_date).days + 1)
        else:
            start_clock = parse_time(payload.get("start_time", existing.start_time.strftime("%H:%M") if existing and existing.start_time else "09:00"), "Inizio")
            end_clock = parse_time(payload.get("end_time", existing.end_time.strftime("%H:%M") if existing and existing.end_time else "17:00"), "Fine")
            validate_work_times(start_clock, end_clock, 0)
            duration = Decimal(str((datetime.combine(start_date, end_clock) - datetime.combine(start_date, start_clock)).total_seconds() / 3600))
        paid_raw = payload.get("paid")
        if isinstance(paid_raw, str):
            paid = paid_raw.lower() in {"1", "true", "on", "yes"}
        elif paid_raw is None and existing is not None:
            paid = bool(existing.paid)
        elif paid_raw is None:
            paid = True
        else:
            paid = bool(paid_raw)
        if kind == "health":
            kind = "sickness"
        elif kind == "unpaid_leave":
            kind = "permit"
        if kind == "vacation":
            paid = True
        permit_category = None
        if kind == "permit":
            permit_category = str(payload.get("permit_category", getattr(existing, "permit_category", None) or ("medical" if paid else "other")))
            if permit_category not in PERMIT_CATEGORIES:
                raise ValueError("Categoria permesso non valida")
            if paid and permit_category == "other":
                raise ValueError("La categoria Altro è disponibile solo per permessi non retribuiti")
        paid_hours_raw = payload.get("paid_hours")
        if not paid:
            paid_hours = Decimal("0")
        elif kind == "vacation":
            paid_hours = vacation_hours_per_day(worker) * Decimal(
                vacation_working_days(start_date, end_date)
            )
        elif kind == "sickness":
            # Malattia is always day-based. Legacy clients may still send
            # start_time/end_time or paid_hours; those values are deliberately
            # ignored. Equivalent payroll hours are derived internally from the
            # worker schedule and never change the number of sickness days.
            paid_hours = vacation_hours_per_day(worker) * duration
        elif paid_hours_raw not in (None, ""):
            paid_hours = nonnegative_decimal(paid_hours_raw, "Ore pagate")
        else:
            paid_hours = duration * Decimal((end_date - start_date).days + 1)
        override_raw = payload.get("paid_beyond_legal_limit")
        paid_beyond_legal_limit = str(override_raw).lower() in {"1", "true", "on", "yes"} if override_raw is not None else bool(getattr(existing, "paid_beyond_legal_limit", False))
        oncological_raw = payload.get("oncological")
        oncological = str(oncological_raw).lower() in {"1", "true", "on", "yes"} if oncological_raw is not None else bool(getattr(existing, "oncological", False))
        return worker, {
            "worker_id": worker.id,
            "start_date": start_date,
            "end_date": end_date,
            "start_time": start_clock,
            "end_time": end_clock,
            "kind": kind,
            "paid": paid,
            "paid_hours": paid_hours,
            "permit_category": permit_category,
            "paid_beyond_legal_limit": paid_beyond_legal_limit,
            "oncological": oncological if kind == "sickness" else False,
            "notes": (payload.get("notes") if "notes" in payload else existing.notes if existing else None) or None,
        }

    def _validate_vacation_balance(worker, absence, replacing=None):
        if absence.kind != "vacation":
            return
        existing = Absence.query.filter_by(worker_id=worker.id).all()
        if replacing is not None:
            existing = [item for item in existing if item.id != replacing.id]
        for year in range(absence.start_date.year, absence.end_date.year + 1):
            balance = vacation_balance(
                worker,
                existing + [absence],
                year,
                min(absence.end_date, date(year, 12, 31)),
            )
            if balance["available_usable"] < 0:
                raise ValueError(
                    f"Ferie insufficienti per {year}: abilita la fruizione anticipata delle ferie da maturare oppure riduci il periodo"
                )

    def _validate_permit_balance(worker, absence, replacing=None):
        existing = Absence.query.filter_by(worker_id=worker.id).all()
        validate_paid_permit(worker, existing, absence, replacing=replacing)

    def _validate_sickness_balance(worker, absence, replacing=None):
        if absence.kind != "sickness" or not absence.paid or absence.paid_beyond_legal_limit:
            return
        existing = Absence.query.filter_by(worker_id=worker.id).all()
        if replacing is not None:
            existing = [item for item in existing if item.id != replacing.id]
        for year in range(absence.start_date.year, absence.end_date.year + 1):
            year_start, year_end = date(year, 1, 1), date(year, 12, 31)
            used = sum((sickness_days_in_period(a, year_start, year_end) for a in existing if a.kind in {"sickness", "health"} and a.paid), Decimal("0"))
            requested = sickness_days_in_period(absence, year_start, year_end)
            if requested <= 0:
                continue
            rule = sickness_rule(worker, max(absence.start_date, year_start), absence.oncological)
            if rule.get("known") and used + requested > rule["paid_days_limit"]:
                raise ValueError(f"Limite contrattuale di malattia retribuita superato ({rule['paid_days_limit']} giorni). Abilita il trattamento di miglior favore del datore per retribuire l'eccedenza.")

    @app.post("/api/absence")
    @login_required
    def add_absence():
        try:
            payload = request.get_json(silent=True) if request.is_json else request.form
            if not payload:
                raise ValueError("Payload mancante")
            worker, values = _absence_values(payload)
            absence = Absence(**values)
            if absence.kind == "vacation":
                _validate_vacation_balance(worker, absence)
            elif absence.kind == "permit":
                _validate_permit_balance(worker, absence)
            elif absence.kind == "sickness":
                _validate_sickness_balance(worker, absence)
            db.session.add(absence)
            db.session.commit()
            audit("absence_created", "absence", absence.id)
            return jsonify({"id": absence.id}), 201
        except (ValueError, KeyError, TypeError) as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/absence/<int:absence_id>")
    @login_required
    def get_absence(absence_id):
        absence = db.get_or_404(Absence, absence_id)
        worker = db.session.get(Worker, absence.worker_id)
        employer = db.session.get(Employer, worker.employer_id) if worker and worker.employer_id else None
        return jsonify({
            "id": absence.id,
            "kind": absence.kind,
            "worker_id": absence.worker_id,
            "worker": f"{worker.first_name} {worker.last_name}" if worker else "",
            "employer": f"{employer.first_name} {employer.last_name}" if employer else "Datore non associato",
            "start_date": str(absence.start_date),
            "end_date": str(absence.end_date),
            "start_time": "" if absence.kind in {"vacation", "sickness", "health"} else (absence.start_time or time(9, 0)).strftime("%H:%M"),
            "end_time": "" if absence.kind in {"vacation", "sickness", "health"} else (absence.end_time or time(17, 0)).strftime("%H:%M"),
            "paid": bool(absence.paid),
            "paid_hours": "" if absence.kind in {"vacation", "sickness", "health"} else str(absence.paid_hours or 0),
            "permit_category": absence.permit_category or "",
            "paid_beyond_legal_limit": bool(absence.paid_beyond_legal_limit),
            "oncological": bool(absence.oncological),
            "notes": absence.notes or "",
        })

    @app.patch("/api/absence/<int:absence_id>")
    @login_required
    def update_absence(absence_id):
        absence = db.get_or_404(Absence, absence_id)
        payload = request.get_json(silent=True) or {}
        try:
            worker, values = _absence_values(payload, absence)
            candidate = Absence(**values)
            if candidate.kind == "vacation":
                _validate_vacation_balance(worker, candidate, replacing=absence)
            elif candidate.kind == "permit":
                _validate_permit_balance(worker, candidate, replacing=absence)
            elif candidate.kind == "sickness":
                _validate_sickness_balance(worker, candidate, replacing=absence)
            for key, value in values.items():
                setattr(absence, key, value)
            db.session.commit()
            audit("absence_updated", "absence", absence.id)
            return {"ok": True}
        except (ValueError, KeyError, TypeError) as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400

    @app.delete("/api/absence/<int:absence_id>")
    @login_required
    def delete_absence(absence_id):
        absence = db.get_or_404(Absence, absence_id)
        db.session.delete(absence)
        db.session.commit()
        audit("absence_deleted", "absence", absence_id)
        return {"ok": True}

    @app.post("/absences")
    @login_required
    def absences():
        try:
            payload = dict(request.form)
            payload.setdefault("start_time", "09:00")
            payload.setdefault("end_time", "17:00")
            worker, values = _absence_values(payload)
            absence = Absence(**values)
            if absence.kind == "vacation":
                _validate_vacation_balance(worker, absence)
            elif absence.kind == "permit":
                _validate_permit_balance(worker, absence)
            elif absence.kind == "sickness":
                _validate_sickness_balance(worker, absence)
            db.session.add(absence)
            db.session.commit()
            audit("absence_created", "absence", absence.id)
            flash("Assenza registrata", "success")
        except (ValueError, KeyError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), "error")
        return redirect(url_for("calendar"))

    def _month_start(value):
        if isinstance(value, date):
            return date(value.year, value.month, 1)
        try:
            year_text, month_text = (value or "").split("-", 1)
            year, month = int(year_text), int(month_text)
            if month < 1 or month > 12:
                raise ValueError
            return date(year, month, 1)
        except (TypeError, ValueError):
            raise ValueError("Mese non valido; usare YYYY-MM") from None

    def _add_months(value, months):
        index = value.year * 12 + value.month - 1 + months
        return date(index // 12, index % 12 + 1, 1)

    def _expense_balance(expense):
        amount = Decimal(expense.amount)
        settlements = list(getattr(expense, "settlements", []) or [])
        allocations = list(getattr(expense, "recovery_allocations", []) or [])
        if expense.reimbursed and not settlements and not allocations:
            settled = amount
            payroll_allocated = Decimal("0")
            residual = Decimal("0")
            status = "Regolata (storico)"
        else:
            settled = sum((Decimal(item.amount) for item in settlements), Decimal("0"))
            payroll_allocated = sum(
                (Decimal(item.amount) for item in allocations if item.locked_at), Decimal("0")
            )
            residual = max(Decimal("0"), amount - settled - payroll_allocated)
            if residual == 0 and settled and payroll_allocated:
                status = "Regolazione mista"
            elif residual == 0 and payroll_allocated:
                status = "Regolata tramite cedolino"
            elif residual == 0:
                status = "Compensata manualmente"
            elif allocations and any(not item.locked_at for item in allocations):
                status = "Rateizzata / riportata"
            elif settled:
                status = "Parzialmente compensata"
            else:
                status = "Da regolare"
        planned = min(
            residual,
            sum(
                (Decimal(item.amount) for item in allocations if not item.locked_at),
                Decimal("0"),
            ),
        )
        return (
            settled.quantize(Decimal("0.01")),
            payroll_allocated.quantize(Decimal("0.01")),
            planned.quantize(Decimal("0.01")),
            residual.quantize(Decimal("0.01")),
            status,
        )

    def _decorate_expense(expense):
        settled, payroll_allocated, planned, residual, status = _expense_balance(expense)
        expense.manual_settled = settled
        expense.payroll_allocated = payroll_allocated
        expense.planned_recovery = planned
        expense.residual_amount = residual
        expense.balance_status = status
        return expense

    def _expense_relevant_to_period(expense, period_start, period_end):
        if period_start <= expense.expense_date <= period_end:
            return True
        if any(
            period_start <= item.due_month <= period_end
            for item in getattr(expense, "recovery_allocations", [])
        ):
            return True
        return any(
            period_start <= item.settlement_date <= period_end
            for item in getattr(expense, "settlements", [])
        )

    @app.route("/expenses", methods=["GET", "POST"])
    @login_required
    def expenses():
        if request.method == "POST":
            try:
                direction = request.form["direction"]
                if direction not in {"employer_advance", "worker_advance"}:
                    raise ValueError("Direzione non valida")
                description = request.form["description"].strip()[:255]
                if not description:
                    raise ValueError("Descrizione obbligatoria")
                expense = Expense(
                    worker_id=int(request.form["worker_id"]),
                    expense_date=parse_date(request.form["expense_date"], "Data"),
                    description=description,
                    amount=nonnegative_decimal(request.form["amount"], "Importo"),
                    direction=direction,
                    reimbursed=False,
                )
                db.session.add(expense)
                db.session.commit()
                audit("expense_created", "expense", expense.id)
                flash("Spesa registrata", "success")
                return redirect(url_for("expenses"))
            except (ValueError, KeyError, TypeError) as exc:
                db.session.rollback()
                flash(str(exc), "error")
        expense_rows = [
            _decorate_expense(item)
            for item in Expense.query.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()
        ]
        return render_template(
            "expenses.html",
            workers=Worker.query.order_by(Worker.last_name, Worker.first_name).all(),
            expenses=expense_rows,
        )

    @app.get("/expenses/<int:expense_id>")
    @login_required
    def expense_detail(expense_id):
        expense = _decorate_expense(db.get_or_404(Expense, expense_id))
        worker = db.session.get(Worker, expense.worker_id)
        return render_template("expense_detail.html", expense=expense, worker=worker)

    @app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
    @login_required
    def expense_edit(expense_id):
        expense = db.get_or_404(Expense, expense_id)
        if request.method == "POST":
            try:
                direction = request.form["direction"]
                if direction not in {"employer_advance", "worker_advance"}:
                    raise ValueError("Direzione non valida")
                new_amount = nonnegative_decimal(request.form["amount"], "Importo")
                settled = sum((Decimal(item.amount) for item in expense.settlements), Decimal("0"))
                locked = sum(
                    (Decimal(item.amount) for item in expense.recovery_allocations if item.locked_at),
                    Decimal("0"),
                )
                if new_amount < settled + locked:
                    raise ValueError(
                        "L'importo non può essere inferiore alle compensazioni e quote cedolino già registrate"
                    )
                description = request.form["description"].strip()[:255]
                if not description:
                    raise ValueError("Descrizione obbligatoria")
                new_worker_id = int(request.form["worker_id"])
                new_expense_date = parse_date(request.form["expense_date"], "Data")
                if (expense.settlements or expense.recovery_allocations) and new_worker_id != expense.worker_id:
                    raise ValueError("Non è possibile cambiare lavoratore dopo compensazioni o pianificazioni")
                if (expense.settlements or expense.recovery_allocations) and direction != expense.direction:
                    raise ValueError("Non è possibile cambiare direzione dopo compensazioni o pianificazioni")
                if any(item.settlement_date < new_expense_date for item in expense.settlements):
                    raise ValueError("La nuova data renderebbe non valide le compensazioni già registrate")
                new_month_start = date(new_expense_date.year, new_expense_date.month, 1)
                if any(item.due_month < new_month_start for item in expense.recovery_allocations):
                    raise ValueError("La nuova data renderebbe non valido il piano di recupero")
                expense.worker_id = new_worker_id
                expense.expense_date = new_expense_date
                expense.description = description
                expense.amount = new_amount
                expense.direction = direction
                db.session.commit()
                audit("expense_updated", "expense", expense.id)
                flash("Spesa aggiornata", "success")
                return redirect(url_for("expense_detail", expense_id=expense.id))
            except (ValueError, KeyError, TypeError) as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template(
            "expense_edit.html",
            expense=_decorate_expense(expense),
            workers=Worker.query.order_by(Worker.last_name, Worker.first_name).all(),
        )

    @app.post("/expenses/<int:expense_id>/recovery-plan")
    @login_required
    def expense_recovery_plan(expense_id):
        expense = db.get_or_404(Expense, expense_id)
        try:
            mode = (request.form.get("mode") or "current_month").strip()
            if mode not in {"current_month", "carry_forward", "installments"}:
                raise ValueError("Modalità di recupero non valida")
            locked_allocations = [
                item for item in expense.recovery_allocations if item.locked_at
            ]
            latest_locked = max(
                (item.due_month for item in locked_allocations), default=None
            )
            locked_total = sum(
                (Decimal(item.amount) for item in locked_allocations), Decimal("0")
            )
            expense_month_start = date(expense.expense_date.year, expense.expense_date.month, 1)
            already_archived = GeneratedReport.query.filter(
                GeneratedReport.worker_id == expense.worker_id,
                GeneratedReport.report_type == "monthly_payroll",
                GeneratedReport.period_start <= expense_month_start,
                GeneratedReport.period_end >= expense_month_start,
            ).first()
            if already_archived and not expense.recovery_allocations:
                raise ValueError(
                    "Il cedolino del mese originario è già stato generato; il residuo non può essere ripianificato"
                )
            manual = sum((Decimal(item.amount) for item in expense.settlements), Decimal("0"))
            residual = max(
                Decimal("0"), Decimal(expense.amount) - manual - locked_total
            )
            if residual <= 0:
                raise ValueError("La partita non ha residuo da pianificare")
            if locked_allocations and mode == "current_month":
                raise ValueError(
                    "Esistono quote già consolidate: il residuo può solo essere riportato o rateizzato nei mesi successivi"
                )

            for allocation in list(expense.recovery_allocations):
                if not allocation.locked_at:
                    db.session.delete(allocation)
            db.session.flush()

            if mode != "current_month":
                due_month = _month_start(request.form.get("start_month"))
                minimum_month = (
                    _add_months(latest_locked, 1)
                    if latest_locked
                    else _add_months(expense_month_start, 1)
                )
                if due_month < minimum_month:
                    raise ValueError(
                        f"Il piano deve iniziare da {minimum_month.strftime('%m/%Y')} o dopo"
                    )
                amounts = []
                if mode == "carry_forward":
                    amounts = [residual]
                else:
                    raw_installment = (request.form.get("installment_amount") or "").strip()
                    raw_count = (request.form.get("installment_count") or "").strip()
                    if raw_installment:
                        installment = nonnegative_decimal(raw_installment, "Importo rata")
                        if installment <= 0:
                            raise ValueError("L'importo rata deve essere maggiore di zero")
                        remaining = residual
                        while remaining > 0:
                            if len(amounts) >= 120:
                                raise ValueError("Il piano non può superare 120 rate")
                            quota = min(installment, remaining)
                            amounts.append(quota.quantize(Decimal("0.01")))
                            remaining -= quota
                    else:
                        try:
                            count = int(raw_count)
                        except (TypeError, ValueError):
                            raise ValueError(
                                "Indicare il numero di rate oppure l'importo della rata"
                            ) from None
                        if count < 1 or count > 120:
                            raise ValueError("Il numero di rate deve essere compreso tra 1 e 120")
                        base = (residual / Decimal(count)).quantize(Decimal("0.01"))
                        remaining = residual
                        for index in range(count):
                            quota = remaining if index == count - 1 else min(base, remaining)
                            amounts.append(quota.quantize(Decimal("0.01")))
                            remaining -= quota
                for index, quota in enumerate(amounts):
                    if quota <= 0:
                        continue
                    db.session.add(
                        ExpenseRecoveryAllocation(
                            expense_id=expense.id,
                            due_month=_add_months(due_month, index),
                            amount=quota,
                        )
                    )
            db.session.commit()
            audit(
                "expense_recovery_plan_updated",
                "expense",
                expense.id,
                f"mode={mode}",
            )
            flash("Piano di recupero aggiornato", "success")
        except (ValueError, KeyError, TypeError, IntegrityError) as exc:
            db.session.rollback()
            flash(str(exc) if isinstance(exc, ValueError) else "Piano non valido", "error")
        return redirect(url_for("expense_detail", expense_id=expense.id))

    @app.post("/expenses/<int:expense_id>/settlements")
    @login_required
    def expense_settlement_create(expense_id):
        expense = db.get_or_404(Expense, expense_id)
        stored_path = None
        try:
            amount = nonnegative_decimal(request.form.get("amount"), "Importo")
            if amount <= 0:
                raise ValueError("L'importo della compensazione deve essere maggiore di zero")
            method = (request.form.get("method") or "cash").strip()
            if method not in {"cash", "bank_transfer", "card", "electronic", "other"}:
                raise ValueError("Modalità di compensazione non valida")
            already = sum((Decimal(item.amount) for item in expense.settlements), Decimal("0"))
            locked = sum(
                (Decimal(item.amount) for item in expense.recovery_allocations if item.locked_at),
                Decimal("0"),
            )
            if expense.reimbursed and not expense.settlements and not expense.recovery_allocations:
                raise ValueError("La spesa risulta già regolata nello storico")
            if already + locked + amount > Decimal(expense.amount):
                raise ValueError("La compensazione supera il saldo ancora disponibile della spesa")
            settlement_date = parse_date(request.form.get("settlement_date"), "Data compensazione")
            expense_month_end = date(
                expense.expense_date.year,
                expense.expense_date.month,
                monthrange(expense.expense_date.year, expense.expense_date.month)[1],
            )
            if settlement_date < expense.expense_date:
                raise ValueError("La compensazione non può precedere la spesa")
            if settlement_date > expense_month_end and not expense.recovery_allocations:
                raise ValueError(
                    "Per compensare nei mesi successivi occorre prima riportare o rateizzare il residuo"
                )
            latest_locked = max(
                (item.due_month for item in expense.recovery_allocations if item.locked_at),
                default=None,
            )
            if latest_locked and _month_start(settlement_date) <= latest_locked:
                raise ValueError(
                    "La compensazione non può modificare un mese già consolidato nel cedolino"
                )
            settlement = ExpenseSettlement(
                expense_id=expense.id,
                settlement_date=settlement_date,
                amount=amount,
                method=method,
                notes=(request.form.get("notes") or "").strip() or None,
                created_by_user_id=current_user.id,
            )
            uploaded = request.files.get("file")
            if uploaded and uploaded.filename:
                safe, suffix, mime, payload = _validated_upload(uploaded)
                stored = f"expense-settlement-{uuid4().hex}{suffix}"
                stored_path = Path(app.config["UPLOAD_FOLDER"]) / stored
                stored_path.write_bytes(payload)
                settlement.filename = safe
                settlement.stored_name = stored
                settlement.mime_type = mime
                settlement.sha256 = hashlib.sha256(payload).hexdigest()
                settlement.size_bytes = len(payload)
            db.session.add(settlement)
            db.session.commit()
            audit(
                "expense_settlement_created",
                "expense_settlement",
                settlement.id,
                f"expense={expense.id}; amount={amount}; method={method}",
            )
            flash("Compensazione registrata", "success")
        except (ValueError, OSError, KeyError, TypeError) as exc:
            db.session.rollback()
            if stored_path:
                safe_unlink(stored_path)
            flash(str(exc), "error")
        return redirect(url_for("expense_detail", expense_id=expense.id))

    @app.route("/expenses/<int:expense_id>/settlements/<int:settlement_id>/edit", methods=["GET", "POST"])
    @login_required
    def expense_settlement_edit(expense_id, settlement_id):
        expense = db.get_or_404(Expense, expense_id)
        settlement = db.get_or_404(ExpenseSettlement, settlement_id)
        if settlement.expense_id != expense.id:
            abort(404)
        if request.method == "POST":
            try:
                amount = nonnegative_decimal(request.form.get("amount"), "Importo")
                if amount <= 0:
                    raise ValueError("L'importo della compensazione deve essere maggiore di zero")
                other = sum(
                    (Decimal(item.amount) for item in expense.settlements if item.id != settlement.id),
                    Decimal("0"),
                )
                locked = sum(
                    (Decimal(item.amount) for item in expense.recovery_allocations if item.locked_at),
                    Decimal("0"),
                )
                if other + locked + amount > Decimal(expense.amount):
                    raise ValueError("La compensazione supera il saldo ancora disponibile della spesa")
                method = (request.form.get("method") or "cash").strip()
                if method not in {"cash", "bank_transfer", "card", "electronic", "other"}:
                    raise ValueError("Modalità di compensazione non valida")
                settlement_date = parse_date(request.form.get("settlement_date"), "Data compensazione")
                expense_month_end = date(
                    expense.expense_date.year,
                    expense.expense_date.month,
                    monthrange(expense.expense_date.year, expense.expense_date.month)[1],
                )
                if settlement_date < expense.expense_date:
                    raise ValueError("La compensazione non può precedere la spesa")
                if settlement_date > expense_month_end and not expense.recovery_allocations:
                    raise ValueError(
                        "Per compensare nei mesi successivi occorre prima riportare o rateizzare il residuo"
                    )
                latest_locked = max(
                    (item.due_month for item in expense.recovery_allocations if item.locked_at),
                    default=None,
                )
                if latest_locked and _month_start(settlement_date) <= latest_locked:
                    raise ValueError(
                        "La compensazione non può modificare un mese già consolidato nel cedolino"
                    )
                settlement.amount = amount
                settlement.settlement_date = settlement_date
                settlement.method = method
                settlement.notes = (request.form.get("notes") or "").strip() or None
                db.session.commit()
                audit("expense_settlement_updated", "expense_settlement", settlement.id)
                flash("Compensazione aggiornata", "success")
                return redirect(url_for("expense_detail", expense_id=expense.id))
            except (ValueError, KeyError, TypeError) as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template("expense_settlement_edit.html", expense=_decorate_expense(expense), settlement=settlement)

    @app.get("/expenses/<int:expense_id>/settlements/<int:settlement_id>/attachment")
    @login_required
    def expense_settlement_attachment(expense_id, settlement_id):
        settlement = db.get_or_404(ExpenseSettlement, settlement_id)
        if settlement.expense_id != expense_id or not settlement.stored_name:
            abort(404)
        audit("expense_settlement_attachment_downloaded", "expense_settlement", settlement.id)
        return send_from_directory(app.config["UPLOAD_FOLDER"], settlement.stored_name, as_attachment=True, download_name=settlement.filename)

    @app.post("/expenses/<int:expense_id>/settlements/<int:settlement_id>/delete")
    @login_required
    def expense_settlement_delete(expense_id, settlement_id):
        settlement = db.get_or_404(ExpenseSettlement, settlement_id)
        if settlement.expense_id != expense_id:
            abort(404)
        expense = db.get_or_404(Expense, expense_id)
        latest_locked = max(
            (item.due_month for item in expense.recovery_allocations if item.locked_at),
            default=None,
        )
        if latest_locked and _month_start(settlement.settlement_date) <= latest_locked:
            flash(
                "La compensazione appartiene a un periodo già consolidato nel cedolino",
                "error",
            )
            return redirect(url_for("expense_detail", expense_id=expense_id))
        stored = settlement.stored_name
        db.session.delete(settlement)
        db.session.commit()
        if stored:
            safe_unlink(Path(app.config["UPLOAD_FOLDER"]) / stored)
        audit("expense_settlement_deleted", "expense_settlement", settlement_id)
        flash("Compensazione eliminata", "success")
        return redirect(url_for("expense_detail", expense_id=expense_id))

    @app.post("/expenses/<int:expense_id>/delete")
    @login_required
    def expense_delete(expense_id):
        expense = db.get_or_404(Expense, expense_id)
        files_to_remove = [item.stored_name for item in expense.settlements if item.stored_name]
        db.session.delete(expense)
        db.session.commit()
        for stored in files_to_remove:
            safe_unlink(Path(app.config["UPLOAD_FOLDER"]) / stored)
        audit("expense_deleted", "expense", expense_id)
        flash("Spesa eliminata", "success")
        return redirect(url_for("expenses"))

    def _payment_from_form(payment=None):
        payment = payment or Payment()
        worker_id = request.form.get("worker_id", type=int)
        worker = db.session.get(Worker, worker_id) if worker_id else None
        if not worker:
            raise ValueError("Lavoratore non valido")
        payment_type = (request.form.get("payment_type") or "").strip()
        if payment_type not in {"salary", "inps_contributions", "thirteenth", "tfr", "expense_refund", "other"}:
            raise ValueError("Tipo di pagamento non valido")
        if payment_type == "inps_contributions" and not worker.inps_number:
            raise ValueError("I contributi INPS sono disponibili solo se è registrata la posizione INPS del lavoratore")
        status = (request.form.get("status") or "pending").strip()
        if status not in {"pending", "paid"}:
            raise ValueError("Stato pagamento non valido")
        payment.worker_id = worker.id
        payment.employer_id = worker.employer_id
        payment.payment_type = payment_type
        payment.amount = nonnegative_decimal(request.form.get("amount"), "Importo")
        payment.status = status
        raw_payment_date = (request.form.get("payment_date") or "").strip()
        payment.payment_date = _optional_date(raw_payment_date, "Data pagamento") if raw_payment_date else None
        if status == "paid" and payment.payment_date is None:
            payment.payment_date = date.today()
        if status == "pending":
            payment.payment_date = None
        payment.period_start = _optional_date(request.form.get("period_start"), "Inizio periodo")
        payment.period_end = _optional_date(request.form.get("period_end"), "Fine periodo")
        if payment.period_start and payment.period_end and payment.period_end < payment.period_start:
            raise ValueError("La fine del periodo non può precedere l'inizio")
        payment.description = (request.form.get("description") or "").strip()[:255] or None
        payment.notes = (request.form.get("notes") or "").strip() or None
        return payment

    def _add_payment_attachments(payment):
        added = []
        for uploaded in request.files.getlist("attachments"):
            if not uploaded or not uploaded.filename:
                continue
            safe, _, mime, payload = _validated_upload(uploaded, images_only=False)
            stored = f"payment-{payment.id}-{uuid4().hex}-{safe}"
            (Path(app.config["PAYMENT_FOLDER"]) / stored).write_bytes(payload)
            attachment = PaymentAttachment(
                payment_id=payment.id,
                filename=safe,
                stored_name=stored,
                mime_type=mime,
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
            )
            db.session.add(attachment)
            added.append(attachment)
        return added

    @app.route("/payments", methods=["GET", "POST"])
    @login_required
    def payments():
        if request.method == "POST":
            try:
                payment = _payment_from_form()
                db.session.add(payment)
                db.session.flush()
                _add_payment_attachments(payment)
                db.session.commit()
                audit("payment_created", "payment", payment.id, payment.payment_type)
                flash("Pagamento registrato", "success")
                return redirect(url_for("payment_detail", payment_id=payment.id))
            except (ValueError, OSError) as exc:
                db.session.rollback()
                flash(str(exc), "error")
        worker_id = request.args.get("worker_id", type=int)
        query = Payment.query
        if worker_id:
            query = query.filter_by(worker_id=worker_id)
        rows = query.order_by(Payment.created_at.desc(), Payment.id.desc()).all()
        workers = Worker.query.order_by(Worker.last_name, Worker.first_name).all()
        return render_template(
            "payments.html",
            payments=rows,
            workers=workers,
            payment_labels=PAYMENT_LABELS,
            selected_worker=worker_id,
            today=date.today().isoformat(),
        )

    @app.get("/payments/<int:payment_id>")
    @login_required
    def payment_detail(payment_id):
        payment = db.get_or_404(Payment, payment_id)
        worker = db.session.get(Worker, payment.worker_id)
        employer = db.session.get(Employer, payment.employer_id) if payment.employer_id else None
        attachments = PaymentAttachment.query.filter_by(payment_id=payment.id).order_by(PaymentAttachment.uploaded_at).all()
        report = db.session.get(GeneratedReport, payment.source_report_id) if payment.source_report_id else None
        return render_template(
            "payment_detail.html",
            payment=payment,
            worker=worker,
            employer=employer,
            attachments=attachments,
            source_report=report,
            payment_labels=PAYMENT_LABELS,
        )

    @app.route("/payments/<int:payment_id>/edit", methods=["GET", "POST"])
    @login_required
    def payment_edit(payment_id):
        payment = db.get_or_404(Payment, payment_id)
        if request.method == "POST":
            try:
                _payment_from_form(payment)
                _add_payment_attachments(payment)
                db.session.commit()
                audit("payment_updated", "payment", payment.id, payment.payment_type)
                flash("Pagamento aggiornato", "success")
                return redirect(url_for("payment_detail", payment_id=payment.id))
            except (ValueError, OSError) as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template(
            "payment_edit.html",
            payment=payment,
            workers=Worker.query.order_by(Worker.last_name, Worker.first_name).all(),
            payment_labels=PAYMENT_LABELS,
        )

    @app.post("/payments/<int:payment_id>/delete")
    @login_required
    def payment_delete(payment_id):
        payment = db.get_or_404(Payment, payment_id)
        attachments = PaymentAttachment.query.filter_by(payment_id=payment.id).all()
        for attachment in attachments:
            safe_unlink(Path(app.config["PAYMENT_FOLDER"]) / attachment.stored_name)
            db.session.delete(attachment)
        db.session.delete(payment)
        db.session.commit()
        audit("payment_deleted", "payment", payment_id)
        flash("Pagamento eliminato", "success")
        return redirect(url_for("payments"))

    @app.get("/payments/attachments/<int:attachment_id>")
    @login_required
    def payment_attachment_download(attachment_id):
        attachment = db.get_or_404(PaymentAttachment, attachment_id)
        audit("payment_attachment_downloaded", "payment_attachment", attachment.id)
        return send_from_directory(
            app.config["PAYMENT_FOLDER"],
            attachment.stored_name,
            as_attachment=True,
            download_name=attachment.filename,
        )

    @app.post("/payments/attachments/<int:attachment_id>/delete")
    @login_required
    def payment_attachment_delete(attachment_id):
        attachment = db.get_or_404(PaymentAttachment, attachment_id)
        payment_id = attachment.payment_id
        stored = attachment.stored_name
        db.session.delete(attachment)
        db.session.commit()
        safe_unlink(Path(app.config["PAYMENT_FOLDER"]) / stored)
        audit("payment_attachment_deleted", "payment_attachment", attachment_id)
        flash("Allegato eliminato", "success")
        return redirect(url_for("payment_detail", payment_id=payment_id))

    @app.route("/documents", methods=["GET", "POST"])
    @login_required
    def documents():
        if request.method == "POST":
            f = request.files.get("file")
            try:
                if not f or not f.filename:
                    raise ValueError("Selezionare un file")
                safe = secure_filename(f.filename)
                suffix = Path(safe).suffix.lower()
                if suffix not in ALLOWED_UPLOADS:
                    raise ValueError("Tipo file non consentito")
                payload = f.read()
                if not payload:
                    raise ValueError("Il file è vuoto")
                if len(payload) > app.config["DOCUMENT_MAX_BYTES"]:
                    raise ValueError("Il documento supera la dimensione massima consentita")
                signature_ok = (
                    (suffix == ".pdf" and payload.startswith(b"%PDF-"))
                    or (suffix == ".png" and payload.startswith(b"\x89PNG\r\n\x1a\n"))
                    or (suffix in {".jpg", ".jpeg"} and payload.startswith(b"\xff\xd8\xff"))
                )
                if not signature_ok:
                    raise ValueError("Il contenuto del file non corrisponde all'estensione")
                mime = f.mimetype or "application/octet-stream"
                if mime not in ALLOWED_UPLOADS[suffix]:
                    raise ValueError("MIME type non consentito")
                stored = f"{uuid4().hex}-{safe}"
                destination = Path(app.config["UPLOAD_FOLDER"]) / stored
                destination.write_bytes(payload)
                document = Document(
                    worker_id=int(request.form["worker_id"]),
                    filename=safe,
                    stored_name=stored,
                    category=(request.form.get("category") or "other")[:80],
                    mime_type=mime,
                    sha256=hashlib.sha256(payload).hexdigest(),
                    size_bytes=len(payload),
                )
                db.session.add(document)
                db.session.commit()
                audit("document_uploaded", "document", document.id, document.sha256)
                return redirect(url_for("documents"))
            except (ValueError, OSError) as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template(
            "documents.html",
            workers=Worker.query.all(),
            documents=Document.query.order_by(Document.uploaded_at.desc()).all(),
        )

    @app.get("/documents/<int:document_id>")
    @login_required
    def download_document(document_id):
        d = db.get_or_404(Document, document_id)
        audit("document_downloaded", "document", d.id)
        return send_from_directory(
            app.config["UPLOAD_FOLDER"], d.stored_name, as_attachment=True, download_name=d.filename
        )

    @app.post("/documents/<int:document_id>/delete")
    @login_required
    def delete_document(document_id):
        document = db.get_or_404(Document, document_id)
        stored_name = document.stored_name
        db.session.delete(document)
        db.session.commit()
        safe_unlink(Path(app.config["UPLOAD_FOLDER"]) / stored_name)
        audit("document_deleted", "document", document_id)
        flash("Documento eliminato", "success")
        return redirect(url_for("documents"))

    def _worker_data(worker_id):
        worker = db.get_or_404(Worker, worker_id)
        return (worker,
                WorkEntry.query.filter_by(worker_id=worker_id).all(),
                Absence.query.filter_by(worker_id=worker_id).all(),
                Expense.query.filter_by(worker_id=worker_id).all(),
                HourlyRate.query.filter_by(worker_id=worker_id).order_by(HourlyRate.valid_from).all())

    def _tfr_factor():
        factor = Setting.query.filter_by(key="tfr_divisor").first()
        return nonnegative_decimal(factor.value if factor else "13.5", "Divisore TFR")

    def get_summary(worker_id, year, month):
        if month not in range(1, 13) or year < 1990 or year > 2200:
            raise ValueError("Periodo non valido")
        worker, entries, absences_list, expenses_list, rates_list = _worker_data(worker_id)
        return monthly_summary(entries, absences_list, expenses_list, rates_list, year, month, _tfr_factor(), worker)

    def get_annual(worker_id, year):
        if year < 1990 or year > 2200:
            raise ValueError("Anno non valido")
        worker, entries, absences_list, expenses_list, rates_list = _worker_data(worker_id)
        return worker, annual_summary(entries, absences_list, expenses_list, rates_list, year, _tfr_factor(), worker), vacation_balance(worker, absences_list, year)

    def _employer_for(worker):
        return db.session.get(Employer, worker.employer_id) if worker.employer_id else None


    def _report_approval(worker, default_mode="both"):
        employer = _employer_for(worker)
        mode = (request.args.get("approval") or default_mode).strip().lower()
        if mode not in {"none", "worker", "employer", "both"}:
            mode = default_mode
        place = (request.args.get("signature_place") or "").strip()
        if not place and employer:
            place = employer.city or employer.address or ""
        report_date = request.args.get("report_date") or date.today().isoformat()
        try:
            parsed_date = date.fromisoformat(report_date)
        except ValueError:
            parsed_date = date.today()
        return {
            "mode": mode,
            "place": place,
            "date": parsed_date,
            "worker_signature": _signature_path(worker),
            "employer_signature": _signature_path(employer),
        }

    def _rule_notes(year):
        verified = year in {2025, 2026}
        prefix = f"Regole {year} verificate su fonti ufficiali INPS/Agenzia delle Entrate." if verified else f"Formula generale applicata per {year}; verificare eventuali variazioni annuali su INPS, Ministero del Lavoro e Agenzia delle Entrate prima dell'uso ufficiale."
        return [prefix, "Ferie: 26 giorni lavorativi annui; per servizio inferiore all'anno maturano in dodicesimi e la frazione di mese pari o superiore a 15 giorni vale come mese intero (fonte: INPS, Calcolare contributi, tredicesima e ferie per i lavoratori domestici).", "TFR (rapporti dal 1990): quota dell'anno = retribuzione utile / 13,5. La quota dell'anno corrente non è rivalutata (fonte: INPS, Dimissioni, licenziamento e TFR dei lavoratori domestici; art. 2120 c.c.).", "Quote TFR di anni precedenti: rivalutazione legale 1,5% + 75% dell'incremento dell'indice FOI ISTAT dicembre/dicembre.", "Tredicesima: un dodicesimo della retribuzione annua; nel prospetto viene inclusa come quota maturata stimata nella base utile TFR (fonte: INPS).", "CU di cortesia: il PDF è una certificazione del datore privato non sostituto d'imposta e non il modello CU telematico (fonte: Agenzia delle Entrate, istruzioni dichiarazione precompilata)."]

    def _fiscal_data(worker, summary, year):
        inps = inps_contribution_summary(worker, summary, year) if worker.inps_number else None
        taxes = estimated_irpef_summary(worker, summary, year) if worker.inps_number and worker.contract_number else None
        if not inps and not taxes:
            return None
        return {"inps": inps, "taxes": taxes}

    PAYMENT_LABELS = {
        "salary": "Retribuzione",
        "inps_contributions": "Contributi INPS",
        "thirteenth": "Tredicesima",
        "tfr": "TFR",
        "expense_refund": "Rimborso spese",
        "other": "Altro",
    }

    def _payments_for_period(worker_id, period_start=None, period_end=None, payment_types=None):
        rows = Payment.query.filter_by(worker_id=worker_id).order_by(Payment.created_at, Payment.id).all()
        selected = []
        for payment in rows:
            if payment_types and payment.payment_type not in payment_types:
                continue
            start = payment.period_start or payment.payment_date
            end = payment.period_end or payment.payment_date or start
            if period_start and end and end < period_start:
                continue
            if period_end and start and start > period_end:
                continue
            selected.append(payment)
        return selected

    def _ensure_generated_payment(report, worker, payment_type, amount, period_start, period_end, description):
        amount = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
        if amount <= 0:
            return None
        if payment_type == "inps_contributions" and not worker.inps_number:
            return None
        existing = Payment.query.filter_by(
            worker_id=worker.id,
            payment_type=payment_type,
            period_start=period_start,
            period_end=period_end,
        ).all()
        paid = sum((row.amount for row in existing if row.status == "paid"), Decimal("0"))
        residual = max(Decimal("0"), amount - paid)
        pending = next((row for row in existing if row.status == "pending" and (row.description or "").startswith("Generato automaticamente")), None)
        if residual <= 0:
            if pending:
                db.session.delete(pending)
            return None
        if pending is None:
            pending = Payment(
                worker_id=worker.id,
                employer_id=worker.employer_id,
                source_report_id=report.id,
                payment_type=payment_type,
                amount=residual,
                status="pending",
                period_start=period_start,
                period_end=period_end,
                description=f"Generato automaticamente: {description}",
            )
            db.session.add(pending)
        else:
            pending.amount = residual
            pending.source_report_id = report.id
            pending.employer_id = worker.employer_id
        return pending

    def _archive_pdf(
        worker,
        report_type,
        filename,
        buffer,
        period_start=None,
        period_end=None,
        auto_payments=None,
    ):
        payload = buffer.getvalue() if hasattr(buffer, "getvalue") else buffer.read()
        report = store_report(
            app,
            worker.id if worker else None,
            report_type,
            filename,
            payload,
            period_start=period_start,
            period_end=period_end,
        )
        for spec in auto_payments or []:
            _ensure_generated_payment(
                report,
                worker,
                spec["payment_type"],
                spec.get("amount"),
                period_start,
                period_end,
                spec.get("description") or filename,
            )
        if report_type == "monthly_payroll" and worker and period_start and period_end:
            monthly_expenses = Expense.query.filter(
                Expense.worker_id == worker.id,
                Expense.expense_date <= period_end,
            ).all()
            for expense in monthly_expenses:
                allocations = list(expense.recovery_allocations)
                due_now = [
                    item
                    for item in allocations
                    if period_start <= item.due_month <= period_end
                ]
                if not allocations and period_start <= expense.expense_date <= period_end:
                    manual = sum(
                        (
                            Decimal(item.amount)
                            for item in expense.settlements
                            if item.settlement_date <= period_end
                        ),
                        Decimal("0"),
                    )
                    if not (expense.reimbursed and not expense.settlements):
                        residual = max(Decimal("0"), Decimal(expense.amount) - manual)
                        if residual > 0:
                            allocation = ExpenseRecoveryAllocation(
                                expense_id=expense.id,
                                due_month=period_start,
                                amount=residual.quantize(Decimal("0.01")),
                                locked_at=datetime.now(UTC).replace(tzinfo=None),
                            )
                            db.session.add(allocation)
                            due_now = [allocation]
                lock_time = datetime.now(UTC).replace(tzinfo=None)
                for allocation in due_now:
                    if allocation.locked_at is None:
                        allocation.locked_at = lock_time
        db.session.commit()
        audit("report_generated", "generated_report", report.id, report_type)
        if request.args.get("return_to_list") == "1":
            return redirect(
                url_for(
                    "reports",
                    worker_id=worker.id if worker else None,
                    year=request.args.get("year"),
                    month=request.args.get("month"),
                    approval=request.args.get("approval"),
                    signature_place=request.args.get("signature_place"),
                    report_date=request.args.get("report_date"),
                    created_report=report.id,
                    _anchor="archived-reports",
                )
            )
        return send_file(
            BytesIO(payload),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )


    @app.get("/reports")
    @login_required
    def reports():
        today = date.today()
        workers = Worker.query.order_by(Worker.last_name, Worker.first_name).all()
        worker_id = request.args.get("worker_id", type=int)
        if worker_id is None and len(workers) == 1:
            worker_id = workers[0].id
        year = request.args.get("year", today.year, type=int)
        month = request.args.get("month", today.month, type=int)
        summary = annual = vacation = None
        try:
            if worker_id:
                summary = get_summary(worker_id, year, month)
                _, annual, vacation = get_annual(worker_id, year)
        except ValueError as exc:
            flash(str(exc), "error")
        selected = db.session.get(Worker, worker_id) if worker_id else None
        selected_employer = _employer_for(selected) if selected else None
        permit_overview = (
            permit_metrics(
                selected,
                Absence.query.filter_by(worker_id=worker_id).all(),
                year,
                min(date.today(), date(year, 12, 31)),
            )
            if selected
            else []
        )
        default_place = (selected_employer.city or selected_employer.address or "") if selected_employer else ""
        period_start = date(year, month, 1) if month in range(1, 13) else None
        period_end = date(year, month, monthrange(year, month)[1]) if period_start else None
        period_payments = _payments_for_period(worker_id, period_start, period_end) if worker_id and period_start else []
        paid_salary = sum((p.amount for p in period_payments if p.status == "paid" and p.payment_type == "salary"), Decimal("0"))
        residual_salary = max(Decimal("0"), (summary["payable"] if summary else Decimal("0")) - paid_salary)
        return render_template(
            "reports.html",
            workers=workers,
            summary=summary,
            annual=annual,
            vacation=vacation,
            selected_worker=worker_id,
            year=year,
            month=month,
            approval=request.args.get("approval", "both"),
            signature_place=request.args.get("signature_place", default_place),
            report_date=request.args.get("report_date", today.isoformat()),
            archived_reports=GeneratedReport.query.order_by(GeneratedReport.created_at.desc()).limit(100).all(),
            period_payments=period_payments,
            paid_salary=paid_salary,
            residual_salary=residual_salary,
            created_report=request.args.get("created_report", type=int),
            permit_overview=permit_overview,
        )

    @app.get("/reports/payroll.pdf")
    @login_required
    def payroll():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if None in {worker_id, year, month}:
            abort(400)
        worker, _, absences_list, expenses_list, _ = _worker_data(worker_id)
        try:
            summary = get_summary(worker_id, year, month)
        except ValueError:
            abort(400)
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])
        vacation = vacation_balance(worker, absences_list, year, min(date.today(), date(year, 12, 31)))
        fiscal = _fiscal_data(worker, summary, year)
        period_payments = _payments_for_period(worker.id, period_start, period_end)
        auto_payments = [{
            "payment_type": "salary",
            "amount": summary["payable"],
            "description": f"Retribuzione {month:02d}/{year}",
        }]
        if worker.inps_number and fiscal and fiscal.get("inps") and not fiscal["inps"].get("unavailable"):
            auto_payments.append({
                "payment_type": "inps_contributions",
                "amount": fiscal["inps"].get("total", 0),
                "description": f"Contributi INPS stimati {month:02d}/{year}",
            })
        audit("payroll_downloaded", "worker", worker_id, f"{year}-{month:02d}")
        return _archive_pdf(
            worker,
            "monthly_payroll",
            f"cedolino-{year}-{month:02d}.pdf",
            payroll_pdf(
                worker,
                summary,
                year,
                month,
                _employer_for(worker),
                vacation,
                fiscal,
                [
                    x
                    for x in expenses_list
                    if _expense_relevant_to_period(x, period_start, period_end)
                ],
                approval=_report_approval(worker, "both"),
                payments=period_payments,
                permits=permit_metrics(worker, absences_list, year, period_end),
                sickness=sickness_metrics(worker, absences_list, year, period_end),
            ),
            period_start,
            period_end,
            auto_payments=auto_payments,
        )

    @app.get("/reports/annual-payroll.pdf")
    @login_required
    def annual_payroll():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        if worker_id is None or year is None:
            abort(400)
        worker, annual, vacation = get_annual(worker_id, year)
        annual_absences = Absence.query.filter_by(worker_id=worker_id).all()
        start, end = date(year, 1, 1), date(year, 12, 31)
        audit("annual_payroll_downloaded", "worker", worker_id, str(year))
        return _archive_pdf(
            worker,
            "annual_payroll",
            f"cedolino-annuale-{year}.pdf",
            annual_payroll_pdf(
                worker,
                _employer_for(worker),
                annual,
                year,
                vacation,
                _fiscal_data(worker, annual, year),
                Expense.query.filter(Expense.worker_id == worker_id, Expense.expense_date >= start, Expense.expense_date <= end).order_by(Expense.expense_date).all(),
                approval=_report_approval(worker, "both"),
                payments=_payments_for_period(worker.id, start, end),
                permits=permit_metrics(worker, annual_absences, year, end),
                sickness=sickness_metrics(worker, annual_absences, year, end),
            ),
            start,
            end,
        )

    @app.get("/reports/cu-courtesy.pdf")
    @login_required
    def courtesy_cu():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        if worker_id is None or year is None:
            abort(400)
        worker, annual, _ = get_annual(worker_id, year)
        start, end = date(year, 1, 1), date(year, 12, 31)
        audit("courtesy_cu_downloaded", "worker", worker_id, str(year))
        return _archive_pdf(
            worker,
            "courtesy_cu",
            f"cu-cortesia-{year}.pdf",
            courtesy_cu_pdf(
                worker,
                _employer_for(worker),
                annual,
                year,
                _fiscal_data(worker, annual, year),
                approval=_report_approval(worker, "employer"),
                payments=_payments_for_period(worker.id, start, end),
            ),
            start,
            end,
        )

    @app.get("/reports/tfr.pdf")
    @login_required
    def tfr_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        through_year_end = request.args.get("through_year_end") == "1"
        if worker_id is None or year is None:
            abort(400)
        worker, entries, absences_list, expenses_list, rates_list = _worker_data(worker_id)
        cutoff = date(year, 12, 31) if through_year_end or year < date.today().year else date.today()
        start = date(year, 1, 1)
        tfr = tfr_year_summary(worker, entries, absences_list, expenses_list, rates_list, year, cutoff, _tfr_factor())
        audit("tfr_report_downloaded", "worker", worker_id, str(year))
        return _archive_pdf(
            worker,
            "tfr",
            f"tfr-{year}.pdf",
            tfr_annual_pdf(
                worker,
                _employer_for(worker),
                tfr,
                year,
                _rule_notes(year),
                _fiscal_data(worker, tfr, year),
                approval=_report_approval(worker, "both"),
                payments=_payments_for_period(worker.id, start, cutoff, {"tfr"}),
            ),
            start,
            cutoff,
            auto_payments=[{
                "payment_type": "tfr",
                "amount": tfr["tfr_accrual"],
                "description": f"TFR {year}",
            }],
        )

    @app.get("/reports/thirteenth.pdf")
    @login_required
    def thirteenth_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        through_year_end = request.args.get("through_year_end") == "1"
        if worker_id is None or year is None:
            abort(400)
        worker, entries, absences_list, expenses_list, rates_list = _worker_data(worker_id)
        cutoff = date(year, 12, 31) if through_year_end or year < date.today().year else date.today()
        start = date(year, 1, 1)
        th = thirteenth_year_summary(worker, entries, absences_list, expenses_list, rates_list, year, cutoff)
        annual = annual_summary([e for e in entries if e.work_date <= cutoff], [a for a in absences_list if a.start_date <= cutoff], [x for x in expenses_list if x.expense_date <= cutoff], rates_list, year, _tfr_factor(), worker)
        audit("thirteenth_report_downloaded", "worker", worker_id, str(year))
        return _archive_pdf(
            worker,
            "thirteenth",
            f"tredicesima-{year}.pdf",
            thirteenth_payroll_pdf(
                worker,
                _employer_for(worker),
                th,
                year,
                _rule_notes(year),
                _fiscal_data(worker, annual, year),
                approval=_report_approval(worker, "both"),
                payments=_payments_for_period(worker.id, start, cutoff, {"thirteenth"}),
            ),
            start,
            cutoff,
            auto_payments=[{
                "payment_type": "thirteenth",
                "amount": th["thirteenth"],
                "description": f"Tredicesima {year}",
            }],
        )

    @app.get("/reports/thirteenth-tfr.pdf")
    @login_required
    def thirteenth_tfr_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        through_year_end = request.args.get("through_year_end") == "1"
        if worker_id is None or year is None:
            abort(400)
        worker, entries, absences_list, expenses_list, rates_list = _worker_data(worker_id)
        cutoff = date(year, 12, 31) if through_year_end or year < date.today().year else date.today()
        start = date(year, 1, 1)
        combined = combined_thirteenth_tfr_summary(worker, entries, absences_list, expenses_list, rates_list, year, cutoff, _tfr_factor())
        audit("thirteenth_tfr_report_downloaded", "worker", worker_id, str(year))
        return _archive_pdf(
            worker,
            "thirteenth_tfr",
            f"tredicesima-tfr-{year}.pdf",
            combined_thirteenth_tfr_pdf(
                worker,
                _employer_for(worker),
                combined,
                year,
                _rule_notes(year),
                approval=_report_approval(worker, "both"),
                payments=_payments_for_period(worker.id, start, cutoff, {"thirteenth", "tfr"}),
            ),
            start,
            cutoff,
            auto_payments=[
                {"payment_type": "thirteenth", "amount": combined["thirteenth"]["thirteenth"], "description": f"Tredicesima {year}"},
                {"payment_type": "tfr", "amount": combined["tfr"]["tfr_accrual"], "description": f"TFR {year}"},
            ],
        )

    @app.get("/reports/trend.pdf")
    @login_required
    def trend_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        if worker_id is None or year is None:
            abort(400)
        worker, annual, _ = get_annual(worker_id, year)
        trend_absences = Absence.query.filter_by(worker_id=worker_id).all()
        start, end = date(year, 1, 1), date(year, 12, 31)
        audit("trend_report_downloaded", "worker", worker_id, str(year))
        return _archive_pdf(
            worker,
            "trend",
            f"andamento-{year}.pdf",
            trend_pdf(
                worker,
                _employer_for(worker),
                annual,
                year,
                _fiscal_data(worker, annual, year),
                Expense.query.filter(Expense.worker_id == worker_id, Expense.expense_date >= start, Expense.expense_date <= end).order_by(Expense.expense_date).all(),
                approval=_report_approval(worker, "none"),
                payments=_payments_for_period(worker.id, start, end),
                permits=permit_metrics(worker, trend_absences, year, end),
                sickness=sickness_metrics(worker, trend_absences, year, end),
            ),
            start,
            end,
        )

    @app.get("/reports/location-trend.pdf")
    @login_required
    def location_trend_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        if worker_id is None or year is None:
            abort(400)
        worker = db.get_or_404(Worker, worker_id)
        entries = (
            WorkEntry.query.filter(
                WorkEntry.worker_id == worker_id,
                WorkEntry.work_date >= date(year, 1, 1),
                WorkEntry.work_date <= date(year, 12, 31),
            )
            .order_by(WorkEntry.work_date, WorkEntry.start_time)
            .all()
        )
        by_location = {}
        for entry in entries:
            label = entry.location or "Luogo non specificato"
            row = by_location.setdefault(label, {"total": Decimal("0"), "months": [Decimal("0") for _ in range(12)]})
            row["total"] += entry.hours
            row["months"][entry.work_date.month - 1] += entry.hours
        location_data = [
            {"location": label, "total": values["total"], "months": values["months"]}
            for label, values in sorted(by_location.items(), key=lambda item: (-item[1]["total"], item[0].lower()))
        ]
        audit("location_trend_report_downloaded", "worker", worker_id, str(year))
        return _archive_pdf(
            worker,
            "location_trend",
            f"andamento-ore-luogo-{year}.pdf",
            location_trend_pdf(
                worker,
                _employer_for(worker),
                location_data,
                year,
                approval=_report_approval(worker, "none"),
                payments=_payments_for_period(worker.id, date(year, 1, 1), date(year, 12, 31)),
            ),
            date(year, 1, 1),
            date(year, 12, 31),
        )

    @app.get("/reports/archive/<int:report_id>")
    @login_required
    def download_archived_report(report_id):
        report = db.get_or_404(GeneratedReport, report_id)
        audit("report_downloaded", "generated_report", report.id)
        return send_from_directory(
            app.config["REPORT_FOLDER"],
            report.stored_name,
            as_attachment=True,
            download_name=report.filename,
        )

    @app.get("/reports/archive/<int:report_id>/view")
    @login_required
    def view_archived_report(report_id):
        report = db.get_or_404(GeneratedReport, report_id)
        audit("report_viewed", "generated_report", report.id)
        return send_from_directory(
            app.config["REPORT_FOLDER"],
            report.stored_name,
            as_attachment=False,
            download_name=report.filename,
            mimetype=report.mime_type,
        )

    @app.post("/reports/archive/<int:report_id>/delete")
    @login_required
    def delete_archived_report(report_id):
        report = db.get_or_404(GeneratedReport, report_id)
        stored_name = report.stored_name
        Payment.query.filter_by(source_report_id=report.id).update({"source_report_id": None}, synchronize_session=False)
        db.session.delete(report)
        db.session.commit()
        safe_unlink(Path(app.config["REPORT_FOLDER"]) / stored_name)
        audit("report_deleted", "generated_report", report_id)
        flash("Report eliminato", "success")
        return redirect(url_for("reports"))

    def _calendar_subject(kind, object_id):
        if kind == "worker":
            obj = db.session.get(Worker, object_id)
            if obj is None:
                abort(404)
            return obj, f"{obj.first_name} {obj.last_name}", [obj.id]
        if kind == "employer":
            obj = db.session.get(Employer, object_id)
            if obj is None:
                abort(404)
            worker_ids = [row.id for row in Worker.query.filter_by(employer_id=obj.id).all()]
            return obj, f"{obj.first_name} {obj.last_name}", worker_ids
        abort(404)

    def _subscription_token(kind, object_id, create=False):
        key = _calendar_token_key(kind, object_id)
        token = _setting(key, "") or ""
        if create and not token:
            token = secrets.token_urlsafe(32)
            _save_setting(key, token)
            db.session.commit()
        return token

    def _subscription_authorized(kind, object_id, token):
        expected = _subscription_token(kind, object_id, create=False)
        return bool(expected and token and secrets.compare_digest(expected, token))

    def _calendar_ics(kind, object_id):
        _, label, worker_ids = _calendar_subject(kind, object_id)
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//colf-manager//Calendar subscription//IT",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{_calendar_escape('colf-manager · ' + label)}",
        ]
        if worker_ids:
            workers = {w.id: w for w in Worker.query.filter(Worker.id.in_(worker_ids)).all()}
            entries = (
                WorkEntry.query.filter(WorkEntry.worker_id.in_(worker_ids))
                .order_by(WorkEntry.work_date, WorkEntry.start_time)
                .all()
            )
            for entry in entries:
                worker = workers.get(entry.worker_id)
                worker_name = f"{worker.first_name} {worker.last_name}" if worker else "Lavoratore"
                start = datetime.combine(entry.work_date, entry.start_time)
                end = datetime.combine(entry.work_date, entry.end_time)
                lines.extend(
                    [
                        "BEGIN:VEVENT",
                        f"UID:work-{entry.id}@colf-manager",
                        f"DTSTAMP:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
                        f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
                        f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
                        f"SUMMARY:{_calendar_escape(('Ore straordinarie' if entry.entry_kind == 'overtime' else 'Ore ordinarie') + ' · ' + worker_name)}",
                        f"LOCATION:{_calendar_escape(entry.location)}",
                        f"DESCRIPTION:{_calendar_escape(entry.notes or '')}",
                        "END:VEVENT",
                    ]
                )
            absences = (
                Absence.query.filter(Absence.worker_id.in_(worker_ids))
                .order_by(Absence.start_date, Absence.start_time)
                .all()
            )
            for absence in absences:
                worker = workers.get(absence.worker_id)
                worker_name = f"{worker.first_name} {worker.last_name}" if worker else "Lavoratore"
                current = absence.start_date
                while current <= absence.end_date:
                    start_time = absence.start_time or time(9, 0)
                    end_time = absence.end_time or time(17, 0)
                    start = datetime.combine(current, start_time)
                    end = datetime.combine(current, end_time)
                    kind_label = "Ferie" if absence.kind == "vacation" else "Malattia" if absence.kind in {"health", "sickness"} else "Permesso"
                    lines.extend(
                        [
                            "BEGIN:VEVENT",
                            f"UID:absence-{absence.id}-{current.isoformat()}@colf-manager",
                            f"DTSTAMP:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
                            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
                            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
                            f"SUMMARY:{_calendar_escape(kind_label + ' · ' + worker_name)}",
                            f"DESCRIPTION:{_calendar_escape(absence.notes or '')}",
                            "END:VEVENT",
                        ]
                    )
                    current += timedelta(days=1)
        lines.append("END:VCALENDAR")
        return "\r\n".join(_calendar_fold(line) for line in lines) + "\r\n"

    @app.get("/calendar-subscriptions/<kind>/<int:object_id>/<token>/calendar.ics")
    def calendar_subscription_ics(kind, object_id, token):
        if not _subscription_authorized(kind, object_id, token):
            abort(404)
        payload = _calendar_ics(kind, object_id)
        response = Response(payload, mimetype="text/calendar")
        response.headers["Content-Disposition"] = 'inline; filename="colf-manager.ics"'
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    @app.route(
        "/caldav/<kind>/<int:object_id>/<token>/",
        methods=["GET", "OPTIONS", "PROPFIND", "REPORT"],
    )
    def calendar_subscription_caldav(kind, object_id, token):
        if not _subscription_authorized(kind, object_id, token):
            abort(404)
        _, label, _ = _calendar_subject(kind, object_id)
        collection_href = request.path
        calendar_href = collection_href + "calendar.ics"
        if request.method == "OPTIONS":
            response = Response(status=204)
            response.headers["Allow"] = "OPTIONS, GET, PROPFIND, REPORT"
            response.headers["DAV"] = "1, calendar-access"
            return response
        if request.method == "GET":
            return redirect(calendar_href)
        if request.method == "REPORT":
            calendar_data = _calendar_ics(kind, object_id)
            xml = (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                '<d:response><d:href>'
                + calendar_href
                + '</d:href><d:propstat><d:prop><d:getetag>"colf-manager"</d:getetag>'
                '<c:calendar-data><![CDATA['
                + calendar_data
                + ']]></c:calendar-data></d:prop><d:status>HTTP/1.1 200 OK</d:status>'
                '</d:propstat></d:response></d:multistatus>'
            )
            response = Response(xml, status=207, mimetype="application/xml")
            response.headers["DAV"] = "1, calendar-access"
            return response
        display_name = html_escape(f"colf-manager · {label}", quote=True)
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            '<d:response><d:href>'
            + collection_href
            + '</d:href><d:propstat><d:prop>'
            '<d:resourcetype><d:collection/><c:calendar/></d:resourcetype>'
            f'<d:displayname>{display_name}</d:displayname>'
            '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
            '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>'
        )
        response = Response(xml, status=207, mimetype="application/xml")
        response.headers["DAV"] = "1, calendar-access"
        return response

    @app.get("/caldav/<kind>/<int:object_id>/<token>/calendar.ics")
    def calendar_subscription_caldav_ics(kind, object_id, token):
        return calendar_subscription_ics(kind, object_id, token)

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        admin_keys = [
            "calendar_recent_limit",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_username",
            "smtp_password",
            "smtp_from_email",
            "smtp_from_name",
            "auth_methods",
            "external_url",
        ]
        selected_kind = request.args.get("calendar_kind", "worker")
        selected_id = request.args.get("calendar_id", type=int)
        if request.method == "POST":
            action = request.form.get("action", "save_settings")
            try:
                if action == "change_password":
                    if not check_password_hash(
                        current_user.password_hash, request.form.get("current_password", "")
                    ):
                        raise ValueError("Password attuale non valida")
                    new_password = request.form.get("new_password", "")
                    if new_password != request.form.get("confirm_password", ""):
                        raise ValueError("Le nuove password non coincidono")
                    validate_password(new_password)
                    current_user.password_hash = generate_password_hash(new_password)
                    current_user.must_change_password = False
                    db.session.commit()
                    audit("password_changed", "user", current_user.id)
                    flash("Password aggiornata", "success")
                    return redirect(url_for("settings") + "#password")

                if action in {"calendar_select", "calendar_regenerate", "calendar_revoke"}:
                    if not current_user.is_admin:
                        abort(403)
                    target = request.form.get("calendar_target", "")
                    if ":" not in target:
                        raise ValueError("Selezionare un calendario")
                    selected_kind, raw_id = target.split(":", 1)
                    selected_id = int(raw_id)
                    _calendar_subject(selected_kind, selected_id)
                    key = _calendar_token_key(selected_kind, selected_id)
                    if action == "calendar_revoke":
                        row = db.session.get(Setting, key)
                        if row is not None:
                            db.session.delete(row)
                            db.session.commit()
                        audit("calendar_subscription_revoked", selected_kind, selected_id)
                        flash("Sottoscrizione revocata", "success")
                        return redirect(url_for("settings") + "#calendar-subscriptions")
                    token = secrets.token_urlsafe(32) if action == "calendar_regenerate" else None
                    if token:
                        _save_setting(key, token)
                        db.session.commit()
                    else:
                        _subscription_token(selected_kind, selected_id, create=True)
                    audit("calendar_subscription_enabled", selected_kind, selected_id)
                    return redirect(
                        url_for(
                            "settings",
                            calendar_kind=selected_kind,
                            calendar_id=selected_id,
                        )
                        + "#calendar-subscriptions"
                    )

                if not current_user.is_admin:
                    abort(403)
                recent_limit = max(
                    1, min(50, int(request.form.get("calendar_recent_limit", "10")))
                )
                _save_setting("calendar_recent_limit", recent_limit)
                external_url = request.form.get("external_url", "").strip().rstrip("/")
                if external_url:
                    parsed = urlsplit(external_url)
                    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                        raise ValueError("URL esterna non valida: usare http:// o https://")
                _save_setting("external_url", external_url)
                _save_setting("smtp_host", request.form.get("smtp_host", "").strip())
                _save_setting("smtp_port", int(request.form.get("smtp_port", "587") or 587))
                security = request.form.get("smtp_security", "starttls")
                if security not in {"none", "starttls", "ssl"}:
                    raise ValueError("Sicurezza SMTP non valida")
                _save_setting("smtp_security", security)
                _save_setting("smtp_username", request.form.get("smtp_username", "").strip())
                if request.form.get("smtp_password"):
                    _save_setting("smtp_password", request.form.get("smtp_password"))
                _save_setting("smtp_from_email", request.form.get("smtp_from_email", "").strip())
                _save_setting(
                    "smtp_from_name", request.form.get("smtp_from_name", "colf-manager").strip()
                )
                _save_setting("auth_methods", "local")
                db.session.commit()
                audit("settings_updated", "setting")
                flash("Impostazioni salvate", "success")
                return redirect(url_for("settings"))
            except (ValueError, TypeError) as exc:
                db.session.rollback()
                flash(str(exc), "error")

        values = {key: _setting(key, "") for key in admin_keys}
        values["calendar_recent_limit"] = values["calendar_recent_limit"] or "10"
        values["smtp_port"] = values["smtp_port"] or "587"
        values["smtp_security"] = values["smtp_security"] or "starttls"
        values["smtp_from_name"] = values["smtp_from_name"] or "colf-manager"
        values["auth_methods"] = "local"
        values["smtp_password_configured"] = bool(values.get("smtp_password"))
        values.pop("smtp_password", None)

        subscription = None
        if current_user.is_admin and selected_id:
            try:
                _, label, _ = _calendar_subject(selected_kind, selected_id)
                token = _subscription_token(selected_kind, selected_id, create=False)
                if token:
                    base = _external_base_url()
                    subscription = {
                        "kind": selected_kind,
                        "id": selected_id,
                        "label": label,
                        "ics_url": f"{base}/calendar-subscriptions/{selected_kind}/{selected_id}/{token}/calendar.ics",
                        "caldav_url": f"{base}/caldav/{selected_kind}/{selected_id}/{token}/",
                    }
            except (ValueError, TypeError):
                subscription = None

        return render_template(
            "settings.html",
            settings=values,
            workers=Worker.query.order_by(Worker.last_name, Worker.first_name).all(),
            employers=Employer.query.order_by(Employer.last_name, Employer.first_name).all(),
            subscription=subscription,
            selected_kind=selected_kind,
            selected_id=selected_id,
        )

    def _smtp_settings():
        return {
            "host": _setting("smtp_host", ""),
            "port": int(_setting("smtp_port", "587") or 587),
            "security": _setting("smtp_security", "starttls"),
            "username": _setting("smtp_username", ""),
            "password": _setting("smtp_password", ""),
            "from_email": _setting("smtp_from_email", ""),
            "from_name": _setting("smtp_from_name", "colf-manager"),
        }

    @app.route("/mail/compose", methods=["GET", "POST"])
    @login_required
    def mail_compose():
        artifact_type = request.values.get("artifact_type", "notification")
        artifact_id = request.values.get("artifact_id", type=int)
        attachment = None
        default_to = ""
        default_subject = "Comunicazione colf-manager"
        if artifact_type == "report" and artifact_id:
            report = db.get_or_404(GeneratedReport, artifact_id)
            attachment = (Path(app.config["REPORT_FOLDER"]) / report.stored_name, report.filename, report.mime_type)
            worker = db.session.get(Worker, report.worker_id) if report.worker_id else None
            default_to = worker.email if worker and worker.email else ""
            default_subject = f"Report {report.report_type} - {report.filename}"
        elif artifact_type == "document" and artifact_id:
            document = db.get_or_404(Document, artifact_id)
            attachment = (Path(app.config["DOCUMENT_FOLDER"]) / document.stored_name, document.filename, document.mime_type or "application/octet-stream")
            worker = db.session.get(Worker, document.worker_id)
            default_to = worker.email if worker and worker.email else ""
            default_subject = f"Documento - {document.filename}"
        if request.method == "POST":
            try:
                to_address = request.form.get("to", "").strip()
                subject = request.form.get("subject", "").strip()
                body = request.form.get("body", "").strip()
                attachments = []
                if attachment:
                    if not attachment[0].is_file():
                        raise ValueError("Allegato non disponibile")
                    attachments.append((attachment[1], attachment[2], attachment[0].read_bytes()))
                send_smtp_message(_smtp_settings(), to_address, subject, body, attachments)
                audit("email_sent", artifact_type, artifact_id, details=f"to={to_address}")
                flash("Messaggio inviato", "success")
                return redirect(url_for("reports") if artifact_type == "report" else url_for("documents") if artifact_type == "document" else url_for("dashboard"))
            except (ValueError, OSError) as exc:
                flash(f"Invio non riuscito: {exc}", "error")
        return render_template(
            "mail_compose.html",
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            attachment_name=attachment[1] if attachment else None,
            default_to=default_to,
            default_subject=default_subject,
        )

    @app.route("/admin/archive", methods=["GET", "POST"])
    @admin_required
    def archive_admin():
        cleanup_result = None
        if request.method == "POST":
            action = request.form.get("action")
            if action == "import":
                upload = request.files.get("archive")
                confirmation = request.form.get("confirmation")
                if not upload or not upload.filename:
                    flash("Selezionare un archivio ZIP", "error")
                elif confirmation != "IMPORT":
                    flash("Digitare IMPORT per confermare il ripristino completo", "error")
                else:
                    try:
                        result = restore_full_export(app, upload.stream)
                        flash(
                            f"Import completato da {result['source_version']} ({result['source_build']}). Effettuare nuovamente l'accesso.",
                            "success",
                        )
                        return redirect(url_for("login"))
                    except (ValueError, OSError, zipfile.BadZipFile, SQLAlchemyError) as exc:
                        db.session.rollback()
                        flash(f"Import fallito: {exc}", "error")
            elif action == "cleanup":
                cleanup_result = cleanup_orphan_files(app, dry_run=False)
                flash(f"Pulizia completata: {len(cleanup_result['deleted'])} file orfani eliminati", "success")
        return render_template("archive_admin.html", cleanup_result=cleanup_result)

    @app.get("/admin/archive/export")
    @admin_required
    def archive_export():
        archive = create_full_export(app)
        audit("full_export_created", "backup", details=archive.name)
        return send_file(
            archive,
            mimetype="application/zip",
            as_attachment=True,
            download_name=archive.name,
            max_age=0,
        )

    return app


def main():
    create_app().run(
        host=os.getenv("COLF_MANAGER_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
