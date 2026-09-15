# colf-manager 1.0.0 · build r25-full

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

Il calendario permette inserimento e spostamento drag & drop. Le tariffe sono storicizzate e univoche per lavoratore/data di decorrenza. Le assenze retribuite che attraversano mesi o cambi tariffa vengono ripartite sui giorni interessati. Gli anticipi della lavoratore aumentano il dovuto (rimborso), quelli del datore lo riducono (recupero).

Gli upload accettano solo PDF/JPEG/PNG, verificano estensione, MIME e firma del file e memorizzano SHA-256 e dimensione. Login, cambio password, operazioni principali e download documenti sono tracciati nell'audit applicativo.

## Database e migrazioni

Flask-Migrate/Alembic è abilitato. I database creati dalla prima build 1.0.0 vengono aggiornati in modo compatibile all'avvio senza ricreazione distruttiva. Dopo avere eseguito un backup e verificato la build hardened:

```bash
flask --app colf_manager.app:create_app db stamp 1000_hardened_baseline
```

Le modifiche schema successive devono usare migrazioni Alembic revisionate e `flask db upgrade`.

## Kubernetes

Le risorse Kubernetes sono separate in manifest indipendenti per applicazione, database, PVC, Secret, backup, NetworkPolicy e Ingress. Eliminare il workload applicativo o PostgreSQL non elimina i PVC; il PVC applicativo può essere cancellato senza toccare i dati del database. Configurare i due Secret e lo storage prima del deploy. Vedi `kubernetes/README.it.md`.

## Lavoratori, datori, ferie e report

Lavoratori e datori di lavoro domestico hanno gestione completa di inserimento, visualizzazione, modifica e cancellazione, con indirizzo, telefono ed e-mail opzionali. Il lavoratore può essere associato a un datore e può opzionalmente utilizzare, entro il 31 dicembre, anche le ferie maturabili nell'anno non ancora maturate. L'app calcola ferie maturate/proiettate, ore ferie retribuite automatiche, quota di tredicesima stimata e TFR annuale. I PDF comprendono cedolino mensile, cedolino annuale, CU/certificazione di cortesia, TFR annuale e andamento mensile ore/retribuzioni.

## Qualità e release

La CI esegue Python 3.11-3.13, Ruff, pytest con coverage minimo 85%, Bandit, pip-audit, gitleaks, Trivy, kubeconform, CodeQL, build multiarch, SBOM e provenance. `scripts/production-gate.sh` verifica anche la presenza della baseline Alembic.

## Limiti d'uso

I calcoli e i prospetti sono documenti gestionali di supporto: non inviano comunicazioni INPS e non sostituiscono CU ufficiale, consulente del lavoro o verifica del CCNL vigente.

Manuali: [Italiano](docs/MANUAL.it.md) · [English](docs/MANUAL.en.md)

Autore: Alessandro De Salvo · Licenza EUPL-1.2

## Report r19

Sono disponibili anche cedolino tredicesima e report cumulativo tredicesima + TFR. Con posizione INPS e numero contratto valorizzati, i report includono contributi INPS stimati e una stima fiscale separata, con avvertenza sul fatto che il datore domestico privato non è normalmente sostituto d’imposta.


## Luoghi

I luoghi di lavoro sono gestiti da un’anagrafica dedicata con aggiunta, visualizzazione, modifica e cancellazione. Il calendario usa i luoghi registrati; le registrazioni storiche conservano una copia del nome/indirizzo usato anche se il luogo viene successivamente modificato o cancellato.


## Archivio, report e backup completo

I report PDF generati vengono conservati nell'applicazione sul volume persistente e possono essere riscaricati o cancellati manualmente. Anche i documenti caricati possono essere cancellati manualmente. Gli amministratori dispongono di un export ZIP completo di database, documenti referenziati e report archiviati e di un import completo con conferma esplicita. I file presenti sul volume ma non più referenziati dal database vengono eliminati automaticamente dal servizio di manutenzione dopo la retention configurata.

