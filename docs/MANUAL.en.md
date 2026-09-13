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

## Web interface

The colf-manager logo identifies navigation, login and both manuals. Login, dashboard, calendar, worker profile, expenses, documents and reports use distinct realistic photography, high-contrast overlays and responsive focal points. Below 850 px, navigation becomes a mobile drawer with a dimmed backdrop; tables and calendar remain scrollable and forms collapse to one column.

## Docker installation

Install Docker with Compose, copy `.env.example` to `.env`, generate three strong secrets, then run `docker compose up -d --build`. Back up PostgreSQL with `pg_dump` and include the attachment volume.

## Kubernetes

Replace all `CHANGE_ME` values and configure hostname, ingress class, StorageClass and PVC sizes. Run `kubectl apply -f kubernetes/colf-manager.yaml`. Production deployments should add TLS, NetworkPolicy, a secret manager, tested backups and an image pinned by digest.

## Workflow

Create the worker and initial hourly rate, add work from the calendar, drag an event to reschedule it, record leave and its paid hours, then add expenses and supporting documents. The Reports page calculates the selected month and creates a payroll support PDF.

## TFR and compliance boundary

The management accrual uses a configurable divisor, initially 13.5, on recorded gross pay. Actual settlement can require revaluation, different pay-item treatment and taxation. Domestic-work rules and INPS contribution tables change; always verify official sources and the applicable contract.

The annual statement is a documentary equivalent for record keeping. It is not an electronically filed Italian Certificazione Unica.

## Security and privacy

Records are personal data and may include health-related information. Use HTTPS, least privilege, encrypted storage/backups, documented retention and data minimization. Avoid entering medical diagnoses. The supplied container runs unprivileged with a read-only root filesystem and no Linux capabilities.

## Build and release

`scripts/release-check.sh` runs lint, tests/coverage, Bandit, dependency auditing, EN/IT PDF generation, wheel/sdist, `twine check`, CycloneDX SBOM and package verification. `scripts/build-package.sh` emits ZIP, TAR.GZ and SHA-256 files with a UTC `YYYYMMDD-HHMM` build ID. The `v1.0.0` tag must match both `VERSION` and `pyproject.toml`.

GitHub gates use explicit `ubuntu-24.04` runners, Python 3.11-3.13, secret scanning, CodeQL, Docker Compose/Kubernetes validation, multi-architecture image builds, Trivy and provenance attestation. `scripts/production-gate.sh` also emits `dist/production-evidence.json`.

Configure the repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` before publishing `main`; its workflow produces `desalvo/colf-manager:latest` only after every gate passes. For a release, also configure `RELEASE_GPG_PUBLIC_KEY` with the ASCII-armored public key, then create a signed `vX.Y.Z` tag. The workflow verifies its signature and match with `VERSION`, publishes only `desalvo/colf-manager:X.Y.Z`, and creates the GitHub Release.

## Limitations

The software does not replace a payroll professional, submit statutory filings or guarantee that user-supplied parameters satisfy current law.
