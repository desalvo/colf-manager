# colf-manager hardening overlay r6

Apply this archive over a **fresh, complete clone** of `desalvo/colf-manager`.
Do not run it from a directory containing only a previous overlay.

## Clean verification

```bash
cd /root
mv colf-manager colf-manager-old 2>/dev/null || true
git clone https://github.com/desalvo/colf-manager.git
cd colf-manager
unzip -o /path/to/colf-manager-v1.0.0-hardening-overlay-r6.zip

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
scripts/prepare-local-checks.sh

# This is the only verification command needed:
scripts/check-all.sh
```

The scripts print `overlay r6` in their first line. If you do not see that text,
you are running an older script and should stop before interpreting its errors.

`check-all.sh` performs Ruff autofix/formatting, strict lint/format verification,
pytest with coverage, Bandit, pip-audit, Docker Compose validation using temporary
validation-only environment variables, Alembic-head validation and the full
production artifact gate.

You do **not** need a real `.env` for verification. Create `.env` only before
actually starting the application.
