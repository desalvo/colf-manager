# Changelog

## 1.0.0 - 2026-09-13

- Hardened overlay r3: self-normalizing local checks, validation test coverage, and environment-independent Docker Compose validation.

- Initial production release: worker registry, effective-dated rates, work calendar and drag/drop, absence and expense tracking, documents, payroll support PDF, TFR estimate, Docker/Kubernetes, bilingual documentation and release controls.
- Production hardening: CSRF, secure session defaults, login rate limiting, mandatory non-placeholder secrets, forced initial password change, admin user creation and audit logging.
- Corrected expense direction semantics and paid-absence allocation across month/rate boundaries; added validation and unique effective-date protection for rates.
- Hardened uploads with extension/MIME/signature checks, SHA-256 and file size metadata.
- Added Flask-Migrate/Alembic baseline, broader test coverage with an 85% gate, TLS/backup/network-policy Kubernetes improvements and configurable runtime hardening.

### Verification tooling fix (overlay r6)
- Require Twine 7.x because Hatchling may emit Core Metadata 2.5; Twine 6.x rejects metadata 2.5.
- Production gate now fails early with the installed Twine version before validating distributions.

- r6: Flask-Limiter 4.1.1+ resolves Rich/Twine 7 dependency conflict; clean-venv verification flow.

## r13-full - 2026-09-14

- Full self-contained repository package (no incremental overlay dependency).
- Split Kubernetes application and database workloads.
- Split application and database Secrets.
- Split application PVC from PostgreSQL/backup PVCs.
- Independent workload and storage deletion scripts.
- Updated kubeconform CI validation for split manifests.
- Production gate evidence updated to r13-full.

## r14-full - 2026-09-14

- Fixed concurrent database bootstrap under multi-worker Gunicorn.
- PostgreSQL schema/bootstrap is serialized with an application-specific advisory lock.
- `create_all`, legacy compatibility updates and initial admin creation now run inside the serialized bootstrap section.
- Prevents concurrent `CREATE TABLE "user"` and `pg_type_typname_nsp_index` duplicate-key failures on fresh Docker/Podman/Kubernetes starts.
- Full self-contained repository package.


## r15-full - 2026-09-14

- Fix PostgreSQL bootstrap visibility after schema creation.
- Commit transactional DDL created on the advisory-lock connection before compatibility checks and ORM queries.
- Keep the session-level PostgreSQL advisory lock held across the full bootstrap sequence.
- Prevent fresh Docker/Podman deployments from failing with `relation "user" does not exist`.
