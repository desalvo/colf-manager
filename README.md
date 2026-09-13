# colf-manager 1.0.0

![colf-manager](src/colf_manager/static/logo.svg)

Web application for a private employer to record a domestic worker's hours, workplaces, historical hourly rates, paid vacation, unpaid leave, paid/unpaid sickness, employer/worker advances, expenses, TFR accrual, documents and management reports.

Italian documentation: [README.it.md](README.it.md) · [Manuale](docs/MANUAL.it.md) · [English manual](docs/MANUAL.en.md)

## Quick start

```bash
cp .env.example .env
# replace every sample secret
docker compose up -d --build
```

Open `http://localhost:8000`. The initial user is `admin`; the password is the value of `COLF_MANAGER_ADMIN_PASSWORD` at first start.

The calendar supports direct entry and drag-and-drop rescheduling. Hourly rates are effective-dated, so historical reports keep the correct rate. PostgreSQL stores structured data; the application volume stores uploaded documents.

The responsive photographic interface uses distinct imagery for login, dashboard, calendar, worker profile, expenses, documents and reports. The logo is shown in the application and both PDF manuals.

`scripts/production-gate.sh` emits reviewable evidence. GitHub Actions runs Python 3.11-3.13, CodeQL, secret scanning, manifest validation, multi-architecture image builds, Trivy, SBOM and provenance attestation on explicit `ubuntu-24.04` runners.

## Production boundary

colf-manager is a management and calculation-support tool. Its payroll and annual certificate are editable support statements, not automatic INPS filings, an official Certificazione Unica, or professional legal/payroll advice. Before payment or filing, verify the current domestic-work CCNL, INPS contribution tables, tax rules and the worker's specific contract.

## Deployment and release

- Docker Compose: `docker-compose.yml`
- Kubernetes: `kubernetes/colf-manager.yaml`
- stable image from `main`: `desalvo/colf-manager:latest`
- release image: `desalvo/colf-manager:1.0.0`
- full release gate: `scripts/release-check.sh`
- packages: `scripts/build-package.sh`
- release: push a signed `v1.0.0` tag after CI passes

Before the first push, configure the GitHub Actions secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. Before the first release tag, also configure `RELEASE_GPG_PUBLIC_KEY` with the ASCII-armored public key used to sign the tag. The `main` branch publishes only `latest`; `vX.Y.Z` tags publish only their matching `X.Y.Z` image.

Docker Compose uses `latest` by default. To pin a release, run `COLF_MANAGER_IMAGE_TAG=1.0.0 docker compose up -d`.

Manuals: [Italian source](docs/MANUAL.it.md) · [Italian PDF](output/pdf/colf-manager-manual-v1.0.0-it.pdf) · [English source](docs/MANUAL.en.md) · [English PDF](output/pdf/colf-manager-manual-v1.0.0-en.pdf)

Author: Alessandro De Salvo <braket71@gmail.com>  
License: EUPL-1.2
