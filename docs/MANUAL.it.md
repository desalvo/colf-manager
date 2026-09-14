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

Creare la lavoratore e la tariffa iniziale, inserire le ore dal calendario, registrare ferie/permessi/malattia, inserire spese e documenti e usare la sezione Report per i riepiloghi.

## TFR e adempimenti

L'accantonamento gestionale usa un divisore configurabile, inizialmente 13,5, sulla retribuzione registrata. La liquidazione effettiva può richiedere rivalutazione, inclusione/esclusione di voci e trattamento fiscale. Verificare sempre fonti ufficiali e contratto applicato.

## Sicurezza e privacy

I dati sono personali e possono includere informazioni sanitarie. Limitare gli accessi, usare HTTPS, cifrare backup e dischi, applicare una retention documentata e registrare solo i dati necessari.

## Build e release

`scripts/release-check.sh` esegue lint, test/copertura, Bandit, audit dipendenze, manuali IT/EN, wheel/sdist, `twine check`, SBOM CycloneDX e verifica pacchetto. La CI usa Python 3.11-3.13, Gitleaks, CodeQL, Trivy e validazione Docker/Kubernetes.

## Anagrafiche e cancellazione

Lavoratori e datori di lavoro possono essere inseriti, visualizzati, modificati e cancellati definitivamente. Indirizzo, telefono ed e-mail sono opzionali. La cancellazione totale di un lavoratore elimina anche ore, assenze, tariffe, spese e documenti associati; la cancellazione di un datore scollega i lavoratori ma non li elimina.

## Ferie automatiche

Il motore usa 26 giorni lavorativi annui e la maturazione in dodicesimi. Una frazione di servizio pari o superiore a 15 giorni nel mese vale come mese intero. Il conteggio ferie considera dal lunedì al sabato ed esclude domeniche e festività nazionali; la festività del patrono locale va verificata separatamente. Per i rapporti a ore, il valore orario di una giornata di ferie usa le ore medie mensili divise per 26. Per ogni lavoratore si può abilitare l'uso anticipato delle ferie che matureranno entro il 31 dicembre.

## TFR e report annuali

