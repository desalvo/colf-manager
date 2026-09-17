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

## Novità r57: compensazioni, riporto e rateizzazione di spese e rimborsi

Ogni spesa o anticipo mantiene un saldo. È possibile registrare più compensazioni parziali, in contanti, con bonifico, carta, altro metodo elettronico o altro metodo. La documentazione è facoltativa: una compensazione in contanti può essere registrata anche senza ricevuta, restando comunque tracciata nel sistema con data, importo, modalità, note e audit. Il sistema impedisce di compensare oltre il saldo ancora disponibile.

Il residuo può essere lasciato nel cedolino del mese della spesa, riportato integralmente a un mese successivo oppure rateizzato su più mesi. La rateizzazione può essere definita indicando il numero di rate oppure un importo rata; l'ultima rata assorbe automaticamente l'eventuale differenza. Quando esiste un piano di riporto/rateizzazione, sono ammesse anche compensazioni manuali nei mesi successivi e queste riducono le quote future ancora aperte.

Quando un cedolino mensile viene generato, la quota del piano inclusa in quel cedolino viene consolidata. Le quote consolidate non possono essere compensate o riscritte una seconda volta; le sole quote future non consolidate restano modificabili e possono essere ripianificate. Nei report sono distinti importo originario, compensazioni manuali, quote già regolate tramite cedolino e residuo aperto.

La pagina **Impostazioni** (icona ingranaggio) raccoglie il limite degli inserimenti rapidi, la configurazione SMTP/SMTPS e i metodi di autenticazione disponibili. Documenti, report archiviati e notifiche possono essere inviati via e-mail direttamente dall'applicazione.


Local packaged photographic assets are bundled in `src/colf_manager/static/heroes/`.


## Novità r32: approvazione e firme nei report
I report possono includere una sezione di approvazione con firma del lavoratore, del datore di lavoro, di entrambi oppure nessuna firma. I nomi sono precompilati automaticamente. Luogo e data sono modificabili prima della generazione; la data proposta è quella di generazione del report. Le informazioni di firma vengono incorporate nel PDF archiviato. Gli hero e gli elementi fotografici locali restano inclusi nel pacchetto in `src/colf_manager/static/heroes/`.

## Calendario: ore ordinarie, straordinarie, malattia, permessi e ferie

Dalla r62 il calendario distingue **Ore ordinarie**, **Ore straordinarie**, **Malattia**, **Ore permesso** e **Ferie**. Ordinarie e straordinarie sono retribuite per default ma possono essere marcate non retribuite. Le straordinarie usano automaticamente la tariffa oraria vigente alla data della registrazione; è possibile indicare una tariffa diversa valida esclusivamente per quella registrazione. Malattia e permesso sono retribuiti per default e possono essere marcati non retribuiti. Le ferie non sono una tipologia di ore: vengono registrate, mostrate e rendicontate esclusivamente in **giorni**, senza orario di inizio/fine.

## Novità r42: drag & drop e andamento ore per luogo

Nel calendario le scelte rapide drag & drop sono disponibili in una colonna dedicata a destra, ordinate per frequenza d’uso (a parità, prima la più recente). Il rilascio su un nuovo giorno conserva tipo di registrazione, orari di inizio/fine, lavoratore, relazione con il datore, luogo e pausa; per i permessi conserva anche la categoria. I controlli Giorno, Mese e Anno consentono di saltare direttamente a una data specifica senza cambiare la vista calendario selezionata. I colori degli eventi sono coerenti nelle viste mese, settimana e giorno.

Nella pagina Report, quando è presente un solo lavoratore questo viene selezionato automaticamente. È inoltre disponibile il PDF **Andamento ore per luogo**, con totale annuale e dettaglio mensile delle ore retribuite distinte per luogo.

### Indicatori malattia in Panoramica

La Panoramica mostra, per il mese selezionato, le ore malattia retribuite e non retribuite registrate. Mostra inoltre il residuo annuo retribuibile. Il CCNL esprime il massimale in giorni (8, 10 o 15 in funzione dell’anzianità); l’app converte il residuo in ore usando l’orario settimanale diviso per 6. Per periodi non coperti dalle regole contrattuali verificate il valore è mostrato come N/D.


