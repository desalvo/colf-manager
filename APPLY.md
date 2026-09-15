# colf-manager r54 full package

This is a complete repository snapshot, not an incremental patch.

```bash
unzip colf-manager-r54-full.zip
cd /root/colf-manager
rsync -a --delete --exclude .git /path/to/extracted/colf-manager/ ./
source .venv/bin/activate
scripts/check-all.sh
```

Expected production gate result: `Production gate r54 full passed.`


Local packaged photographic assets are bundled in `src/colf_manager/static/heroes/`.