Per rapporti dal 1990, il prospetto TFR usa la retribuzione utile registrata, include la quota di tredicesima stimata e divide per 13,5. La quota maturata nell'anno non viene rivalutata; le quote pregresse rimaste accantonate richiedono la rivalutazione prevista dall'art. 2120 c.c. (1,5% fisso più 75% dell'aumento FOI ISTAT). Sono disponibili PDF per cedolino mensile, cedolino globale annuale, certificazione/CU di cortesia, TFR annuale e andamento mensile di ore e retribuzioni. Le regole 2025 e 2026 sono marcate come verificate nel pacchetto; per altri anni il report richiede esplicitamente una verifica delle fonti ufficiali.

## CU di cortesia

Il datore di lavoro domestico privato non è normalmente un sostituto d'imposta. Il documento prodotto è quindi una certificazione di cortesia delle retribuzioni registrate e non il modello CU telematico trasmesso all'Agenzia delle Entrate.

## Limiti

Il software non sostituisce un consulente del lavoro, non effettua versamenti o comunicazioni e non certifica la correttezza legale dei parametri inseriti.

## Tredicesima, TFR e contribuzione

La sezione Report genera anche il cedolino specifico della tredicesima e un prospetto cumulativo tredicesima + TFR, con formula, periodo di riferimento e note sulle regole applicate. Se nell'anagrafica del lavoratore sono presenti posizione INPS e numero contratto, i PDF includono la stima dei contributi INPS e, separatamente, una stima IRPEF informativa. L'opzione "datore si fa carico di tutte le tasse" azzera nei prospetti la quota economica residua attribuita al lavoratore, senza trasformare il datore domestico in sostituto d'imposta.


## Luoghi

La voce **Luoghi** permette di aggiungere, visualizzare, modificare e cancellare i luoghi utilizzati per il lavoro. Ogni luogo può avere un nome, un indirizzo opzionale e note. Nel calendario le nuove ore vengono associate a uno dei luoghi registrati. Per preservare lo storico, ogni registrazione conserva anche una copia testuale del luogo: modificare o cancellare l'anagrafica di un luogo non modifica le ore già registrate.


## Archivio, report e backup completo

I report PDF generati vengono conservati nell'applicazione sul volume persistente e possono essere riscaricati o cancellati manualmente. Anche i documenti caricati possono essere cancellati manualmente. Gli amministratori dispongono di un export ZIP completo di database, documenti referenziati e report archiviati e di un import completo con conferma esplicita. I file presenti sul volume ma non più referenziati dal database vengono eliminati automaticamente dal servizio di manutenzione dopo la retention configurata.

La Panoramica può essere consultata scegliendo mese e anno. Il calendario consente di navigare nei mesi precedenti e registrare retroattivamente le ore nel periodo visualizzato.

## Novità r31: interfaccia, calendario, posta e impostazioni

La barra laterale è sempre disponibile nelle viste desktop, incluso il calendario, e può essere minimizzata in una barra compatta a icone. Su smartphone e tablet diventa un drawer accessibile tramite hamburger e richiudibile toccando fuori dal menu.

Il calendario utilizza una vista settimanale a scala oraria: ogni registrazione occupa uno spazio proporzionale alla durata effettiva. I colori sono derivati dalla combinazione di lavoratore, datore e luogo. Le registrazioni possono essere modificate, ridimensionate, spostate o cancellate direttamente dal calendario. La colonna destra propone gli ultimi inserimenti ricorrenti (limite configurabile, predefinito 10), trascinabili su giorno e orario per creare rapidamente nuove ore.

Le tariffe orarie e le spese dispongono di storico completo con inserimento, modifica e cancellazione. Le spese del lavoratore o del datore vengono riportate nei cedolini/report nel mese in cui sono state registrate.

La pagina **Impostazioni** (icona ingranaggio) raccoglie il limite degli inserimenti rapidi, la configurazione SMTP/SMTPS e i metodi di autenticazione disponibili. Documenti, report archiviati e notifiche possono essere inviati via e-mail direttamente dall'applicazione.


Local packaged photographic assets are bundled in `src/colf_manager/static/heroes/`.


## Novità r32: approvazione e firme nei report
I report possono includere una sezione di approvazione con firma del lavoratore, del datore di lavoro, di entrambi oppure nessuna firma. I nomi sono precompilati automaticamente. Luogo e data sono modificabili prima della generazione; la data proposta è quella di generazione del report. Le informazioni di firma vengono incorporate nel PDF archiviato. Gli hero e gli elementi fotografici locali restano inclusi nel pacchetto in `src/colf_manager/static/heroes/`.

## Calendario: ore, ferie e malattia

Dalla r37 la stessa finestra del calendario consente di scegliere **Ore retribuite**, **Ferie** o **Malattia**. Ferie e malattia sono registrate come intervalli orari e possono coesistere nello stesso giorno con ore retribuite. Per periodi di più giorni, la data iniziale e finale sono sempre comprese. Le ferie sono mostrate in colore dedicato, la malattia in un secondo colore dedicato; le ore retribuite mantengono un colore stabile determinato dalla combinazione datore/lavoratore/luogo. Cliccando un intervallo è possibile visualizzarlo, modificarlo o eliminarlo.

## Novità r40: drag & drop e andamento ore per luogo

Nel calendario gli inserimenti recenti sono disponibili in una colonna dedicata a destra sotto forma di elementi grafici trascinabili. Il rilascio su un nuovo giorno conserva tipo di registrazione, orari di inizio/fine, lavoratore, relazione con il datore, luogo e pausa; per ferie e malattia conserva anche lo stato retribuito e le ore pagate configurate. I colori degli eventi sono coerenti nelle viste mese, settimana e giorno.

Nella pagina Report, quando è presente un solo lavoratore questo viene selezionato automaticamente. È inoltre disponibile il PDF **Andamento ore per luogo**, con totale annuale e dettaglio mensile delle ore retribuite distinte per luogo.
