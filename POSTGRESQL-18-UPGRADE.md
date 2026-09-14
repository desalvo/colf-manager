# PostgreSQL 18.6 upgrade notes

Colf Manager r25 uses `postgres:18.6-alpine` for new installations.

## Important: existing PostgreSQL 17 installations

PostgreSQL 18 is a major-version upgrade. Do **not** simply start the PostgreSQL 18 container against a PostgreSQL 17 data directory.

The official PostgreSQL 18 image also changes its storage layout:

- PostgreSQL 17 and earlier: default `PGDATA=/var/lib/postgresql/data`
- PostgreSQL 18: default `PGDATA=/var/lib/postgresql/18/docker`
- PostgreSQL 18 volume mount target: `/var/lib/postgresql`

Use a logical dump/restore or `pg_upgrade` before switching an existing production database.

## Recommended safe procedure

1. Stop writes to Colf Manager.
2. Create and verify a PostgreSQL 17 logical backup with `pg_dump -Fc` (or `pg_dumpall` when appropriate).
3. Keep the old PostgreSQL 17 PVC/volume untouched until the migration is verified.
4. Provision a fresh PostgreSQL 18 data volume/PVC.
5. Start PostgreSQL 18.6 on the new empty volume.
6. Restore the dump using `pg_restore`.
7. Start Colf Manager and run the application/database checks.
8. Keep the PostgreSQL 17 backup/PVC until functional verification is complete.

For Kubernetes, do not reuse the old PostgreSQL 17 PVC as the PostgreSQL 18 data directory without a supported major-upgrade procedure.
