# colf-manager r14 full package

This archive is a complete repository snapshot. It is not an incremental patch.

## Main fix

Database initialization is serialized across Gunicorn workers and Kubernetes replicas using a PostgreSQL advisory lock. This prevents simultaneous `CREATE TABLE` operations during first boot.

## Replace an existing clone

```bash
cd /root/colf-manager
git status
# commit or stash local changes first

rsync -a --delete --exclude .git /path/to/extracted/colf-manager/ ./

source .venv/bin/activate
scripts/production-gate.sh

git status
git diff
git add -A
git commit -m "Fix concurrent database bootstrap"
git push origin main
```

Expected final gate line:

```text
Production gate r14 full passed.
```

## Temporary workaround for an older image

Until the r14 image is deployed, set `GUNICORN_WORKERS=1` to avoid the startup race. This is only a workaround; r14 supports multiple workers normally.
