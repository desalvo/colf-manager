#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== colf-manager hardening full package r35: local checks =="

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
    echo "Extract full package r35 over a fresh/full clone of desalvo/colf-manager." >&2
    exit 2
  fi
done

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ERROR: activate .venv first." >&2
  echo "Run: source .venv/bin/activate" >&2
  exit 2
fi

# Verify the checked-in source without modifying the working tree.
echo "[1/6] Ruff lint and formatting"
ruff check .
ruff format --check .
echo "[2/6] Tests and coverage"
pytest
echo "[3/6] Bandit"
bandit -q -r src -x tests
echo "[4/6] pip-audit"
pip-audit .
echo "[5/6] Docker Compose interpolation/config"
env \
  POSTGRES_PASSWORD='validation-only-postgres-password' \
  COLF_MANAGER_SECRET_KEY='validation-only-secret-key-0123456789abcdef0123456789abcdef' \
  COLF_MANAGER_ADMIN_PASSWORD='Validation-admin-password-1234' \
  docker compose config --quiet
echo "[6/6] Alembic heads"
COLF_MANAGER_PRODUCTION=0 COLF_MANAGER_DATA="$(mktemp -d)" \
  flask --app colf_manager.app:create_app db heads

echo
echo "Full package r35 local checks passed."
