# Aggiornamento a PostgreSQL 18.6

Colf Manager r25 usa `postgres:18.6-alpine` per le nuove installazioni.

## Importante: installazioni PostgreSQL 17 esistenti

PostgreSQL 18 è un aggiornamento di versione major. **Non** avviare semplicemente il container PostgreSQL 18 sulla directory dati di PostgreSQL 17.

L'immagine ufficiale PostgreSQL 18 modifica inoltre la struttura dello storage:

- PostgreSQL 17 e precedenti: `PGDATA=/var/lib/postgresql/data`
- PostgreSQL 18: `PGDATA=/var/lib/postgresql/18/docker`
- mount del volume PostgreSQL 18: `/var/lib/postgresql`

Prima di passare una base dati esistente a PostgreSQL 18 usare un dump/restore logico oppure `pg_upgrade`.

## Procedura sicura consigliata

1. Bloccare le scritture su Colf Manager.
2. Creare e verificare un backup logico PostgreSQL 17 con `pg_dump -Fc` (o `pg_dumpall` quando opportuno).
3. Conservare intatto il vecchio volume/PVC PostgreSQL 17 fino alla verifica della migrazione.
4. Creare un nuovo volume/PVC dati per PostgreSQL 18.
5. Avviare PostgreSQL 18.6 sul nuovo volume vuoto.
6. Ripristinare il dump con `pg_restore`.
7. Avviare Colf Manager ed eseguire i controlli applicativi/database.
8. Conservare backup/PVC PostgreSQL 17 fino al completamento della verifica funzionale.

In Kubernetes non riutilizzare il vecchio PVC PostgreSQL 17 come directory dati PostgreSQL 18 senza una procedura supportata di major upgrade.