## Novità r47: indirizzi, panoramica ed export

Lavoratori e datori dispongono ora dei campi Città, Provincia e CAP. Nei report il luogo firma proposto usa per default la città del datore di lavoro. La Panoramica usa indicatori più compatti e la sezione Attività del periodo, che include anche il nome del lavoratore, è collassata per default. L'export completo supporta esplicitamente i valori orari (`datetime.time`) presenti nelle registrazioni di calendario.


## Novità r48: sottoscrizioni calendario e impostazioni

In **Impostazioni** è possibile configurare la URL esterna dell'applicazione e attivare una sottoscrizione in sola lettura per il calendario di un singolo lavoratore o di un datore di lavoro. Per ogni calendario attivato vengono mostrati un link **ICS** e un endpoint **CalDAV** protetti da token casuale revocabile. Il calendario del datore aggrega gli eventi dei lavoratori associati. I feed includono ore ordinarie, straordinarie, malattia, permessi e ferie in giorni. Il cambio password personale è ora integrato nella stessa pagina Impostazioni.

## Firme grafiche nei report
Nelle anagrafiche di lavoratore e datore di lavoro è possibile caricare una firma grafica in formato PNG, JPEG, TIFF, WEBP o BMP. Quando il report prevede la firma del soggetto e la firma è registrata, l'immagine viene apposta automaticamente nello spazio firma; in assenza del file resta la linea per la firma manuale. Tutti i PDF riportano inoltre logo di colf-manager, versione/build e autore.

## Pagamenti e quietanze
La voce Pagamenti consente di registrare retribuzioni, contributi INPS, tredicesima, TFR, rimborsi spese e altri pagamenti. Ogni voce può essere Da pagare o Pagato e può includere data di pagamento, periodo di competenza, descrizione, note e allegati. Gli importi ancora da pagare sono evidenziati nell'interfaccia. Per ogni pagamento con stato **Pagato** è disponibile una quietanza PDF professionale che mostra separatamente importo dovuto, importo effettivamente pagato e residuo; se è stata caricata la firma del datore, viene inserita automaticamente nella quietanza. I contributi INPS sono disponibili solo per i lavoratori con posizione INPS registrata. Quando un pagamento viene creato o modificato e interessa un mese per il quale esiste già un cedolino mensile archiviato, il cedolino viene rigenerato con gli importi di pagamento correnti e sostituito nello stesso record di archivio; lo stesso avviene se un pagamento viene riportato a Da pagare o eliminato.

La generazione del cedolino mensile crea automaticamente una voce residua Da pagare per la retribuzione e, quando disponibile il calcolo INPS, una voce contributiva. Le quote già registrate come Pagato vengono mostrate nei report e concorrono al calcolo del residuo. Rigenerare un report aggiorna la voce automatica residua invece di duplicarla.

## Archivio report e backup
Dopo la generazione da interfaccia, la pagina Report viene aggiornata automaticamente e il nuovo documento compare subito nell'archivio. I report archiviati possono essere visualizzati nel browser, scaricati, inviati via e-mail o eliminati. L'export completo include database, documenti, report, firme grafiche, pagamenti e relativi allegati; l'import completo ripristina gli stessi elementi e i collegamenti fra loro.


## Novità r60: modello completo delle tipologie di ore

Le registrazioni di lavoro distinguono ora ore ordinarie e straordinarie. Ogni registrazione ha una flag retribuita/non retribuita; il valore predefinito è retribuita. Le ore straordinarie usano la tariffa vigente, con override opzionale applicato soltanto a quella registrazione. I riepiloghi e i cedolini distinguono ore totali, ordinarie, straordinarie e lavoro non retribuito.

Nella r60 la precedente voce **Malattia** era stata temporaneamente rinominata **Salute**; la r62 ripristina la dicitura **Malattia**. È stata aggiunta **Ore permesso**, retribuita per default e modificabile come non retribuita.

Le **Ferie** restano un istituto espresso in giorni: l'interfaccia non richiede orari, il calendario le visualizza come eventi giornalieri e report/panoramica le espongono sempre in giorni. L'eventuale conversione tecnica necessaria al calcolo economico non viene presentata come monte ore ferie.


