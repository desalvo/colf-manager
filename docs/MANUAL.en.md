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

Records are personal data and may include sickness-related information. Use HTTPS, least privilege, encrypted storage/backups, documented retention and data minimization. Avoid entering medical diagnoses. The supplied container runs unprivileged with a read-only root filesystem and no Linux capabilities.

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

## r57: settlements, carry-forward and installments for expenses and reimbursements

Each expense or advance keeps a balance. Multiple partial settlements can be recorded by cash, bank transfer, card, another electronic method or another method. Evidence is optional: a cash settlement may exist as an auditable record without a receipt, while still retaining date, amount, method, notes and audit history. The system blocks settlement beyond the still-available balance.

The remaining balance can stay in payroll for the expense month, be carried forward in full to a later month, or be split across multiple months. Installments can be defined by installment count or fixed installment amount; the last installment automatically absorbs any remainder. When a carry-forward/installment plan exists, later manual settlements are allowed and reduce future still-open quotas.

When monthly payroll is generated, the quota included in that payroll is consolidated. Consolidated quotas cannot be settled or rewritten a second time; only future unconsolidated quotas remain editable and can be rescheduled. Reports distinguish original amount, manual settlements, amounts already allocated through payroll and the remaining open balance.

The **Settings** page (gear icon) centralises the recent-pattern limit, SMTP/SMTPS configuration and available authentication methods. Notifications, stored documents and archived reports can be sent by e-mail directly from the application.


Local packaged photographic assets are bundled in `src/colf_manager/static/heroes/`.


## r32: report approvals and signatures
Reports may include an approval section for the worker, employer, both, or no signer. Names are prefilled automatically. Place and date can be edited before generation; the proposed date is the report generation date. Signature information is embedded in the archived PDF. Local hero and photographic assets remain bundled under `src/colf_manager/static/heroes/`.

## Calendar: ordinary hours, overtime, sickness, permits and vacation

From r62 the calendar distinguishes **Ordinary hours**, **Overtime hours**, **Sickness**, **Permit hours** and **Vacation**. Ordinary and overtime hours are paid by default but may be marked unpaid. Overtime automatically uses the hourly rate effective on the entry date; an optional rate may be supplied for that entry only. Sickness and permit hours are paid by default and can also be marked unpaid. Vacation is not an hour type: it is recorded, displayed and reported exclusively in **days**, without start/end clock times.

## r42: drag and drop and hours trend by location

Recent calendar entries are displayed in a dedicated right-side column as graphical draggable pills. Dropping one onto a new day preserves the entry type, original start/end times, worker, employer relationship, location and break; vacation and sickness items also preserve paid status and configured paid hours. Event colors are kept consistent across month, week and day views.

On the Reports page, the worker is selected automatically when only one worker exists. A new **Hours trend by location** PDF is also available, with annual totals and monthly paid-work-hour breakdowns by location.

### Sickness indicators on the Dashboard

For the selected month, the Dashboard shows recorded paid and unpaid sickness hours. It also shows the remaining annual paid-sickness entitlement. The domestic-work collective agreement expresses the ceiling in days (8, 10 or 15 depending on seniority); the application converts the remaining entitlement to hours using weekly hours divided by 6. For periods outside the verified contractual rules the value is shown as N/A.


## r47: addresses, dashboard and export

Workers and employers now include City, Province and Postal Code. Report signature place defaults to the employer city. The Dashboard uses a more compact KPI layout and the Period activity section, now including the worker name, is collapsed by default. Full export explicitly supports time values (`datetime.time`) used by calendar entries.


## r48: calendar subscriptions and settings

**Settings** now includes the external application URL and read-only calendar subscriptions for individual workers or employers. Each enabled calendar exposes a token-protected **ICS** link and **CalDAV** endpoint; employer calendars aggregate events for their associated workers. Feeds include ordinary hours, overtime, sickness, permits and day-based vacation. Personal password changes are now integrated into Settings.

## Graphic signatures in reports
Worker and employer records can store a graphic signature in PNG, JPEG, TIFF, WEBP or BMP format. When a report requires that party's signature and a signature is registered, the image is automatically placed in the signature area; otherwise a manual signature line is shown. Every PDF also carries the colf-manager logo, version/build and author.

