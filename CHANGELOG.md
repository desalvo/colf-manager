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

## r16-full - 2026-09-14

- Complete CRUD for workers and household employers, including optional address, phone and e-mail.
- Safe permanent deletion workflows.
- Worker-to-employer association.
- Correct previous/next month calendar controls and direct return to dashboard.
- Automatic accrued/projected vacation entitlement with optional advance use through year end.
- Automatic vacation paid-hours estimate for hourly workers.
- Estimated thirteenth-month and TFR accrual integrated in monthly/annual calculations.
- Professional PDF reports: monthly payroll, annual payroll, courtesy CU/income certification, annual TFR, hours/pay trend.
- Year-aware legal rule notes and official-source disclaimers.
- Alembic revision 1001 for employer and vacation-policy schema changes.
## r17-full - 2026-09-14

- Cedolino PDF specifico della tredicesima.
- Prospetto PDF cumulativo tredicesima + TFR con descrizione delle formule e del periodo.
- Numero contratto di lavoro e tipo contratto nell'anagrafica del lavoratore.
- Opzione contrattuale per porre economicamente a carico del datore anche le quote del lavoratore.
- Stima contributi INPS nei report quando posizione INPS e numero contratto sono presenti.
- Separazione tra contributi INPS e stima IRPEF: il datore domestico privato non viene trattato come sostituto d'imposta.
- Tabelle contributive 2025/2026 e indicazione della fonte/anno nei prospetti.
- Migration Alembic 1002_contract_tax_reporting.

## r19-full - 2026-09-14

- Fixed Ruff E701/E702/E741/F401/F841 failures introduced by the reporting work.
- Restored formatter-clean manual generator.
- Made monthly payroll PDF backward compatible when a summary lacks `thirteenth_accrual`.
- Updated PDF regression test to include the thirteenth accrual field.
- Updated production/local gate markers to r18.

## r19-full - 2026-09-14

- Added complete location management (create, view, edit, delete).
- Calendar now selects from registered locations.
- Historical work entries keep a location snapshot after location edits/deletion.
- Added database migration 1003_locations and regression tests.

## r20-full - 2026-09-14

- Unified worker terminology throughout the application and documentation.
- Added author, version and build to the application sidebar.
- Persist generated PDF reports and allow manual download/deletion.
- Added manual document deletion.
- Added full database/document/report ZIP export and destructive confirmed import.
- Added automatic orphan-file garbage collection for Docker/Podman and Kubernetes.
- Added selectable dashboard month/year and retroactive calendar entry defaults.

## r21-full - 2026-09-14

- Added regression tests for complete export/import and orphan-file maintenance.
- Restored production coverage above the configured 65% threshold without lowering it.
- Removed Bandit B608 by replacing dynamic PostgreSQL sequence SQL with bound queries and SQLAlchemy expressions.
- Production and local quality gates are now non-mutating (`ruff check` + `ruff format --check`).
- Compose validation continues to inject validation-only secrets without weakening production secret requirements.

## r23-full - 2026-09-14

- Formatted Alembic migrations `1003_locations.py` and `1004_generated_reports.py` to pass `ruff format --check`.
- Formatted `backup.py` and `storage.py` to pass `ruff format --check`.
- No functional behavior change from r21.
- Build and verification markers updated to r23-full.


## r24-full - 2026-09-14

- Fix Kubernetes PostgreSQL startup on restricted security contexts.
- Run `postgres:17-alpine` explicitly as UID/GID 70 and set `fsGroup: 70`.
- Add `fsGroupChangePolicy: OnRootMismatch` for the PostgreSQL PVC.
- Mount `/var/run/postgresql` from an `emptyDir` so the non-root process can create its Unix socket.
- Keep `allowPrivilegeEscalation: false` and drop all Linux capabilities.
- No PostgreSQL PVC deletion is required for this permission-only fix.

## r25-full - 2026-09-14

- Upgrade the bundled PostgreSQL runtime from 17 to the latest stable PostgreSQL 18.6 release.
- Pin database and backup images to `postgres:18.6-alpine`.
- Adopt the PostgreSQL 18 official-image storage layout by mounting the persistent volume at `/var/lib/postgresql`.
- Keep the Alpine `postgres` UID/GID 70 security context for the database and backup workloads.
- Add explicit PostgreSQL 17 → 18 major-upgrade guidance for existing Docker/Podman and Kubernetes installations.

## r27-full - 2026-09-14

- Pin the application image user/group to UID/GID 10001 and declare `USER 10001:10001`.
- Set Kubernetes application and maintenance workloads to explicit numeric `runAsUser`/`runAsGroup` 10001.
- Set `fsGroup: 10001` with `fsGroupChangePolicy: OnRootMismatch` for the shared application data PVC.
- Fix kubelet startup rejection when `runAsNonRoot` is enabled and the image declares the named `colf-manager` user.
- Mount ephemeral `/tmp` volumes for application and maintenance workloads while keeping `readOnlyRootFilesystem: true`.
