# Architecture

The browser talks to a Gunicorn-hosted Flask application. Flask-Login provides the authenticated session, SQLAlchemy persists workers, effective-dated rates, work entries, absences, expenses and document metadata in PostgreSQL, while uploaded bytes live on a separate persistent volume. ReportLab creates PDFs from server-side calculations.

Trust boundaries: HTTPS ingress, application session, database credentials and attachment storage. Health checks do not expose private data. The application container is non-root and stateless except for the mounted document directory; PostgreSQL and document backups must be coordinated.

Key entities: `Worker` owns `HourlyRate`, `WorkEntry`, `Absence`, `Expense` and `Document`. A rate is selected by the latest `valid_from` date not after a work/absence date. Monetary arithmetic uses `Decimal` and rounds to cents only at summarized boundaries.

## Kubernetes layout

Application workload, PostgreSQL workload, application PVCs, database/backup PVCs and application/database Secrets are deliberately kept in separate manifests. Removing a workload never removes its storage. Application storage can be destroyed independently from PostgreSQL storage.

## Delivery pipeline

Pull requests and `main` run tests on Python 3.11-3.13, security and dependency audits, container scanning, and Docker Compose/Kubernetes validation on GitHub-hosted `ubuntu-24.04` runners. A successful `main` pipeline publishes the multi-architecture image `desalvo/colf-manager:latest`. A signed `vX.Y.Z` tag matching `VERSION` publishes only `desalvo/colf-manager:X.Y.Z`, creates an SBOM and provenance attestations, and uploads the generated release artifacts to GitHub.


## Managed locations

`Location` stores reusable work places (name, optional address and notes). `WorkEntry.location_id` links new entries to the managed record, while the existing `WorkEntry.location` string remains an immutable historical snapshot. Deleting a location sets the relation to null and does not rewrite or delete historical work entries.


## Archive, reports and full backup

Generated PDF reports are persisted on application storage and can be downloaded again or manually deleted. Uploaded documents can also be manually deleted. Administrators can create a complete ZIP export containing application database rows, referenced documents and archived reports, and can perform a confirmed full restore. Files present on storage but no longer referenced by the database are automatically removed by the maintenance service after the configured retention period.

The Dashboard can be viewed for a selected month and year. The calendar supports navigation to prior months and retroactive work-entry creation in the displayed period.
