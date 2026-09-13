#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== colf-manager hardening overlay r6: environment preparation =="

required=(VERSION pyproject.toml README.md src/colf_manager/templates/dashboard.html)
for path in "${required[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "ERROR: missing $path; apply r5 over a complete clone." >&2
    exit 2
  fi
done

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "ERROR: no Python virtual environment is active." >&2
  echo "Run: python3 -m venv .venv && source .venv/bin/activate" >&2
  exit 2
fi

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
python - <<'PY'
from importlib.metadata import version
from packaging.version import Version
checks = {
    'Flask-Limiter': Version('4.1.1'),
    'twine': Version('7.0.0'),
    'rich': Version('14.3.3'),
}
for package, minimum in checks.items():
    current = Version(version(package))
    if current < minimum:
        raise SystemExit(f'{package} >= {minimum} required; found {current}')
    print(f'{package}: {current}')
PY
echo
echo "Dependencies installed for overlay r6."
echo "Run one command only: scripts/check-all.sh"
