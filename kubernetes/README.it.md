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
