# colf-manager CI/CD overlay r7

Questo overlay aggiorna esclusivamente i workflow GitHub Actions.

Modifiche:
- actions/checkout: v4 -> v6 (Node 24)
- actions/setup-python: v5 -> v6 (Node 24)
- github/codeql-action: v3 -> v4
- aquasecurity/trivy-action: 0.31.0 -> v0.36.0
- nessuna modifica alla logica di pubblicazione Docker Hub

Applicazione:

```bash
cd /root/colf-manager
unzip -o /percorso/colf-manager-ci-overlay-r7.zip
git diff -- .github/workflows
git add .github/workflows
git commit -m "Fix GitHub Actions and Docker latest publishing"
git push origin main
```

Dopo il push:
1. CI / production gates: test, security e manifests devono essere verdi.
2. production-gate deve partire.
3. Publish Docker latest deve partire e pubblicare desalvo/colf-manager:latest.

Se Publish Docker latest fallisce al login, verificare in GitHub:
Settings -> Secrets and variables -> Actions -> Repository secrets:
- DOCKERHUB_USERNAME
- DOCKERHUB_TOKEN

Non usare un token Docker Hub scaduto o una password account al posto del token.
