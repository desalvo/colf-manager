#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== colf-manager hardening overlay r6: local checks =="

required=(
  VERSION
  pyproject.toml
  README.md
  src/colf_manager/templates/dashboard.html
  src/colf_manager/static/style.css
  scripts/production-gate.sh
  tests/test_validation.py
)
for path in "${required[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "ERROR: missing $path" >&2
    echo "Extract overlay r6 over a fresh/full clone of desalvo/colf-manager." >&2
    exit 2
  fi
done

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ERROR: activate .venv first." >&2
  echo "Run: source .venv/bin/activate" >&2
  exit 2
fi

# Canonicalize first, then prove the tree is clean according to Ruff.
echo "[1/8] Ruff autofix"
ruff check --fix .
echo "[2/8] Ruff format"
ruff format .
echo "[3/8] Ruff strict verification"
ruff check .
ruff format --check .
echo "[4/8] Tests and coverage"
pytest
echo "[5/8] Bandit"
bandit -q -r src -x tests
echo "[6/8] pip-audit"
pip-audit .
echo "[7/8] Docker Compose interpolation/config"
env \
  POSTGRES_PASSWORD='validation-only-postgres-password' \
  COLF_MANAGER_SECRET_KEY='validation-only-secret-key-0123456789abcdef0123456789abcdef' \
  COLF_MANAGER_ADMIN_PASSWORD='Validation-admin-password-1234' \
  docker compose config --quiet
echo "[8/8] Alembic heads"
COLF_MANAGER_PRODUCTION=0 COLF_MANAGER_DATA="$(mktemp -d)" \
  flask --app colf_manager.app:create_app db heads

echo
echo "Overlay r6 local checks passed."