## Novità r61: permessi contrattuali per categoria

L'anagrafica del lavoratore registra ora se il rapporto è **convivente** e, quando applicabile, se rientra nel regime di convivenza a orario ridotto dell'art. 14(2) del CCNL. È inoltre possibile indicare la carica in un organismo direttivo sindacale ai fini dei permessi previsti dal contratto.

I permessi sono classificati in: visite mediche documentate, rinnovo del permesso di soggiorno, ricongiungimento familiare, assistenza a familiari con grave disabilità certificata, lutto/comprovata disgrazia familiare, nascita di un figlio per il padre, formazione professionale, formazione Ebincolf e permessi sindacali. Per i permessi **non retribuiti** è disponibile anche la categoria **Altro**.

Il motore applica le regole in base alla data. Nel CCNL in vigore dal 1 novembre 2025 il monte comune dell'art. 19 è pari a 16 ore annue per i conviventi, 12 ore per i conviventi nel regime ridotto art. 14(2), 12 ore per i non conviventi con almeno 30 ore settimanali e viene riproporzionato sotto le 30 ore. Visite mediche, rinnovo del permesso di soggiorno, ricongiungimento familiare e assistenza a familiari con grave disabilità condividono tale monte retribuito. La formazione richiede tempo pieno, contratto a tempo indeterminato e almeno 6 mesi di anzianità nel CCNL 2025-2028; per il periodo precedente il motore applica il requisito di 12 mesi.

Lutto e nascita restano diritti per evento, senza un falso plafond annuo. L'overview, in sezioni chiuse per default, mostra uso retribuito/non retribuito, disponibilità e residui; i report pertinenti riportano gli stessi dati.


## Novità r62: malattia in giorni e indicatori visuali

La malattia è ora registrata esclusivamente in giorni di calendario, senza orari. Il motore seleziona la regola contrattuale vigente per la data: limiti di conservazione del posto e giorni retribuibili sono distinti, con 50% fino al terzo giorno consecutivo e 100% dal quarto. Il datore può autorizzare un trattamento di miglior favore e retribuire giorni di malattia o ore di permesso oltre il limite contrattuale; l'eccedenza resta separata dal diritto residuo. Ogni indicatore dell'overview ha un'icona e, quando esiste un limite, una codifica visuale del livello rispetto alla soglia.

## Pagamenti, spese e firme nei report

I report distinguono gli importi maturati/registrati dai pagamenti effettivamente eseguiti. Nel riepilogo annuale i pagamenti sono mostrati per categoria (retribuzione, contributi INPS, tredicesima, TFR, rimborso spese e altro) e come totale complessivo. Il report "Pagamenti effettuati nell'anno" include tutti i pagamenti con stato Pagato e data di pagamento nell'anno selezionato, con dettaglio per lavoratore, datore, categoria, importo e periodo.

Una quota di spesa già consolidata tramite cedolino può essere riportata allo stato pianificato con "Annulla regolamento" dalla scheda della spesa. La cancellazione di un pagamento rimuove immediatamente quell'importo dai totali pagati e dai successivi report generati.

Se è caricata una firma grafica del lavoratore o del datore, i PDF eliminano il fondo bianco dell'immagine rendendolo trasparente, mantengono le proporzioni e centrano la firma nel relativo campo.

### Imputazione economica delle ferie su più mesi
Per un periodo continuativo che attraversa più mesi, se nel mese iniziale ricadono **massimo 3 giorni di ferie computabili**, l’intera retribuzione ferie è imputata al mese di fine periodo e il riporto è indicato nell’app e nel cedolino. Se nel mese iniziale ricadono **4 o più giorni**, ogni giorno di ferie è imputato economicamente al proprio mese.

## Registro Audit
La voce **Audit**, disponibile agli amministratori, permette di consultare le operazioni registrate dall'applicazione. Sono disponibili ricerca testuale, filtro per data e paginazione. In **Impostazioni → Audit** si configura la retention automatica (12 mesi per default; 0 per disabilitarla). La pulizia manuale può eliminare i record più vecchi di una soglia in giorni oppure conservare soltanto gli ultimi N record. Le operazioni di pulizia manuale vengono registrate nel nuovo storico risultante.
