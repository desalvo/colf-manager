# Architecture

The browser talks to a Gunicorn-hosted Flask application. Flask-Login provides the authenticated session, SQLAlchemy persists workers, effective-dated rates, work entries, absences, expenses and document metadata in PostgreSQL, while uploaded bytes live on a separate persistent volume. ReportLab creates PDFs from server-side calculations.

Trust boundaries: HTTPS ingress, application session, database credentials and attachment storage. Health checks do not expose private data. The application container is non-root and stateless except for the mounted document directory; PostgreSQL and document backups must be coordinated.

Key entities: `Worker` owns `HourlyRate`, `WorkEntry`, `Absence`, `Expense` and `Document`. A rate is selected by the latest `valid_from` date not after a work/absence date. Monetary arithmetic uses `Decimal` and rounds to cents only at summarized boundaries.

## Delivery pipeline

Pull requests and `main` run tests on Python 3.11-3.13, security and dependency audits, container scanning, and Docker Compose/Kubernetes validation on GitHub-hosted `ubuntu-24.04` runners. A successful `main` pipeline publishes the multi-architecture image `desalvo/colf-manager:latest`. A signed `vX.Y.Z` tag matching `VERSION` publishes only `desalvo/colf-manager:X.Y.Z`, creates an SBOM and provenance attestations, and uploads the generated release artifacts to GitHub.

Docker Hub credentials are stored as `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets. The ASCII-armored release signing public key is stored as `RELEASE_GPG_PUBLIC_KEY`; private signing keys never enter GitHub Actions.
