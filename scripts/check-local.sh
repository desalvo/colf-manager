#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== colf-manager hardening full package r54: local checks =="

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
    echo "Extract full package r54 over a fresh/full clone of desalvo/colf-manager." >&2
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
scripts/compose-config-check.sh
echo "[6/6] Alembic heads"
COLF_MANAGER_PRODUCTION=0 COLF_MANAGER_DATA="$(mktemp -d)" \
  flask --app colf_manager.app:create_app db heads

echo
echo "Full package r54 local checks passed."
