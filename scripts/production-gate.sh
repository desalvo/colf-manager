#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== colf-manager full package r39: production gate =="

if [[ "${GITHUB_ACTIONS:-}" != "true" && -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ERROR: activate .venv first for local execution." >&2
  exit 2
fi

version="$(cat VERSION)"
test "$version" = "$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
test "$version" = "$(python -c 'import colf_manager; print(colf_manager.__version__)')"

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

COLF_MANAGER_PRODUCTION=0 COLF_MANAGER_DATA="$(mktemp -d)"   flask --app colf_manager.app:create_app db heads

python scripts/generate-manuals.py

rm -rf dist build
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
    Path("kubernetes/namespace.yaml"),
    Path("kubernetes/secret-database.yaml"),
    Path("kubernetes/secret-application.yaml"),
    Path("kubernetes/pvc-database.yaml"),
    Path("kubernetes/pvc-application.yaml"),
    Path("kubernetes/database.yaml"),
    Path("kubernetes/application.yaml"),
    Path("kubernetes/backup.yaml"),
    Path("kubernetes/network-policy.yaml"),
    Path("kubernetes/ingress.yaml"),
    Path("kubernetes/kustomization.yaml"),
    Path("kubernetes/maintenance.yaml"),
    Path("migrations/versions/1004_generated_reports.py"),
    Path("SECURITY.md"),
    Path("LICENSE"),
    Path("output/pdf/colf-manager-manual-v1.0.0-it.pdf"),
    Path("output/pdf/colf-manager-manual-v1.0.0-en.pdf"),
    Path("src/colf_manager/static/logo.svg"),
    Path("src/colf_manager/static/logo.png"),
    Path("src/colf_manager/mailer.py"),
    Path("src/colf_manager/templates/settings.html"),
    Path("src/colf_manager/templates/mail_compose.html"),
    Path("src/colf_manager/templates/rates.html"),
    Path("src/colf_manager/templates/expense_edit.html"),
    Path("src/colf_manager/static/calendar.js"),
    Path("migrations/versions/1000_hardened_baseline.py"),
    Path("migrations/versions/1001_employers_vacation_reports.py"),
    Path("migrations/versions/1002_contract_tax_reporting.py"),
    Path("migrations/versions/1003_locations.py"),
]

missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
if missing:
    raise SystemExit(f"Missing production artifacts: {missing}")

if Path("kubernetes/colf-manager.yaml").exists():
    raise SystemExit("Obsolete kubernetes/colf-manager.yaml must be removed")

pages = {
    str(path): len(PdfReader(path).pages)
    for path in required
    if path.suffix == ".pdf"
}
if any(count < 2 for count in pages.values()):
    raise SystemExit(f"Incomplete manuals: {pages}")

evidence = {
    "version": "1.0.0",
    "overlay_revision": "r39-full",
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
        "split-kubernetes-artifacts",
        "artifacts",
    ],
}

Path("dist").mkdir(exist_ok=True)
Path("dist/production-evidence.json").write_text(
    json.dumps(evidence, indent=2) + "\n"
)
PY

echo "Production gate r39 full passed."
