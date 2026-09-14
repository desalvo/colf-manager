# colf-manager r15 full package

This archive is a complete repository snapshot, not an incremental patch.

It fixes PostgreSQL bootstrap in multi-worker Docker/Podman/Kubernetes deployments.
The bootstrap holds a session-level PostgreSQL advisory lock, creates the schema,
commits the transactional DDL so pooled connections can see it, then performs
legacy compatibility checks and initial-admin creation before releasing the lock.

## Replace an existing clone

```bash
cd /root/colf-manager
git status
# commit/stash local changes first
rsync -a --delete --exclude .git /path/to/extracted/colf-manager/ ./
source .venv/bin/activate
scripts/production-gate.sh
git status
git diff
git add -A
git commit -m "Fix PostgreSQL bootstrap transaction visibility"
git push origin main
```

Expected final line:

```text
Production gate r15 full passed.
```
