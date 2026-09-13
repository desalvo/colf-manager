# colf-manager hardening overlay r8

Correzioni:
- aggiorna i pacchetti Debian della runtime image durante il build;
- aggiorna setuptools >= 78.1.1 e msgpack >= 1.2.1 nella runtime image;
- forza `pull: true` nei build GitHub Actions;
- Trivy resta bloccante su HIGH/CRITICAL con fix disponibili;
- Trivy usa solo lo scanner vulnerabilità (`scanners: vuln`), perché Gitleaks copre già i secrets;
- production gate/evidence allineati a r8.

Applicazione:

```bash
cd /root/colf-manager
unzip -o /percorso/colf-manager-hardening-overlay-r8.zip

git diff -- Dockerfile .github/workflows/ci.yml scripts/production-gate.sh

source .venv/bin/activate
scripts/production-gate.sh

git add Dockerfile .github/workflows/ci.yml scripts/production-gate.sh
git commit -m "Patch container vulnerabilities and unblock manifests"
git push origin main
```

Dopo il push, `manifests` deve completare anche Trivy e kubeconform.
Se `manifests` passa, partiranno `production-gate` e poi `Publish Docker latest`.
