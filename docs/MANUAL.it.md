# colf-manager 1.0.0 - Manuale italiano

## Scopo

colf-manager centralizza la gestione quotidiana di un rapporto di lavoro domestico e mantiene uno storico verificabile di ore, luoghi, tariffe, assenze, spese e documenti.

## Funzioni

- calendario mensile storico con spostamento drag & drop;
- più fasce orarie nello stesso giorno e luogo per ogni fascia;
- costo orario con decorrenza, senza riscrivere i mesi passati;
- ferie pagate, permessi non retribuiti e malattia pagata/non pagata;
- anticipi e rimborsi in entrambe le direzioni;
- anagrafica, codice fiscale, data assunzione e riferimento INPS opzionale;
- archivio documentale su volume persistente;
- riepiloghi mensili e prospetto paga PDF;
- accantonamento TFR stimato.

## Installazione Docker

Installare Docker con Compose, copiare `.env.example` in `.env`, generare segreti robusti e avviare `docker compose up -d --build`. Eseguire il backup PostgreSQL con `pg_dump` e includere il volume degli allegati.

## Kubernetes

Le risorse Kubernetes sono separate per responsabilità. Configurare `secret-database.yaml` e `secret-application.yaml`, quindi applicare namespace, PVC, database, applicazione, backup, NetworkPolicy e Ingress. La cancellazione di `application.yaml` conserva `app-data`; la cancellazione di `database.yaml` conserva `postgres-data` e `backup-data`. `pvc-application.yaml` può essere eliminato autonomamente senza toccare i dati del database. Vedi `kubernetes/README.it.md`.

## Uso

Creare la lavoratrice e la tariffa iniziale, inserire le ore dal calendario, registrare ferie/permessi/malattia, inserire spese e documenti e usare la sezione Report per i riepiloghi.

## TFR e adempimenti

L'accantonamento gestionale usa un divisore configurabile, inizialmente 13,5, sulla retribuzione registrata. La liquidazione effettiva può richiedere rivalutazione, inclusione/esclusione di voci e trattamento fiscale. Verificare sempre fonti ufficiali e contratto applicato.

## Sicurezza e privacy

I dati sono personali e possono includere informazioni sanitarie. Limitare gli accessi, usare HTTPS, cifrare backup e dischi, applicare una retention documentata e registrare solo i dati necessari.

## Build e release

`scripts/release-check.sh` esegue lint, test/copertura, Bandit, audit dipendenze, manuali IT/EN, wheel/sdist, `twine check`, SBOM CycloneDX e verifica pacchetto. La CI usa Python 3.11-3.13, Gitleaks, CodeQL, Trivy e validazione Docker/Kubernetes.

## Limiti

Il software non sostituisce un consulente del lavoro, non effettua versamenti o comunicazioni e non certifica la correttezza legale dei parametri inseriti.
