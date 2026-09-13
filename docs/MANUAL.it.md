# colf-manager 1.0.0 - Manuale italiano

## Scopo

colf-manager centralizza la gestione quotidiana di un rapporto di lavoro domestico. È pensato per un datore di lavoro privato e mantiene uno storico verificabile di ore, luoghi, tariffe, assenze, spese e documenti.

## Funzioni

- calendario mensile storico con spostamento drag & drop;
- più fasce orarie nello stesso giorno e luogo per ogni fascia;
- costo orario con decorrenza, senza riscrivere i mesi passati;
- ferie pagate, permessi non retribuiti e malattia pagata/non pagata;
- anticipi e rimborsi in entrambe le direzioni;
- anagrafica, codice fiscale, data assunzione e riferimento INPS opzionale;
- archivio documentale su volume persistente;
- riepiloghi mensili e base dati per periodi trimestrali, semestrali, annuali o personalizzati;
- prospetto paga PDF e accantonamento TFR stimato.

## Interfaccia web

Il logo colf-manager identifica navigazione, accesso e manuali. Login, dashboard, calendario, anagrafica, spese, documenti e report adottano fotografie realistiche distinte, overlay ad alto contrasto e focal point responsive. Sotto 850 px il menu diventa un pannello mobile con sfondo oscurato; tabelle e calendario restano scorrevoli e i moduli passano a una colonna.

## Installazione Docker

Installare Docker con Compose, copiare `.env.example` in `.env`, generare tre segreti robusti e avviare `docker compose up -d --build`. Eseguire il backup con `pg_dump` e includere il volume `app-data` degli allegati.

## Kubernetes

Modificare i valori `CHANGE_ME` del Secret, hostname, ingress class, StorageClass e dimensioni PVC. Applicare `kubectl apply -f kubernetes/colf-manager.yaml`. In produzione usare TLS, NetworkPolicy, secret manager, backup verificati e un registro immagine con digest bloccato.

## Uso

1. Accedere e cambiare immediatamente la password iniziale tramite una nuova distribuzione sicura del secret prima del primo avvio.
2. Inserire la lavoratrice e la tariffa iniziale.
3. Aggiungere ore dal calendario; trascinare un evento per ripianificarlo.
4. Registrare ferie, permessi o malattia specificando se retribuiti e le ore pagate.
5. Registrare spese e caricare ricevute o altri documenti.
6. Aprire Report e paghe per calcolare il mese e scaricare il prospetto.

## TFR e adempimenti

L'accantonamento gestionale usa un divisore configurabile, inizialmente 13,5, sulla retribuzione registrata. La liquidazione effettiva può richiedere rivalutazione, inclusione/esclusione di voci e trattamento fiscale. Le regole del rapporto domestico, le quote contributive e le tabelle INPS cambiano: verificare sempre fonti ufficiali e contratto applicato.

La certificazione annuale prodotta dall'app è un riepilogo equivalente per uso documentale, non una Certificazione Unica trasmessa all'Agenzia delle Entrate.

## Sicurezza e privacy

I dati sono personali e possono includere informazioni sanitarie. Limitare gli accessi, usare HTTPS, cifrare backup e dischi, applicare una retention documentata, non inserire diagnosi nelle note e registrare solo i dati necessari. Il container gira senza root, con filesystem di base in sola lettura e capability rimosse.

## Build e release

`scripts/release-check.sh` esegue lint, test/copertura, Bandit, audit dipendenze, manuali IT/EN, wheel/sdist, `twine check`, SBOM CycloneDX e verifica pacchetto. `scripts/build-package.sh` genera ZIP, TAR.GZ e SHA-256 con build ID UTC `YYYYMMDD-HHMM`. Il tag `v1.0.0` deve corrispondere a `VERSION` e `pyproject.toml`.

I gate GitHub usano runner espliciti `ubuntu-24.04`, matrice Python 3.11-3.13, scansione segreti, CodeQL, validazione Docker Compose/Kubernetes, build multiarch, Trivy e attestazione di provenienza. `scripts/production-gate.sh` genera inoltre `dist/production-evidence.json`.

Configurare i secret repository `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN` prima di pubblicare `main`; il relativo workflow produce `desalvo/colf-manager:latest` solo dopo il superamento di tutti i gate. Per una release configurare anche `RELEASE_GPG_PUBLIC_KEY` con la chiave pubblica ASCII-armored, quindi creare un tag firmato `vX.Y.Z`: il workflow verifica firma e coerenza con `VERSION`, pubblica esclusivamente `desalvo/colf-manager:X.Y.Z` e crea la GitHub Release.

## Limiti

Il software non sostituisce un consulente del lavoro, non effettua versamenti o comunicazioni e non certifica la correttezza legale dei parametri inseriti.
