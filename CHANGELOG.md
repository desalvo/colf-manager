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
