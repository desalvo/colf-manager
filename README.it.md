# colf-manager 1.0.0

<img src="src/colf_manager/static/logo.svg" alt="colf-manager" width="180">

Applicazione web per il datore di lavoro domestico: ore e luoghi, tariffe storicizzate, ferie, permessi, malattia, anticipi e rimborsi, TFR, documenti, riepiloghi e prospetti paga.

## Avvio rapido

```bash
cp .env.example .env
# sostituire TUTTI i valori di esempio con segreti reali
docker compose up -d --build
```

Aprire `http://localhost:8000`. L'utente iniziale è `admin`; la password è quella definita in `COLF_MANAGER_ADMIN_PASSWORD`. Al primo accesso viene richiesto il cambio password. In modalità produzione l'applicazione rifiuta di avviarsi con segreti mancanti o placeholder.

Per Docker Compose in HTTP locale `COLF_MANAGER_SECURE_COOKIES=0`; dietro HTTPS/Ingress impostarlo a `1`. Il login è protetto da rate limiting, tutte le operazioni mutative da CSRF e le sessioni usano cookie HttpOnly/SameSite. Gli amministratori possono creare ulteriori utenti da **Utenti**.

Il calendario permette inserimento e spostamento drag & drop. Le tariffe sono storicizzate e univoche per lavoratrice/data di decorrenza. Le assenze retribuite che attraversano mesi o cambi tariffa vengono ripartite sui giorni interessati. Gli anticipi della lavoratrice aumentano il dovuto (rimborso), quelli del datore lo riducono (recupero).

Gli upload accettano solo PDF/JPEG/PNG, verificano estensione, MIME e firma del file e memorizzano SHA-256 e dimensione. Login, cambio password, operazioni principali e download documenti sono tracciati nell'audit applicativo.

## Database e migrazioni

Flask-Migrate/Alembic è abilitato. I database creati dalla prima build 1.0.0 vengono aggiornati in modo compatibile all'avvio senza ricreazione distruttiva. Dopo avere eseguito un backup e verificato la build hardened:

```bash
flask --app colf_manager.app:create_app db stamp 1000_hardened_baseline
```

Le modifiche schema successive devono usare migrazioni Alembic revisionate e `flask db upgrade`.

## Kubernetes

Le risorse Kubernetes sono separate in manifest indipendenti per applicazione, database, PVC, Secret, backup, NetworkPolicy e Ingress. Eliminare il workload applicativo o PostgreSQL non elimina i PVC; il PVC applicativo può essere cancellato senza toccare i dati del database. Configurare i due Secret e lo storage prima del deploy. Vedi `kubernetes/README.it.md`.

## Qualità e release

La CI esegue Python 3.11-3.13, Ruff, pytest con coverage minimo 85%, Bandit, pip-audit, gitleaks, Trivy, kubeconform, CodeQL, build multiarch, SBOM e provenance. `scripts/production-gate.sh` verifica anche la presenza della baseline Alembic.

## Limiti d'uso

I calcoli e i prospetti sono documenti gestionali di supporto: non inviano comunicazioni INPS e non sostituiscono CU ufficiale, consulente del lavoro o verifica del CCNL vigente.

Manuali: [Italiano](docs/MANUAL.it.md) · [English](docs/MANUAL.en.md)

Autore: Alessandro De Salvo · Licenza EUPL-1.2
