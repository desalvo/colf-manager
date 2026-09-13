# colf-manager hardening overlay r9

Perché r8 falliva ancora
-------------------------
Il filesystem finale era già corretto:
- Debian: 0 HIGH/CRITICAL
- msgpack runtime installato: 1.2.2
- setuptools runtime installato: 84.0.0

Trivy continuava però a rilevare msgpack 1.1.2 e setuptools 70.3.0 in un
inventario/SBOM Python secondario ereditato dall'immagine, segnalando esso stesso:
"Third-party SBOM may lead to inaccurate vulnerability detection".

r9 separa quindi i controlli:
- pip-audit: dipendenze Python
- Trivy: vulnerabilità OS/container
- Gitleaks: secrets
- Bandit: codice Python
- kubeconform: manifest Kubernetes

Inoltre:
- il build CI disabilita provenance/SBOM per l'immagine temporanea `colf-manager:ci`;
- il build di release/latest continua a generare provenance e SBOM;
- il runtime Docker non installa più msgpack/setuptools solo per lo scanner;
- viene eseguito un runtime smoke test;
- il marker del production gate viene portato a r9 tramite uno script di patch.

Applicazione
------------

```bash
cd /root/colf-manager
unzip -o /percorso/colf-manager-hardening-overlay-r9.zip

# aggiorna il marker del gate senza sostituire lo script intero
bash scripts/apply-r9-marker.sh

git diff -- Dockerfile .github/workflows/ci.yml scripts/production-gate.sh

source .venv/bin/activate
scripts/production-gate.sh

git add Dockerfile .github/workflows/ci.yml scripts/production-gate.sh
git commit -m "Fix Trivy runtime scan and manifest gate"
git push origin main
```
