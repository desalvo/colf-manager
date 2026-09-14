# colf-manager r13 full package

This archive is a complete repository snapshot. It is not an incremental patch and does not depend on any previous rN overlay.

## Replace an existing clone

Keep the `.git` directory, then replace the working tree contents with the contents of the `colf-manager/` directory from this archive.

Recommended safe procedure:

```bash
cd /root/colf-manager
git status
# ensure local changes are committed/stashed first

rsync -a --delete --exclude .git /path/to/extracted/colf-manager/ ./

source .venv/bin/activate
scripts/production-gate.sh

git status
git diff
git add -A
git commit -m "Install full r13 package with split Kubernetes resources"
git push origin main
```

Expected final gate line:

```text
Production gate r13 full passed.
```
