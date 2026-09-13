# colf-manager 1.0.0

<img src="src/colf_manager/static/logo.svg" alt="colf-manager" width="180">

Web application for a private employer to record a domestic worker's hours, workplaces, effective-dated rates, leave, sickness, employer/worker advances, expenses, TFR accrual, documents and management reports.

## Quick start

```bash
cp .env.example .env
# replace EVERY sample value with real secrets
docker compose up -d --build
```

Open `http://localhost:8000`. The initial user is `admin`; its initial password is `COLF_MANAGER_ADMIN_PASSWORD` and must be changed on first login. Production mode refuses to start with missing or placeholder secrets.

For local HTTP Docker Compose keep `COLF_MANAGER_SECURE_COOKIES=0`; set it to `1` behind HTTPS/Ingress. Login is rate-limited, state-changing requests are CSRF-protected, and session cookies use HttpOnly/SameSite. Administrators can create additional users from the **Users** page.

The calendar supports direct entry and drag-and-drop rescheduling. Rates are effective-dated and unique per worker/effective date. Paid absences spanning months or rate changes are split across the applicable days. Worker advances increase the amount due as reimbursements; employer advances reduce it as recoveries.

Uploads are limited to PDF/JPEG/PNG and validate extension, MIME type and file signature while storing SHA-256 and size. Authentication, password changes, key business operations and document downloads are audit-logged.

## Database migrations

Flask-Migrate/Alembic is enabled. Databases created by the original 1.0.0 build receive a compatibility upgrade at startup without destructive recreation. After a backup and successful hardened deployment, establish the baseline with:

```bash
flask --app colf_manager.app:create_app db stamp 1000_hardened_baseline
```

All later schema changes should use reviewed Alembic revisions and `flask db upgrade`.

## Kubernetes

`kubernetes/colf-manager.yaml` includes TLS ingress, security contexts, resource limits, application/database/backup PVCs, PostgreSQL ingress restriction and a daily `pg_dump` CronJob with 14-day local retention. Replace all `CHANGE_ME` values and configure host, ingress class, TLS secret and optional `storageClassName` before deployment. See `kubernetes/README.md`.

## Quality and release

CI covers Python 3.11-3.13, Ruff, pytest with an 85% coverage gate, Bandit, pip-audit, gitleaks, Trivy, kubeconform, CodeQL, multi-architecture image builds, SBOM and provenance. `scripts/production-gate.sh` also validates the Alembic baseline.

## Production boundary

Payroll/TFR outputs are management-support documents. They do not submit INPS filings and do not replace official CU documents, professional payroll/legal advice or verification of the current domestic-work CCNL.

Documentation: [Italian README](README.it.md) · [Italian manual](docs/MANUAL.it.md) · [English manual](docs/MANUAL.en.md)

Author: Alessandro De Salvo · License: EUPL-1.2
