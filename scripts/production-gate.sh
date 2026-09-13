#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="$(cat VERSION)"
test "$version" = "$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
test "$version" = "$(python -c 'import colf_manager; print(colf_manager.__version__)')"
ruff check .
ruff format --check .
pytest
bandit -q -r src -x tests
python scripts/generate-manuals.py
python -m build
twine check dist/colf_manager-*.whl dist/colf_manager-*.tar.gz
cyclonedx-py environment --output-format JSON --output-file dist/colf-manager-sbom.json
python - <<'PY'
import json
from pathlib import Path
from pypdf import PdfReader

required = [
    Path("Dockerfile"), Path("docker-compose.yml"), Path("kubernetes/colf-manager.yaml"),
    Path("SECURITY.md"), Path("LICENSE"), Path("output/pdf/colf-manager-manual-v1.0.0-it.pdf"),
    Path("output/pdf/colf-manager-manual-v1.0.0-en.pdf"), Path("src/colf_manager/static/logo.svg"),
    Path("src/colf_manager/static/logo.png"),
]
missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
if missing:
    raise SystemExit(f"Missing production artifacts: {missing}")
pages = {str(path): len(PdfReader(path).pages) for path in required if path.suffix == ".pdf"}
if any(count < 2 for count in pages.values()):
    raise SystemExit(f"Incomplete manuals: {pages}")
evidence = {"version": "1.0.0", "status": "passed", "manual_pages": pages, "checks": ["version", "lint", "format", "tests", "coverage", "bandit", "manuals", "build", "twine", "sbom", "artifacts"]}
Path("dist").mkdir(exist_ok=True)
Path("dist/production-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
PY
