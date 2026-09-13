#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== colf-manager hardening overlay r6: recreate .venv =="
rm -rf .venv
python3 -m venv .venv
echo "Virtual environment created. Run:"
echo "  source .venv/bin/activate"
echo "  scripts/prepare-local-checks.sh"
