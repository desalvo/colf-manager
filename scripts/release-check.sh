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
python -c "from pathlib import Path; from pypdf import PdfReader; paths=[Path('output/pdf/colf-manager-manual-v1.0.0-it.pdf'),Path('output/pdf/colf-manager-manual-v1.0.0-en.pdf')]; [(_ for _ in ()).throw(AssertionError(str(p))) if len(PdfReader(p).pages)<2 else None for p in paths]"
