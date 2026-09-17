# colf-manager 1.0.0 · build r101-full

<img src="src/colf_manager/static/logo.svg" alt="colf-manager" width="180">

Web application for a private employer to record a domestic worker's hours, workplaces, effective-dated rates, vacation, sickness/permit hours, employer/worker advances, expenses, TFR accrual, documents and management reports.

### Calendar editor r71

The calendar entry dialog uses one paid/unpaid control and displays only the fields relevant to the selected type (ordinary/overtime, permit, sickness or vacation). Existing values are preserved when an event is opened for editing.

## Quick start

```bash
cp .env.example .env
# replace EVERY sample value with real secrets
docker compose up -d --build
```

Open `http://localhost:8000`. The initial user is `admin`; its initial password is `COLF_MANAGER_ADMIN_PASSWORD` and must be changed on first login. Production mode refuses to start with missing or placeholder secrets.

For local HTTP Docker Compose keep `COLF_MANAGER_SECURE_COOKIES=0`; set it to `1` behind HTTPS/Ingress. Login is rate-limited, state-changing requests are CSRF-protected, and session cookies use HttpOnly/SameSite. Flask-Login session protection defaults to `basic` to avoid false immediate logouts behind reverse proxies/Ingress; set `COLF_MANAGER_SESSION_PROTECTION=strong` only when the client identifier is stable. Administrators can create additional users from the **Users** page.

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


## Responsive mobile r45

The mobile/tablet UI uses a dedicated off-canvas navigation shell: the sidebar is hidden by default below 851 px and is available only through the hamburger control. Page content, forms, cards, reports and calendar panels stay inside the viewport; tables and time-grid calendar views use local contained scrolling where needed.


## Calendar subscriptions

From **Settings**, administrators can configure the external application URL and enable tokenized read-only subscriptions for a worker or employer. Each enabled calendar exposes an ICS feed and a CalDAV collection URL. Employer subscriptions aggregate events for associated workers. Tokens can be regenerated or revoked at any time.

### r55 - reports, signatures and payments
- PDF reports now show the application logo, version/build and author on every page, with refreshed professional styling and inline archive viewing.
- Optional worker/employer graphic signatures can be uploaded from their records (PNG, JPEG, TIFF, WEBP, BMP) and automatically embedded when signatures are requested.
- A Payments register supports manual entries and automatic residual tracking from generated reports: salary, INPS contributions, thirteenth-month salary, TFR, reimbursements and other payments, with status, payment method (Bank transfer by default, Card deposit, Cash or Other), date, period, notes and attachments.
- INPS contribution payments are available only when the worker has a recorded INPS position.
- Full export/import includes signatures, payments and payment attachments in addition to database, documents and reports.

### Manual expense/reimbursement settlements
Each expense creates a balance owed either to the employer or to the worker. Multiple partial settlements can be recorded, including cash with no attachment, or bank/card/other methods with optional evidence. The system tracks original amount, manually settled amount and remaining balance, and prevents over-settlement. The remaining balance can stay in the payroll for the expense month, be carried forward in full to a later month, or be split into installments by installment count or amount. Manual settlements remain possible in later months when a carry-forward/installment plan exists and reduce future open quotas. Quotas already included in generated payroll are locked to prevent duplicate reimbursement. For example, a EUR 120 expense settled by EUR 40 and then EUR 30 leaves EUR 50 for payroll.

### Hour types and vacation (r60)
- **Ordinary hours**: paid by default; they may be marked unpaid.
- **Overtime hours**: paid by default; they use the effective hourly rate or a per-entry override.
- **Sickness**: from r62 it is handled exclusively in calendar days with the restored sickness label.
- **Permit hours**: paid by default and may be marked unpaid.
- **Vacation**: always recorded and reported in days, never as an hour type.


### Permit categories and live-in status (r61)
- worker profile tracks live-in status, reduced live-in schedule under CCNL art. 14(2), and relevant union-office status;
- CCNL permit categories cover medical visits, residence-permit renewal, family reunification, certified severe-disability family care, bereavement, childbirth for fathers, professional training, Ebincolf training and union leave;
- `Other` is available for unpaid permits;
- effective-dated rules distinguish the previous CCNL from the 2025-2028 CCNL;
- art. 19 shared paid-hours bank is computed from live-in status and contractual weekly hours;
- overview and relevant reports show monthly/yearly usage, entitlement and remaining balances.


### Sickness days and employer-favour treatment (r62)
- Sickness is always expressed in calendar days, without clock times.
- Effective-dated rules encode job-protection and paid-sickness ceilings; the first three consecutive days are paid at 50%, from day four at 100%.
- The employer may voluntarily pay sickness or permit time beyond the contractual ceiling, tracked separately from the legal entitlement.
- Every overview indicator has an icon; limited indicators use threshold-aware visual states.

### r74
Report annuale complessivo dei pagamenti effettuati, totali pagati per categoria, annullamento regolamento spese da cedolino e firme PDF con fondo bianco trasparente.

- r99: archived reports can be regenerated and replaced in place using the graphical ↻ action while preserving the same archive record.

### PDF reports - layout and final notes

PDF reports keep section headings with their related content on the same page whenever possible, show `Page X of Y`/`Pagina X di Y`, and end with compact calculation/legal/privacy notes followed by place, date and worker signature. An uploaded worker signature is inserted automatically.
