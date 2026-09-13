# colf-manager 1.0.0

![colf-manager](src/colf_manager/static/logo.svg)

Applicazione web per il datore di lavoro domestico: ore e luoghi, tariffe storicizzate, ferie, permessi, malattia, anticipi e rimborsi, TFR, documenti, riepiloghi e prospetti paga.

## Avvio rapido

```bash
cp .env.example .env
# sostituire tutti i segreti di esempio
docker compose up -d --build
```

Aprire `http://localhost:8000`. L'utente iniziale è `admin`; la password è quella definita in `COLF_MANAGER_ADMIN_PASSWORD` al primo avvio.

Il calendario permette inserimento e spostamento drag & drop. Ogni tariffa ha una data di decorrenza e i report storici usano quella valida nel giorno lavorato. PostgreSQL conserva i dati; il volume applicativo conserva gli allegati.

L'interfaccia fotografica responsive utilizza immagini distinte per accesso, panoramica, calendario, anagrafica, spese, documenti e report. Il logo è presente nell'app e in entrambi i manuali PDF.

Il gate `scripts/production-gate.sh` produce evidenze verificabili; GitHub Actions esegue matrice Python 3.11-3.13, CodeQL, ricerca segreti, validazione dei manifesti, build multiarch, Trivy, SBOM e attestazione di provenienza su runner espliciti `ubuntu-24.04`.

## Distribuzione e release

- Docker Compose: `docker-compose.yml`
- Kubernetes: `kubernetes/colf-manager.yaml`
- immagine stabile da `main`: `desalvo/colf-manager:latest`
- immagine di release: `desalvo/colf-manager:1.0.0`
- controllo completo: `scripts/release-check.sh`
- release: pubblicare il tag firmato `v1.0.0` dopo il superamento della CI

Prima del primo push configurare i secret GitHub Actions `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN`. Prima del primo tag configurare anche `RELEASE_GPG_PUBLIC_KEY` con la chiave pubblica ASCII-armored usata per firmare il tag. Il branch `main` pubblica esclusivamente `latest`; i tag `vX.Y.Z` pubblicano esclusivamente la corrispondente versione `X.Y.Z`.

Docker Compose usa `latest` per impostazione predefinita. Per bloccare una release specifica: `COLF_MANAGER_IMAGE_TAG=1.0.0 docker compose up -d`.

## Limiti d'uso

I calcoli, i prospetti paga e la certificazione annuale sono documenti gestionali di supporto: non inviano comunicazioni INPS e non sostituiscono CU ufficiale, consulente del lavoro o verifica del CCNL vigente.

Manuale completo: [sorgente italiano](docs/MANUAL.it.md) · [PDF italiano](output/pdf/colf-manager-manual-v1.0.0-it.pdf) · [English source](docs/MANUAL.en.md) · [English PDF](output/pdf/colf-manager-manual-v1.0.0-en.pdf)

Autore: Alessandro De Salvo <braket71@gmail.com> · Licenza EUPL-1.2