La Panoramica può essere consultata scegliendo mese e anno. Il calendario consente di navigare nei mesi precedenti e registrare retroattivamente le ore nel periodo visualizzato.

## PostgreSQL 18.6

La r25 usa `postgres:18.6-alpine`. Le installazioni PostgreSQL 17 esistenti richiedono una migrazione major supportata; leggere `POSTGRESQL-18-UPGRADE.it.md` prima di modificare il workload database o il PVC.

### Novità r55 - report, firme e pagamenti
- Report PDF con logo applicativo, versione/build e autore su ogni pagina, grafica rinnovata e visualizzazione inline dall'archivio.
- Firma grafica opzionale per lavoratore e datore caricabile dalle rispettive anagrafiche (PNG, JPEG, TIFF, WEBP, BMP) e apposta automaticamente ai report quando richiesta.
- Registro Pagamenti con inserimento manuale e generazione automatica del residuo dai report: retribuzioni, contributi INPS, tredicesima, TFR, rimborsi e altri pagamenti; stato, data, periodo, note e allegati.
- I contributi INPS sono disponibili solo quando il lavoratore ha una posizione INPS registrata.
- Full export/import include firme, pagamenti e relativi allegati oltre a database, documenti e report.

### Compensazioni manuali di spese e rimborsi
Ogni spesa crea una partita a credito del datore o del lavoratore. È possibile registrare più compensazioni parziali, anche in contanti e senza allegato, oppure con bonifico/carta/altro metodo e documento facoltativo. Il sistema mantiene importo originario, totale compensato e residuo; impedisce di compensare oltre il saldo disponibile. Il residuo può essere lasciato nel cedolino del mese della spesa, riportato integralmente a un mese successivo oppure rateizzato su più mesi indicando il numero di rate o l'importo della rata. Le compensazioni manuali restano possibili nei mesi successivi quando esiste un piano di riporto/rateizzazione e riducono le quote future ancora aperte. Le quote già confluite in un cedolino sono consolidate e non possono essere compensate una seconda volta. In questo modo una spesa da €120 compensata per €40 e poi €30 produce un residuo di €50 nel cedolino.

### Tipologie di ore e ferie (r60)
- **Ore ordinarie**: retribuite per default; possono essere marcate non retribuite.
- **Ore straordinarie**: retribuite per default; usano la tariffa vigente oppure un override valido solo per la singola registrazione.
- **Malattia**: dalla r62 ripristina la dicitura corretta ed è gestita esclusivamente in giorni di calendario.
- **Ore permesso**: retribuite per default, con possibilità di marcarle non retribuite.
- **Ferie**: sono sempre espresse e rendicontate in giorni, mai come tipologia di ore.


### Permessi per categoria e convivenza (r61)
- anagrafica lavoratore: convivenza, regime ridotto art. 14(2) e carica sindacale rilevante;
- categorie CCNL per visite mediche, rinnovo permesso di soggiorno, ricongiungimento familiare, assistenza familiare con grave disabilità, lutto, nascita figlio, formazione, formazione Ebincolf e permessi sindacali;
- categoria `Altro` disponibile per permessi non retribuiti;
- motore di regole con decorrenza storica: CCNL previgente e CCNL 2025-2028;
- monte comune art. 19 calcolato in base a convivenza e ore settimanali;
- overview e report espongono utilizzo mensile/annuo, disponibilità e residui per categoria.


### Malattia in giorni e miglior favore (r62)
- Malattia sempre espressa in giorni di calendario, senza orari.
- Regole contrattuali versionate per periodo con 10/45/180 giorni di conservazione del posto e 8/10/15 giorni retribuibili in base all'anzianità; primi 3 giorni al 50%, dal 4° al 100%.
- Possibilità per il datore di retribuire volontariamente malattia e permessi oltre il limite contrattuale, con eccedenza separata.
- Overview con icona su ogni indicatore e stato cromatico per gli indicatori soggetti a limite.
