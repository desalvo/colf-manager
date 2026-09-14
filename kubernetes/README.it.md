# Deployment Kubernetes

Le risorse Kubernetes sono separate intenzionalmente per evitare che la
rimozione dei workload dell'applicazione o del database elimini anche i dati
persistenti.

## File

- `namespace.yaml` — namespace
- `secret-application.yaml` — secret applicativo e password admin iniziale
- `secret-database.yaml` — password PostgreSQL
- `pvc-application.yaml` — solo PVC dati applicazione
- `pvc-database.yaml` — PVC dati PostgreSQL e backup
- `application.yaml` — Deployment e Service applicazione
- `database.yaml` — Deployment e Service PostgreSQL
- `backup.yaml` — CronJob backup PostgreSQL
- `network-policy.yaml` — policy di accesso a PostgreSQL
- `ingress.yaml` — Ingress pubblico
- `kustomization.yaml` — installazione completa opzionale

## Persistenza

La cancellazione di `application.yaml` non elimina `app-data`.

La cancellazione di `database.yaml` non elimina `postgres-data` né
`backup-data`.

Per eliminare esclusivamente il PVC applicativo:

```bash
kubectl delete -f kubernetes/pvc-application.yaml
```

Questo comando non tocca i PVC PostgreSQL.

Per eliminare i PVC del database, operazione distruttiva:

```bash
kubectl delete -f kubernetes/pvc-database.yaml
```

## Installazione

Modificare entrambi i file Secret prima dell'applicazione:

```bash
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/secret-database.yaml
kubectl apply -f kubernetes/secret-application.yaml
kubectl apply -f kubernetes/pvc-database.yaml
kubectl apply -f kubernetes/pvc-application.yaml
kubectl apply -f kubernetes/database.yaml
kubectl apply -f kubernetes/application.yaml
kubectl apply -f kubernetes/backup.yaml
kubectl apply -f kubernetes/network-policy.yaml
kubectl apply -f kubernetes/ingress.yaml
```

In alternativa:

```bash
kubectl apply -k kubernetes
```

## Rimozioni indipendenti

Solo workload applicativo:

```bash
kubectl delete -f kubernetes/application.yaml
```

Solo workload database:

```bash
kubectl delete -f kubernetes/database.yaml
```

Solo PVC applicativo:

```bash
kubectl delete -f kubernetes/pvc-application.yaml
```

Solo PVC database e backup:

```bash
kubectl delete -f kubernetes/pvc-database.yaml
```

Solo Secret applicazione:

```bash
kubectl delete -f kubernetes/secret-application.yaml
```

Solo Secret database:

```bash
kubectl delete -f kubernetes/secret-database.yaml
```

> `kubectl delete -k kubernetes` elimina intenzionalmente l'intero stack,
> compresi tutti i PVC.


## Security context applicazione

L'immagine `desalvo/colf-manager` usa in modo deterministico l'utente non-root
`colf-manager` con UID/GID 10001. Il Deployment applicativo e il CronJob di
manutenzione impostano quindi esplicitamente `runAsUser: 10001`,
`runAsGroup: 10001` e `fsGroup: 10001`. Questo evita il rifiuto kubelet
`image has non-numeric user, cannot verify user is non-root` mantenendo
`runAsNonRoot: true`, `allowPrivilegeEscalation: false` e `capabilities.drop: [ALL]`.

## Security context PostgreSQL

L'immagine `postgres:18.6-alpine` usa l'account Alpine `postgres` con UID/GID 70.
Il Pod database viene quindi eseguito esplicitamente con UID/GID 70 e `fsGroup: 70`.
`/var/run/postgresql` usa un volume `emptyDir`, così PostgreSQL non root può creare il
socket Unix senza richiedere capability `chown`/`chmod`. Il container mantiene
`allowPrivilegeEscalation: false` e continua a rimuovere tutte le capability Linux.

Per una nuova installazione r34 questo security context è pronto per PostgreSQL 18.6.
Se il PVC esistente contiene un cluster PostgreSQL 17, **non** applicare semplicemente il workload
PostgreSQL 18 su quel PVC. Eseguire la migrazione major 17 → 18 descritta in
`POSTGRESQL-18-UPGRADE.it.md`, preferibilmente ripristinando su un nuovo PVC PostgreSQL 18.
