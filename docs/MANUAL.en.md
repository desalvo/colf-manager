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

## Limitations

The software does not replace a payroll professional, submit statutory filings or guarantee that user-supplied parameters satisfy current law.
