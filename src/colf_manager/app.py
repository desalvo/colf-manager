import os
import secrets
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_login import LoginManager, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from .calculations import monthly_summary
from .models import Absence, Document, Expense, HourlyRate, Setting, User, WorkEntry, Worker, db
from .reporting import payroll_pdf


def create_app(test_config=None):
    app = Flask(__name__)
    data_dir = Path(os.getenv("COLF_MANAGER_DATA", "/data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    app.config.update(
        SECRET_KEY=os.getenv("COLF_MANAGER_SECRET_KEY", secrets.token_hex(32)),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL", f"sqlite:///{data_dir / 'colf-manager.db'}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        UPLOAD_FOLDER=str(data_dir / "documents"),
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    login = LoginManager(app)
    login.login_view = "login"

    @login.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()
        if not User.query.first():
            password = os.getenv("COLF_MANAGER_ADMIN_PASSWORD", "change-me-now")
            db.session.add(
                User(
                    username=os.getenv("COLF_MANAGER_ADMIN_USER", "admin"),
                    password_hash=generate_password_hash(password),
                )
            )
            db.session.commit()

    @app.get("/healthz")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.route("/login", methods=["GET", "POST"])
    def login_view():
        if request.method == "POST":
            user = User.query.filter_by(username=request.form["username"]).first()
            if user and check_password_hash(user.password_hash, request.form["password"]):
                login_user(user)
                return redirect(url_for("dashboard"))
            flash("Credenziali non valide", "error")
        return render_template("login.html")

    app.add_url_rule("/login", "login", login_view, methods=["GET", "POST"])

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

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
            w = Worker(
                first_name=request.form["first_name"],
                last_name=request.form["last_name"],
                fiscal_code=request.form.get("fiscal_code"),
                inps_number=request.form.get("inps_number"),
                employment_start=date.fromisoformat(request.form["employment_start"]),
                weekly_hours=request.form.get("weekly_hours") or 0,
            )
            db.session.add(w)
            db.session.flush()
            if request.form.get("hourly_rate"):
                db.session.add(
                    HourlyRate(
                        worker_id=w.id,
                        valid_from=w.employment_start,
                        amount=request.form["hourly_rate"],
                    )
                )
            db.session.commit()
            flash("Lavoratrice registrata", "success")
            return redirect(url_for("workers"))
        return render_template(
            "workers.html", workers=Worker.query.order_by(Worker.last_name).all()
        )

    @app.post("/rates")
    @login_required
    def rates():
        db.session.add(
            HourlyRate(
                worker_id=int(request.form["worker_id"]),
                valid_from=date.fromisoformat(request.form["valid_from"]),
                amount=request.form["amount"],
                notes=request.form.get("notes"),
            )
        )
        db.session.commit()
        flash("Tariffa aggiornata", "success")
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
                "title": f"{e.location} · {e.hours}h",
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
        payload = request.get_json() if request.is_json else request.form
        entry = WorkEntry(
            worker_id=int(payload["worker_id"]),
            work_date=date.fromisoformat(payload["work_date"]),
            start_time=datetime.strptime(payload["start_time"], "%H:%M").time(),
            end_time=datetime.strptime(payload["end_time"], "%H:%M").time(),
            break_minutes=int(payload.get("break_minutes", 0)),
            location=payload["location"],
            notes=payload.get("notes"),
        )
        if entry.end_time <= entry.start_time:
            return jsonify({"error": "end_time must follow start_time"}), 400
        db.session.add(entry)
        db.session.commit()
        return jsonify({"id": entry.id}), 201

    @app.patch("/api/work/<int:entry_id>")
    @login_required
    def move_work(entry_id):
        e = db.get_or_404(WorkEntry, entry_id)
        payload = request.get_json()
        e.work_date = date.fromisoformat(payload["work_date"])
        if payload.get("start_time"):
            e.start_time = datetime.strptime(payload["start_time"], "%H:%M").time()
        if payload.get("end_time"):
            e.end_time = datetime.strptime(payload["end_time"], "%H:%M").time()
        db.session.commit()
        return {"ok": True}

    @app.post("/absences")
    @login_required
    def absences():
        db.session.add(
            Absence(
                worker_id=int(request.form["worker_id"]),
                start_date=date.fromisoformat(request.form["start_date"]),
                end_date=date.fromisoformat(request.form["end_date"]),
                kind=request.form["kind"],
                paid="paid" in request.form,
                paid_hours=request.form.get("paid_hours") or 0,
                notes=request.form.get("notes"),
            )
        )
        db.session.commit()
        flash("Assenza registrata", "success")
        return redirect(url_for("calendar"))

    @app.route("/expenses", methods=["GET", "POST"])
    @login_required
    def expenses():
        if request.method == "POST":
            db.session.add(
                Expense(
                    worker_id=int(request.form["worker_id"]),
                    expense_date=date.fromisoformat(request.form["expense_date"]),
                    description=request.form["description"],
                    amount=request.form["amount"],
                    direction=request.form["direction"],
                )
            )
            db.session.commit()
            flash("Spesa registrata", "success")
            return redirect(url_for("expenses"))
        return render_template(
            "expenses.html",
            workers=Worker.query.all(),
            expenses=Expense.query.order_by(Expense.expense_date.desc()).all(),
        )

    @app.route("/documents", methods=["GET", "POST"])
    @login_required
    def documents():
        if request.method == "POST":
            f = request.files["file"]
            safe = secure_filename(f.filename)
            stored = f"{uuid4().hex}-{safe}"
            f.save(Path(app.config["UPLOAD_FOLDER"]) / stored)
            db.session.add(
                Document(
                    worker_id=int(request.form["worker_id"]),
                    filename=safe,
                    stored_name=stored,
                    category=request.form.get("category", "other"),
                )
            )
            db.session.commit()
            return redirect(url_for("documents"))
        return render_template(
            "documents.html",
            workers=Worker.query.all(),
            documents=Document.query.order_by(Document.uploaded_at.desc()).all(),
        )

    @app.get("/documents/<int:document_id>")
    @login_required
    def download_document(document_id):
        d = db.get_or_404(Document, document_id)
        return send_from_directory(
            app.config["UPLOAD_FOLDER"], d.stored_name, as_attachment=True, download_name=d.filename
        )

    def get_summary(worker_id, year, month):
        factor = Setting.query.filter_by(key="tfr_divisor").first()
        return monthly_summary(
            WorkEntry.query.filter_by(worker_id=worker_id).all(),
            Absence.query.filter_by(worker_id=worker_id).all(),
            Expense.query.filter_by(worker_id=worker_id).all(),
            HourlyRate.query.filter_by(worker_id=worker_id).order_by(HourlyRate.valid_from).all(),
            year,
            month,
            __import__("decimal").Decimal(factor.value if factor else "13.5"),
        )

    @app.get("/reports")
    @login_required
    def reports():
        today = date.today()
        worker_id = request.args.get("worker_id", type=int)
        year = request.args.get("year", today.year, type=int)
        month = request.args.get("month", today.month, type=int)
        summary = get_summary(worker_id, year, month) if worker_id else None
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
        worker = db.get_or_404(Worker, worker_id)
        return send_file(
            payroll_pdf(worker, get_summary(worker_id, year, month), year, month),
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
