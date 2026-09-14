# colf-manager 1.0.0 - English manual

## Purpose

colf-manager centralizes a private household employment relationship and retains an auditable history of hours, workplaces, effective-dated rates, leave, expenses and documents.

## Features

- historical monthly calendar with drag-and-drop rescheduling;
- multiple work intervals per day and a workplace for each interval;
- effective-dated hourly rates without rewriting past reports;
- paid vacation, unpaid leave and paid/unpaid sickness;
- advances and reimbursements in either direction;
- worker details, tax identifier, start date and optional INPS reference;
- persistent document archive;
- monthly summaries and data suitable for quarterly, half-year, annual and custom periods;
- PDF payroll support statement and estimated TFR accrual.

## Docker installation

Install Docker with Compose, copy `.env.example` to `.env`, generate three strong secrets, then run `docker compose up -d --build`. Back up PostgreSQL with `pg_dump` and include the attachment volume.

## Kubernetes

Kubernetes resources are split by responsibility. Configure `secret-database.yaml` and `secret-application.yaml`, then apply namespace, PVCs, database, application, backup, network policy and ingress. Deleting `application.yaml` preserves `app-data`; deleting `database.yaml` preserves `postgres-data` and `backup-data`. `pvc-application.yaml` can be deleted independently without touching database storage. See `kubernetes/README.md`.

## Workflow

Create the worker and initial hourly rate, add work from the calendar, drag an event to reschedule it, record leave and its paid hours, then add expenses and supporting documents. The Reports page calculates the selected month and creates a payroll support PDF.

## TFR and compliance boundary

The management accrual uses a configurable divisor, initially 13.5, on recorded gross pay. Actual settlement can require revaluation, different pay-item treatment and taxation. Domestic-work rules and INPS contribution tables change; always verify official sources and the applicable contract.

## Security and privacy

Records are personal data and may include health-related information. Use HTTPS, least privilege, encrypted storage/backups, documented retention and data minimization. Avoid entering medical diagnoses. The supplied container runs unprivileged with a read-only root filesystem and no Linux capabilities.

## Build and release

`scripts/release-check.sh` runs lint, tests/coverage, Bandit, dependency auditing, EN/IT PDF generation, wheel/sdist, `twine check`, CycloneDX SBOM and package verification. GitHub gates use Python 3.11-3.13, secret scanning, CodeQL, Docker Compose/Kubernetes validation, multi-architecture image builds, Trivy and provenance attestation.

## Records and complete deletion

Workers and household employers can be created, viewed, edited and permanently deleted. Address, phone and e-mail are optional. Permanently deleting a worker also deletes linked time entries, absences, rates, expenses and documents; deleting an employer unlinks workers without deleting them.

## Automatic vacation entitlement

The engine uses 26 working days per year and monthly twelfths. A service fraction of at least 15 calendar days counts as a full month. Vacation days are counted Monday through Saturday excluding Sundays and Italian national holidays; local patron-saint holidays must be checked separately. For hourly workers, paid vacation hours use average monthly hours divided by 26. Each worker can optionally use vacation that is projected to accrue by 31 December before it has fully accrued.

## TFR and annual reports

For relationships from 1990 onward, the annual TFR report uses recorded useful compensation, includes estimated thirteenth-month accrual and divides by 13.5. The current-year quota is not revalued; prior accrued balances require the statutory article 2120 revaluation (1.5% fixed plus 75% of the December-to-December ISTAT FOI increase). PDF outputs include monthly payroll, annual payroll, courtesy annual income certification, annual TFR and monthly hours/pay trend. Rules for 2025 and 2026 are marked as verified in this package; other years explicitly require checking official sources.

## Courtesy CU / income certification

A private household employer is normally not an Italian withholding agent. The generated PDF is therefore a courtesy income certification based on recorded data and is not the electronic Certificazione Unica filed by a withholding agent.

## Limitations

The software does not replace a payroll professional, submit statutory filings or guarantee that user-supplied parameters satisfy current law.

## Thirteenth salary, TFR and contributions

Reports include a dedicated thirteenth-salary payslip and a combined thirteenth salary + TFR statement with formulas and period details. When INPS position and contract number are recorded, PDFs add estimated INPS contributions and a separately identified indicative IRPEF calculation.


## Locations

The **Locations** section lets users create, view, edit and delete work locations. Each location has a name, optional address and notes. New calendar work entries can select a registered location. To preserve history, each work entry also stores a textual snapshot: editing or deleting the location record does not rewrite past work entries.


## Archive, reports and full backup

Generated PDF reports are persisted on application storage and can be downloaded again or manually deleted. Uploaded documents can also be manually deleted. Administrators can create a complete ZIP export containing application database rows, referenced documents and archived reports, and can perform a confirmed full restore. Files present on storage but no longer referenced by the database are automatically removed by the maintenance service after the configured retention period.

The Dashboard can be viewed for a selected month and year. The calendar supports navigation to prior months and retroactive work-entry creation in the displayed period.

## r31: interface, calendar, e-mail and settings

The vertical navigation remains available on desktop, including the calendar, and can be collapsed to an icon rail. On phones and tablets it becomes an accessible drawer that can be dismissed by tapping outside it.

The calendar uses a weekly time-grid: every work entry is visually proportional to its duration. Colours are derived from the worker, employer and location combination. Entries can be edited, resized, moved or deleted directly from the calendar. The right rail shows the latest reusable entry patterns (default 10, configurable) and supports drag-and-drop to create new work entries.

Hourly rates and expenses have complete history management with create, edit and delete operations. Worker/employer expenses are included in payroll reports for the month in which they were recorded.

The **Settings** page (gear icon) centralises the recent-pattern limit, SMTP/SMTPS configuration and available authentication methods. Notifications, stored documents and archived reports can be sent by e-mail directly from the application.


Local packaged photographic assets are bundled in `src/colf_manager/static/heroes/`.


## r32: report approvals and signatures
Reports may include an approval section for the worker, employer, both, or no signer. Names are prefilled automatically. Place and date can be edited before generation; the proposed date is the report generation date. Signature information is embedded in the archived PDF. Local hero and photographic assets remain bundled under `src/colf_manager/static/heroes/`.

## Calendar: paid work, vacation and sickness

From r37 the same calendar dialog lets the user select **Paid work**, **Vacation** or **Sickness**. Vacation and sickness are stored as timed intervals and may coexist on the same day with paid work. For multi-day periods, both the start and end dates are always included. Vacation and sickness use dedicated colors, while paid work keeps a stable color determined by the employer/worker/location combination. Clicking an interval allows it to be viewed, edited or deleted.

## r40: drag and drop and hours trend by location

Recent calendar entries are displayed in a dedicated right-side column as graphical draggable pills. Dropping one onto a new day preserves the entry type, original start/end times, worker, employer relationship, location and break; vacation and sickness items also preserve paid status and configured paid hours. Event colors are kept consistent across month, week and day views.

On the Reports page, the worker is selected automatically when only one worker exists. A new **Hours trend by location** PDF is also available, with annual totals and monthly paid-work-hour breakdowns by location.