## Payments and receipts
The Payments section records salary payments, INPS contributions, thirteenth-month salary, TFR, expense reimbursements and other payments. Each record can be Pending or Paid and can include payment date, reference period, description, notes and supporting attachments such as PDF receipts or images. INPS contribution payments are available only for workers with an INPS position recorded.

Generating a monthly payslip automatically creates a residual Pending salary item and, when an INPS calculation is available, a contribution item. Amounts already recorded as Paid are shown in reports and reduce the displayed residual. Regenerating a report updates the automatic residual item instead of creating uncontrolled duplicates.

## Report archive and backup
After generating a report from the UI, the Reports page refreshes automatically and the new document is immediately visible in the archive. Archived reports can be viewed in the browser, downloaded, emailed or deleted. Full export includes the database, documents, reports, graphic signatures, payments and payment attachments; full import restores the same content and relationships.


## r60: complete hour-type model

Work records now distinguish ordinary and overtime hours. Each record has a paid/unpaid flag and defaults to paid. Overtime uses the effective hourly rate, with an optional override that applies only to that record. Summaries and payslips distinguish total hours, ordinary hours, overtime hours and unpaid work hours.

The former Sickness entry is renamed **Sickness** and new sickness records are paid by default. **Permit hours** are added as a separate type, also paid by default and optionally unpaid. Existing Sickness data is migrated to Sickness.

**Vacation** remains a day-based entitlement: the UI does not request clock times, the calendar renders vacation as day events, and reports/dashboard always expose vacation in days. Any internal conversion needed for monetary calculation is not presented as a vacation-hour balance.


## r61: contract-based permit categories

The worker profile now records **live-in** status and, where applicable, the reduced live-in schedule under CCNL art. 14(2). A relevant union-office flag is also available for union leave eligibility.

Permit categories cover documented medical visits, residence-permit renewal, family reunification, certified severe-disability family care, bereavement/family misfortune, childbirth for fathers, professional training, Ebincolf training and union leave. **Other** is also available for unpaid permits.

Rules are effective-dated. Under the CCNL effective from 1 November 2025 the shared art. 19 paid bank is 16 hours/year for live-in workers, 12 hours for art. 14(2) reduced live-in arrangements, 12 hours for non-live-in workers working at least 30 hours/week, and proportionally reduced below 30 hours/week. Medical visits, residence-permit renewal, family reunification and certified severe-disability family care share this bank. Professional training requires full-time permanent employment and at least 6 months' seniority under the 2025-2028 CCNL; the earlier period uses the previous 12-month requirement.

Bereavement and childbirth are event-based rights and are not misrepresented as annual banks. The overview shows paid/unpaid monthly and yearly usage, available entitlement, annual total where legally defined, and remaining balances in collapsed-by-default sections. Relevant monthly, annual and trend reports include the same permit information.


## r62: sickness in days and visual indicators

Sickness is now recorded exclusively in calendar days, with no clock times. The engine selects the contractual rule effective on the recorded date: job-protection limits and paid-sickness limits are kept separate, with 50% through the third consecutive day and 100% from the fourth day. The employer may authorize more favourable treatment and pay sickness days or permit hours beyond the contractual ceiling; the excess remains separate from the legal/contractual residual entitlement. Every overview indicator has an icon and limited indicators use a visual threshold state.

## Payments, expenses and signatures in reports

Reports distinguish accrued/recorded amounts from payments actually made. The annual summary shows paid amounts by category (salary, INPS contributions, thirteenth salary, TFR, expense reimbursement and other) and as a grand total. The "Payments made during the year" report includes all payments with Paid status and a payment date in the selected year, with worker, employer, category, amount and period details.

A cost allocation already consolidated through payroll can be returned to planned status with "Cancel payroll settlement" from the expense detail page. Deleting a payment immediately removes that amount from paid totals and from subsequently generated reports.

When a graphical worker or employer signature is available, PDFs make the white image background transparent, preserve proportions and center the signature in its field.
