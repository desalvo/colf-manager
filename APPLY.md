# colf-manager r25 full package

This is a complete repository snapshot, not an incremental patch.

```bash
unzip colf-manager-r25-full.zip
cd /root/colf-manager
rsync -a --delete --exclude .git /path/to/extracted/colf-manager/ ./
source .venv/bin/activate
scripts/check-all.sh
```

Expected production gate result: `Production gate r25 full passed.`
