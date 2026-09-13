# colf-manager production gate overlay r10

Questa revisione corregge il fallimento del job GitHub Actions `production-gate`.

Causa:
`scripts/production-gate.sh` richiedeva sempre `VIRTUAL_ENV`, ma GitHub Actions
usa `actions/setup-python`, che non imposta `VIRTUAL_ENV`.

Comportamento r10:
- locale: richiede ancora `.venv` attivo;
- GitHub Actions: accetta `GITHUB_ACTIONS=true`;
- marker/evidence aggiornati a r10.

Applicazione:

```bash
cd /root/colf-manager
unzip -o /percorso/colf-manager-production-gate-r10.zip

git diff -- scripts/production-gate.sh

source .venv/bin/activate
scripts/production-gate.sh

git add scripts/production-gate.sh
git commit -m "Fix production gate on GitHub Actions"
git push origin main
```
