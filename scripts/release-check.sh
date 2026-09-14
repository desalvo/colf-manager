#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="$(cat VERSION)"
python -c "import tomllib; assert tomllib.load(open('pyproject.toml','rb'))['project']['version']=='${version}'"
ruff check .
pytest
bandit -q -r src -x tests
pip-audit .
scripts/production-gate.sh
python scripts/generate-manuals.py
python -m build
twine check dist/colf_manager-*.whl dist/colf_manager-*.tar.gz
cyclonedx-py environment --output-format JSON --output-file dist/colf-manager-sbom.json
