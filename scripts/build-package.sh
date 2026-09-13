#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="$(cat VERSION)"
build_id="$(date -u +%Y%m%d-%H%M)"
mkdir -p dist
python -m build
python scripts/generate-manuals.py
base="colf-manager-v${version}-${build_id}"
git archive --format=tar --prefix="${base}/" HEAD > "dist/${base}.tar"
gzip -9 -c "dist/${base}.tar" > "dist/${base}.tar.gz"
python - "${base}" <<'PY'
import pathlib, sys, zipfile
base=sys.argv[1]; root=pathlib.Path('.')
with zipfile.ZipFile(root/'dist'/f'{base}.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if p.is_file() and not any(x in p.parts for x in ('.git','.venv','dist','tmp','__pycache__')):
            z.write(p, pathlib.Path(base)/p)
PY
rm "dist/${base}.tar"
sha256sum "dist/${base}.zip" "dist/${base}.tar.gz" dist/*.whl dist/*.tar.gz > "dist/SHA256SUMS"
