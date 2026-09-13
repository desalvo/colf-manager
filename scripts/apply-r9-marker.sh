#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python - <<'PY'
from pathlib import Path
p = Path("scripts/production-gate.sh")
s = p.read_text()
s = s.replace("overlay r8: production gate", "overlay r9: production gate")
s = s.replace('"overlay_revision": "r8"', '"overlay_revision": "r9"')
s = s.replace("Production gate r8 passed.", "Production gate r9 passed.")
p.write_text(s)
PY

echo "Production gate markers updated to r9."
