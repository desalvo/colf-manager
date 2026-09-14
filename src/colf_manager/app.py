# fmt: off
import hashlib
import os
import secrets
import zipfile
from calendar import monthrange
from datetime import date
from io import BytesIO
from decimal import Decimal
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
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
    Employer,
    HourlyRate,
    Location,
    Setting,
    User,
    WorkEntry,
    Worker,
    db,
)
from .reporting import (
    annual_payroll_pdf,
    courtesy_cu_pdf,
    payroll_pdf,
    tfr_annual_pdf,
    trend_pdf,
    thirteenth_payroll_pdf,
    combined_thirteenth_tfr_pdf,
)
from .storage import cleanup_orphan_files, safe_unlink, store_report
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
}


def _is_placeholder(value):
    lowered = (value or "").strip().lower().replace("-", "_")
    return not lowered or lowered.startswith(("change_me", "replace_with"))


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    if "worker" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("worker")}
        statements = []
        additions = {
            "employer_id": "INTEGER",
            "birth_date": "DATE",
            "address": "TEXT",
            "phone": "VARCHAR(40)",
            "email": "VARCHAR(255)",
            "employment_end": "DATE",
            "vacation_advance_allowed": "BOOLEAN NOT NULL DEFAULT FALSE",
            "contract_number": "VARCHAR(100)",
            "contract_type": "VARCHAR(20) NOT NULL DEFAULT 'permanent'",
            "employer_covers_all_taxes": "BOOLEAN NOT NULL DEFAULT FALSE",
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
            and request.endpoint not in {"change_password", "logout", "static", "health"}
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
            "default-src 'self'; img-src 'self' https://images.unsplash.com data:; "
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
                return redirect(url_for("change_password" if user.must_change_password else "dashboard"))
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
        stats = {"workers": len(workers), "hours": 0, "pay": 0, "tfr": 0}
        for worker in workers:
            summary = get_summary(worker.id, year, month)
            stats["hours"] += float(summary["worked_hours"])
            stats["pay"] += float(summary["payable"])
            stats["tfr"] += float(summary["tfr_accrual"])
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])
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
        worker.vacation_advance_allowed = "vacation_advance_allowed" in request.form
        worker.notes = (request.form.get("notes") or "").strip() or None
        return worker

    @app.route("/workers", methods=["GET", "POST"])
    @login_required
    def workers():
        if request.method == "POST":
            try:
                w = _worker_from_form()
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
                db.session.commit()
                audit("worker_updated", "worker", worker.id)
                flash("Dati del lavoratore aggiornati", "success")
                return redirect(url_for("worker_detail", worker_id=worker.id))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                flash(str(exc) if isinstance(exc, ValueError) else "Dati non validi", "error")
        return render_template("worker_edit.html", worker=worker, employers=Employer.query.order_by(Employer.last_name).all())

    @app.post("/workers/<int:worker_id>/delete")
    @login_required
    def worker_delete(worker_id):
        worker = db.get_or_404(Worker, worker_id)
        if request.form.get("confirmation") != "DELETE":
            flash("Digitare DELETE per confermare la cancellazione totale", "error")
            return redirect(url_for("worker_detail", worker_id=worker.id))
        documents = Document.query.filter_by(worker_id=worker.id).all()
        reports = GeneratedReport.query.filter_by(worker_id=worker.id).all()
        for document in documents:
            safe_unlink(Path(app.config["UPLOAD_FOLDER"]) / document.stored_name)
        for report in reports:
            safe_unlink(Path(app.config["REPORT_FOLDER"]) / report.stored_name)
        for model in (WorkEntry, Absence, Expense, Document, GeneratedReport, HourlyRate):
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
                db.session.commit()
                audit("employer_updated", "employer", employer.id)
                flash("Dati del datore di lavoro aggiornati", "success")
                return redirect(url_for("employer_detail", employer_id=employer.id))
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template("employer_edit.html", employer=employer)

    @app.post("/employers/<int:employer_id>/delete")
    @login_required
    def employer_delete(employer_id):
        employer = db.get_or_404(Employer, employer_id)
        if request.form.get("confirmation") != "DELETE":
            flash("Digitare DELETE per confermare la cancellazione totale", "error")
            return redirect(url_for("employer_detail", employer_id=employer.id))
        Worker.query.filter_by(employer_id=employer.id).update({"employer_id": None}, synchronize_session=False)
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

    @app.post("/rates")
    @login_required
    def rates():
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
            flash("Tariffa aggiornata", "success")
        except (ValueError, IntegrityError) as exc:
            db.session.rollback()
            flash(str(exc) if isinstance(exc, ValueError) else "Esiste già una tariffa con questa decorrenza", "error")
        return redirect(url_for("workers"))

    @app.route("/calendar")
    @login_required
    def calendar():
        return render_template(
            "calendar.html",
            workers=Worker.query.order_by(Worker.last_name).all(),
            locations=Location.query.order_by(Location.name).all(),
        )

    @app.get("/api/events")
    @login_required
    def events():
        worker_id = request.args.get("worker_id", type=int)
        q = WorkEntry.query
        if worker_id:
            q = q.filter_by(worker_id=worker_id)
        result = [
            {
                "id": f"work-{e.id}",
                "title": f"{e.location} · {e.hours.quantize(Decimal('0.01'))}h",
                "start": f"{e.work_date}T{e.start_time}",
                "end": f"{e.work_date}T{e.end_time}",
                "backgroundColor": "#287d70",
                "extendedProps": {"type": "work", "location": e.location},
            }
            for e in q.all()
        ]
        aq = Absence.query
        if worker_id:
            aq = aq.filter_by(worker_id=worker_id)
        colors = {"vacation": "#dfa63d", "sickness": "#d7675f", "unpaid_leave": "#78868a"}
        result += [
            {
                "id": f"absence-{a.id}",
                "title": a.kind.replace("_", " "),
                "start": str(a.start_date),
                "end": str(a.end_date),
                "allDay": True,
                "backgroundColor": colors.get(a.kind),
            }
            for a in aq.all()
        ]
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
            entry = WorkEntry(
                worker_id=int(payload["worker_id"]),
                location_id=location.id if location else None,
                work_date=parse_date(payload["work_date"], "Data"),
                start_time=start_time,
                end_time=end_time,
                break_minutes=break_minutes,
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
        e = db.get_or_404(WorkEntry, entry_id)
        payload = request.get_json(silent=True) or {}
        try:
            work_date = parse_date(payload.get("work_date", str(e.work_date)), "Data")
            start_time = parse_time(payload["start_time"], "Inizio") if payload.get("start_time") else e.start_time
            end_time = parse_time(payload["end_time"], "Fine") if payload.get("end_time") else e.end_time
            validate_work_times(start_time, end_time, e.break_minutes)
            e.work_date, e.start_time, e.end_time = work_date, start_time, end_time
            db.session.commit()
            audit("work_moved", "work_entry", e.id)
            return {"ok": True}
        except ValueError as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400

    @app.post("/absences")
    @login_required
    def absences():
        try:
            worker = db.get_or_404(Worker, int(request.form["worker_id"]))
            start_date = parse_date(request.form["start_date"], "Dal")
            end_date = parse_date(request.form["end_date"], "Al")
            if end_date < start_date:
                raise ValueError("La data finale deve essere successiva o uguale a quella iniziale")
            kind = request.form["kind"]
            if kind not in {"vacation", "sickness", "unpaid_leave"}:
                raise ValueError("Tipo assenza non valido")
            paid = "paid" in request.form or kind == "vacation"
            paid_hours_raw = request.form.get("paid_hours")
            if kind == "vacation" and not paid_hours_raw:
                paid_hours = Decimal(vacation_working_days(start_date, end_date)) * vacation_hours_per_day(worker)
            else:
                paid_hours = nonnegative_decimal(paid_hours_raw, "Ore pagate")
            absence = Absence(worker_id=worker.id, start_date=start_date, end_date=end_date, kind=kind, paid=paid, paid_hours=paid_hours, notes=request.form.get("notes") or None)
            if kind == "vacation":
                existing = Absence.query.filter_by(worker_id=worker.id).all()
                for year in range(start_date.year, end_date.year + 1):
                    balance = vacation_balance(worker, existing + [absence], year, min(end_date, date(year, 12, 31)))
                    if balance["available_usable"] < 0:
                        raise ValueError(f"Ferie insufficienti per {year}: abilita la fruizione anticipata delle ferie da maturare oppure riduci il periodo")
            db.session.add(absence)
            db.session.commit()
            audit("absence_created", "absence", absence.id)
            flash("Assenza registrata", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
        return redirect(url_for("calendar"))

    @app.route("/expenses", methods=["GET", "POST"])
    @login_required
    def expenses():
        if request.method == "POST":
            try:
                direction = request.form["direction"]
                if direction not in {"employer_advance", "worker_advance"}:
                    raise ValueError("Direzione non valida")
                expense = Expense(
                    worker_id=int(request.form["worker_id"]),
                    expense_date=parse_date(request.form["expense_date"], "Data"),
                    description=request.form["description"].strip()[:255],
                    amount=nonnegative_decimal(request.form["amount"], "Importo"),
                    direction=direction,
                )
                db.session.add(expense)
                db.session.commit()
                audit("expense_created", "expense", expense.id)
                flash("Spesa registrata", "success")
                return redirect(url_for("expenses"))
            except ValueError as exc:
                db.session.rollback()
                flash(str(exc), "error")
        return render_template(
            "expenses.html",
            workers=Worker.query.all(),
            expenses=Expense.query.order_by(Expense.expense_date.desc()).all(),
        )

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
        return monthly_summary(entries, absences_list, expenses_list, rates_list, year, month, _tfr_factor())

    def get_annual(worker_id, year):
        if year < 1990 or year > 2200:
            raise ValueError("Anno non valido")
        worker, entries, absences_list, expenses_list, rates_list = _worker_data(worker_id)
        return worker, annual_summary(entries, absences_list, expenses_list, rates_list, year, _tfr_factor()), vacation_balance(worker, absences_list, year)

    def _employer_for(worker):
        return db.session.get(Employer, worker.employer_id) if worker.employer_id else None

    def _rule_notes(year):
        verified = year in {2025, 2026}
        prefix = f"Regole {year} verificate nel pacchetto r19 su fonti ufficiali INPS/Agenzia delle Entrate." if verified else f"Formula generale applicata per {year}; verificare eventuali variazioni annuali su INPS, Ministero del Lavoro e Agenzia delle Entrate prima dell'uso ufficiale."
        return [prefix, "Ferie: 26 giorni lavorativi annui; per servizio inferiore all'anno maturano in dodicesimi e la frazione di mese pari o superiore a 15 giorni vale come mese intero (fonte: INPS, Calcolare contributi, tredicesima e ferie per i lavoratori domestici).", "TFR (rapporti dal 1990): quota dell'anno = retribuzione utile / 13,5. La quota dell'anno corrente non è rivalutata (fonte: INPS, Dimissioni, licenziamento e TFR dei lavoratori domestici; art. 2120 c.c.).", "Quote TFR di anni precedenti: rivalutazione legale 1,5% + 75% dell'incremento dell'indice FOI ISTAT dicembre/dicembre.", "Tredicesima: un dodicesimo della retribuzione annua; nel prospetto viene inclusa come quota maturata stimata nella base utile TFR (fonte: INPS).", "CU di cortesia: il PDF è una certificazione del datore privato non sostituto d'imposta e non il modello CU telematico (fonte: Agenzia delle Entrate, istruzioni dichiarazione precompilata)."]

    def _fiscal_data(worker, summary, year):
        if not worker.inps_number or not worker.contract_number:
            return None
        return {
            "inps": inps_contribution_summary(worker, summary, year),
            "taxes": estimated_irpef_summary(worker, summary, year),
        }

    def _archive_pdf(worker, report_type, filename, buffer, period_start=None, period_end=None):
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
        audit("report_generated", "generated_report", report.id, report_type)
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
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", today.year, type=int)
        month = request.args.get("month", today.month, type=int)
        summary = annual = vacation = None
        try:
            if worker_id:
                summary = get_summary(worker_id, year, month)
                _, annual, vacation = get_annual(worker_id, year)
        except ValueError as exc:
            flash(str(exc), "error")
        return render_template(
            "reports.html",
            workers=Worker.query.order_by(Worker.last_name).all(),
            summary=summary,
            annual=annual,
            vacation=vacation,
            selected_worker=worker_id,
            year=year,
            month=month,
            archived_reports=GeneratedReport.query.order_by(GeneratedReport.created_at.desc()).limit(100).all(),
        )

    @app.get("/reports/payroll.pdf")
    @login_required
    def payroll():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if None in {worker_id, year, month}:
            abort(400)
        worker, _, absences_list, _, _ = _worker_data(worker_id)
        try:
            summary = get_summary(worker_id, year, month)
        except ValueError:
            abort(400)
        vacation=vacation_balance(worker,absences_list,year,min(date.today(),date(year,12,31)))
        audit("payroll_downloaded","worker",worker_id,f"{year}-{month:02d}")
        return _archive_pdf(worker, "monthly_payroll", f"cedolino-{year}-{month:02d}.pdf", payroll_pdf(worker,summary,year,month,_employer_for(worker),vacation,_fiscal_data(worker, summary, year)), date(year, month, 1), date(year, month, monthrange(year, month)[1]))

    @app.get("/reports/annual-payroll.pdf")
    @login_required
    def annual_payroll():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        if worker_id is None or year is None:
            abort(400)
        worker,annual,vacation=get_annual(worker_id,year)
        audit("annual_payroll_downloaded","worker",worker_id,str(year))
        return _archive_pdf(worker, "annual_payroll", f"cedolino-annuale-{year}.pdf", annual_payroll_pdf(worker,_employer_for(worker),annual,year,vacation,_fiscal_data(worker, annual, year)), date(year, 1, 1), date(year, 12, 31))

    @app.get("/reports/cu-courtesy.pdf")
    @login_required
    def courtesy_cu():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        if worker_id is None or year is None:
            abort(400)
        worker,annual,_=get_annual(worker_id,year)
        audit("courtesy_cu_downloaded","worker",worker_id,str(year))
        return _archive_pdf(worker, "courtesy_cu", f"cu-cortesia-{year}.pdf", courtesy_cu_pdf(worker,_employer_for(worker),annual,year,_fiscal_data(worker, annual, year)), date(year, 1, 1), date(year, 12, 31))

    @app.get("/reports/tfr.pdf")
    @login_required
    def tfr_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        through_year_end = request.args.get("through_year_end") == "1"
        if worker_id is None or year is None:
            abort(400)
        worker,entries,absences_list,expenses_list,rates_list=_worker_data(worker_id)
        cutoff=date(year,12,31) if through_year_end or year < date.today().year else date.today()
        tfr=tfr_year_summary(worker,entries,absences_list,expenses_list,rates_list,year,cutoff,_tfr_factor())
        audit("tfr_report_downloaded","worker",worker_id,str(year))
        return _archive_pdf(worker, "tfr", f"tfr-{year}.pdf", tfr_annual_pdf(worker,_employer_for(worker),tfr,year,_rule_notes(year),_fiscal_data(worker, tfr, year)), date(year, 1, 1), cutoff)

    @app.get("/reports/thirteenth.pdf")
    @login_required
    def thirteenth_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        through_year_end = request.args.get("through_year_end") == "1"
        if worker_id is None or year is None:
            abort(400)
        worker,entries,absences_list,expenses_list,rates_list=_worker_data(worker_id)
        cutoff=date(year,12,31) if through_year_end or year < date.today().year else date.today()
        th=thirteenth_year_summary(worker,entries,absences_list,expenses_list,rates_list,year,cutoff)
        annual=annual_summary([e for e in entries if e.work_date <= cutoff],[a for a in absences_list if a.start_date <= cutoff],[x for x in expenses_list if x.expense_date <= cutoff],rates_list,year,_tfr_factor())
        audit("thirteenth_report_downloaded","worker",worker_id,str(year))
        return _archive_pdf(worker, "thirteenth", f"tredicesima-{year}.pdf", thirteenth_payroll_pdf(worker,_employer_for(worker),th,year,_rule_notes(year),_fiscal_data(worker, annual, year)), date(year, 1, 1), cutoff)

    @app.get("/reports/thirteenth-tfr.pdf")
    @login_required
    def thirteenth_tfr_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        through_year_end = request.args.get("through_year_end") == "1"
        if worker_id is None or year is None:
            abort(400)
        worker,entries,absences_list,expenses_list,rates_list=_worker_data(worker_id)
        cutoff=date(year,12,31) if through_year_end or year < date.today().year else date.today()
        combined=combined_thirteenth_tfr_summary(worker,entries,absences_list,expenses_list,rates_list,year,cutoff,_tfr_factor())
        audit("thirteenth_tfr_report_downloaded","worker",worker_id,str(year))
        return _archive_pdf(worker, "thirteenth_tfr", f"tredicesima-tfr-{year}.pdf", combined_thirteenth_tfr_pdf(worker,_employer_for(worker),combined,year,_rule_notes(year)), date(year, 1, 1), cutoff)

    @app.get("/reports/trend.pdf")
    @login_required
    def trend_report():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        if worker_id is None or year is None:
            abort(400)
        worker,annual,_=get_annual(worker_id,year)
        audit("trend_report_downloaded","worker",worker_id,str(year))
        return _archive_pdf(worker, "trend", f"andamento-{year}.pdf", trend_pdf(worker,_employer_for(worker),annual,year,_fiscal_data(worker, annual, year)), date(year, 1, 1), date(year, 12, 31))

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

    @app.post("/reports/archive/<int:report_id>/delete")
    @login_required
    def delete_archived_report(report_id):
        report = db.get_or_404(GeneratedReport, report_id)
        stored_name = report.stored_name
        db.session.delete(report)
        db.session.commit()
        safe_unlink(Path(app.config["REPORT_FOLDER"]) / stored_name)
        audit("report_deleted", "generated_report", report_id)
        flash("Report eliminato", "success")
        return redirect(url_for("reports"))

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
