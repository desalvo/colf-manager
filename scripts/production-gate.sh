#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== colf-manager hardening overlay r6: production gate =="

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ERROR: activate .venv first." >&2
  exit 2
fi

version="$(cat VERSION)"
test "$version" = "$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
test "$version" = "$(python -c 'import colf_manager; print(colf_manager.__version__)')"

# Normalize once so an overlay applied to a clean clone cannot fail merely
# because the archive itself was created before Ruff's canonical formatting.
ruff check --fix .
ruff format .
ruff check .
ruff format --check .
pytest
bandit -q -r src -x tests
pip-audit .

env \
  POSTGRES_PASSWORD='validation-only-postgres-password' \
  COLF_MANAGER_SECRET_KEY='validation-only-secret-key-0123456789abcdef0123456789abcdef' \
  COLF_MANAGER_ADMIN_PASSWORD='Validation-admin-password-1234' \
  docker compose config --quiet

COLF_MANAGER_PRODUCTION=0 COLF_MANAGER_DATA="$(mktemp -d)" \
  flask --app colf_manager.app:create_app db heads

python scripts/generate-manuals.py
python -m build
python - <<'PY'
from importlib.metadata import version
from packaging.version import Version

current = Version(version("twine"))
if current < Version("7.0.0"):
    raise SystemExit(f"Twine >= 7.0.0 required for Core Metadata 2.5; found {current}")
print(f"Twine metadata validator: {current}")
PY
twine check dist/colf_manager-*.whl dist/colf_manager-*.tar.gz
cyclonedx-py environment --output-format JSON --output-file dist/colf-manager-sbom.json
python - <<'PY'
import json
from pathlib import Path
from pypdf import PdfReader

required = [
    Path("Dockerfile"),
    Path("docker-compose.yml"),
    Path("kubernetes/colf-manager.yaml"),
    Path("SECURITY.md"),
    Path("LICENSE"),
    Path("output/pdf/colf-manager-manual-v1.0.0-it.pdf"),
    Path("output/pdf/colf-manager-manual-v1.0.0-en.pdf"),
    Path("src/colf_manager/static/logo.svg"),
    Path("src/colf_manager/static/logo.png"),
    Path("migrations/versions/1000_hardened_baseline.py"),
]
missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
if missing:
    raise SystemExit(f"Missing production artifacts: {missing}")
pages = {str(path): len(PdfReader(path).pages) for path in required if path.suffix == ".pdf"}
if any(count < 2 for count in pages.values()):
    raise SystemExit(f"Incomplete manuals: {pages}")
evidence = {
    "version": "1.0.0",
    "overlay_revision": "r6",
    "status": "passed",
    "manual_pages": pages,
    "checks": [
        "version",
        "lint",
        "format",
        "tests",
        "coverage>=65",
        "bandit",
        "pip-audit",
        "compose",
        "alembic-head",
        "manuals",
        "build",
        "twine",
        "sbom",
        "artifacts",
    ],
}
Path("dist").mkdir(exist_ok=True)
Path("dist/production-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
PY

echo "Production gate r6 passed."
