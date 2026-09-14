# colf-manager 1.0.0 · build r40-full

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

Kubernetes resources are split into independent application, database, PVC, Secret, backup, NetworkPolicy and Ingress manifests. Deleting the application or database workload does not delete its PVCs, and the application PVC can be removed independently from PostgreSQL storage. Configure the two Secret manifests and storage settings before deployment. See `kubernetes/README.md`.

## Workers, employers, leave and reports

Workers and private household employers have complete create/view/edit/delete pages, including optional address, phone and e-mail. Workers can be linked to an employer and can optionally use projected vacation entitlement through 31 December before it has fully accrued. The application calculates accrued/projected vacation, automatic vacation paid hours, estimated thirteenth-month accrual and annual TFR quota. PDF outputs include monthly payroll, annual payroll, courtesy annual income certification, annual TFR and a monthly hours/pay trend report.

## Quality and release

CI covers Python 3.11-3.13, Ruff, pytest with an 85% coverage gate, Bandit, pip-audit, gitleaks, Trivy, kubeconform, CodeQL, multi-architecture image builds, SBOM and provenance. `scripts/production-gate.sh` also validates the Alembic baseline.

## Production boundary

Payroll/TFR outputs are management-support documents. They do not submit INPS filings and do not replace official CU documents, professional payroll/legal advice or verification of the current domestic-work CCNL.

Documentation: [Italian README](README.it.md) · [Italian manual](docs/MANUAL.it.md) · [English manual](docs/MANUAL.en.md)

Author: Alessandro De Salvo · License: EUPL-1.2

## r19 reports

A dedicated thirteenth-salary payslip and a combined thirteenth salary + TFR report are included. When INPS position and contract number are available, reports add estimated INPS contributions and a clearly separated tax estimate.


## Locations

Work locations have dedicated create, view, edit and delete management. The calendar uses registered locations; historical work entries retain the location snapshot even if the location record is later edited or deleted.


## Archive, reports and full backup

Generated PDF reports are persisted on application storage and can be downloaded again or manually deleted. Uploaded documents can also be manually deleted. Administrators can create a complete ZIP export containing application database rows, referenced documents and archived reports, and can perform a confirmed full restore. Files present on storage but no longer referenced by the database are automatically removed by the maintenance service after the configured retention period.

The Dashboard can be viewed for a selected month and year. The calendar supports navigation to prior months and retroactive work-entry creation in the displayed period.

## PostgreSQL 18.6

r29 uses `postgres:18.6-alpine`. Existing PostgreSQL 17 installations require a supported major-version migration; see `POSTGRESQL-18-UPGRADE.md` before changing the database workload or PVC.


Local packaged photographic assets are bundled in `src/colf_manager/static/heroes/`.
