import hashlib
import os
import secrets
from datetime import date
from decimal import Decimal
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    abort,
    current_app,
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

from .calculations import monthly_summary
from .models import (
    Absence,
    AuditLog,
    Document,
    Expense,
    HourlyRate,
    Setting,
    User,
    WorkEntry,
    Worker,
    db,
)
from .reporting import payroll_pdf
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
            statements.append(
                'ALTER TABLE "user" ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE'
            )
        if "must_change_password" not in columns:
            statements.append(
                'ALTER TABLE "user" ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT TRUE'
            )
        if "is_active" not in columns:
            statements.append(
                'ALTER TABLE "user" ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE'
            )
        if "created_at" not in columns:
            statements.append('ALTER TABLE "user" ADD COLUMN created_at TIMESTAMP')
        for statement in statements:
            db.session.execute(text(statement))
        if statements:
            db.session.commit()
            db.session.execute(
                text('UPDATE "user" SET is_admin=TRUE WHERE id=(SELECT MIN(id) FROM "user")')
            )
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
            raise RuntimeError(
                "COLF_MANAGER_SECRET_KEY must be a non-placeholder value of at least 32 characters"
            )
        if _is_placeholder(admin_password):
            raise RuntimeError(
                "COLF_MANAGER_ADMIN_PASSWORD must be set to a non-placeholder password"
            )
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
        MAX_CONTENT_LENGTH=int(os.getenv("COLF_MANAGER_MAX_UPLOAD_BYTES", str(16 * 1024 * 1024))),
        UPLOAD_FOLDER=str(data_dir / "documents"),
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

    @login.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    def audit(action, object_type=None, object_id=None, details=None, user_id=None):
        try:
            db.session.add(
                AuditLog(
                    user_id=user_id
                    if user_id is not None
                    else (current_user.id if current_user.is_authenticated else None),
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
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
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
        return {"status": "ok", "version": "1.0.0"}

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"])
    def login_view():
        if request.method == "POST":
            username = request.form.get("username", "")[:80]
            user = User.query.filter_by(username=username).first()
            if (
                user
                and user.is_active
                and check_password_hash(user.password_hash, request.form.get("password", ""))
            ):
                login_user(user)
                audit("login", "user", user.id, user_id=user.id)
                return redirect(
                    url_for("change_password" if user.must_change_password else "dashboard")
                )
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
            if not check_password_hash(
                current_user.password_hash, request.form.get("current_password", "")
            ):
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
                flash(
                    str(exc) if isinstance(exc, ValueError) else "Nome utente già esistente",
                    "error",
                )
        return render_template("users.html", users=User.query.order_by(User.username).all())

    @app.get("/")
    @login_required
    def dashboard():
        today = date.today()
        workers = Worker.query.order_by(Worker.last_name).all()
        stats = {"workers": len(workers), "hours": 0, "pay": 0, "tfr": 0}
        for worker in workers:
            s = get_summary(worker.id, today.year, today.month)
            stats["hours"] += float(s["worked_hours"])
            stats["pay"] += float(s["payable"])
            stats["tfr"] += float(s["tfr_accrual"])
        recent = WorkEntry.query.order_by(WorkEntry.work_date.desc()).limit(8).all()
        return render_template(
            "dashboard.html", workers=workers, stats=stats, recent=recent, today=today
        )

    @app.route("/workers", methods=["GET", "POST"])
    @login_required
    def workers():
        if request.method == "POST":
            try:
                w = Worker(
                    first_name=request.form["first_name"].strip(),
                    last_name=request.form["last_name"].strip(),
                    fiscal_code=request.form.get("fiscal_code") or None,
                    inps_number=request.form.get("inps_number") or None,
                    employment_start=parse_date(
                        request.form["employment_start"], "Data assunzione"
                    ),
                    weekly_hours=nonnegative_decimal(
                        request.form.get("weekly_hours"), "Ore settimanali"
                    ),
                )
                db.session.add(w)
                db.session.flush()
                if request.form.get("hourly_rate"):
                    db.session.add(
                        HourlyRate(
                            worker_id=w.id,
                            valid_from=w.employment_start,
                            amount=nonnegative_decimal(request.form["hourly_rate"], "Tariffa"),
                        )
                    )
                db.session.commit()
                audit("worker_created", "worker", w.id)
                flash("Lavoratrice registrata", "success")
                return redirect(url_for("workers"))
            except (ValueError, IntegrityError) as exc:
                db.session.rollback()
                flash(
                    str(exc) if isinstance(exc, ValueError) else "Dati duplicati o non validi",
                    "error",
                )
        return render_template(
            "workers.html", workers=Worker.query.order_by(Worker.last_name).all()
        )

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
            flash(
                str(exc)
                if isinstance(exc, ValueError)
                else "Esiste già una tariffa con questa decorrenza",
                "error",
            )
        return redirect(url_for("workers"))

    @app.route("/calendar")
    @login_required
    def calendar():
        return render_template(
            "calendar.html", workers=Worker.query.order_by(Worker.last_name).all()
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
            entry = WorkEntry(
                worker_id=int(payload["worker_id"]),
                work_date=parse_date(payload["work_date"], "Data"),
                start_time=start_time,
                end_time=end_time,
                break_minutes=break_minutes,
                location=str(payload["location"]).strip()[:255],
                notes=payload.get("notes") or None,
            )
            if not entry.location:
                raise ValueError("Il luogo è obbligatorio")
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
            start_time = (
                parse_time(payload["start_time"], "Inizio")
                if payload.get("start_time")
                else e.start_time
            )
            end_time = (
                parse_time(payload["end_time"], "Fine") if payload.get("end_time") else e.end_time
            )
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
            start_date = parse_date(request.form["start_date"], "Dal")
            end_date = parse_date(request.form["end_date"], "Al")
            if end_date < start_date:
                raise ValueError("La data finale deve essere successiva o uguale a quella iniziale")
            absence = Absence(
                worker_id=int(request.form["worker_id"]),
                start_date=start_date,
                end_date=end_date,
                kind=request.form["kind"],
                paid="paid" in request.form,
                paid_hours=nonnegative_decimal(request.form.get("paid_hours"), "Ore pagate"),
                notes=request.form.get("notes") or None,
            )
            if absence.kind not in {"vacation", "sickness", "unpaid_leave"}:
                raise ValueError("Tipo assenza non valido")
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

    def get_summary(worker_id, year, month):
        if month not in range(1, 13) or year < 2000 or year > 2200:
            raise ValueError("Periodo non valido")
        factor = Setting.query.filter_by(key="tfr_divisor").first()
        return monthly_summary(
            WorkEntry.query.filter_by(worker_id=worker_id).all(),
            Absence.query.filter_by(worker_id=worker_id).all(),
            Expense.query.filter_by(worker_id=worker_id).all(),
            HourlyRate.query.filter_by(worker_id=worker_id).order_by(HourlyRate.valid_from).all(),
            year,
            month,
            nonnegative_decimal(factor.value if factor else "13.5", "Divisore TFR"),
        )

    @app.get("/reports")
    @login_required
    def reports():
        today = date.today()
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", today.year, type=int)
        month = request.args.get("month", today.month, type=int)
        try:
            summary = get_summary(worker_id, year, month) if worker_id else None
        except ValueError as exc:
            flash(str(exc), "error")
            summary = None
        return render_template(
            "reports.html",
            workers=Worker.query.all(),
            summary=summary,
            selected_worker=worker_id,
            year=year,
            month=month,
        )

    @app.get("/reports/payroll.pdf")
    @login_required
    def payroll():
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        if worker_id is None or year is None or month is None:
            abort(400)
        worker = db.get_or_404(Worker, worker_id)
        try:
            summary = get_summary(worker_id, year, month)
        except ValueError:
            abort(400)
        audit("payroll_downloaded", "worker", worker_id, f"{year}-{month:02d}")
        return send_file(
            payroll_pdf(worker, summary, year, month),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"colf-manager-payroll-{year}-{month:02d}.pdf",
        )

    return app


def main():
    create_app().run(
        host=os.getenv("COLF_MANAGER_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
