#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== colf-manager full package r97: complete verification =="
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ERROR: activate .venv first: source .venv/bin/activate" >&2
  exit 2
fi

scripts/check-local.sh

echo
echo "== production gate =="
scripts/production-gate.sh

echo
echo "ALL R96 CHECKS PASSED"
