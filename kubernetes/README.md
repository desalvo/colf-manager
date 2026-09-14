# Kubernetes deployment

The Kubernetes resources are deliberately split so that deleting application or
database workloads does **not** delete persistent storage.

## Files

- `namespace.yaml` — namespace only
- `secret-application.yaml` — application secret and initial admin password
- `secret-database.yaml` — PostgreSQL password
- `pvc-application.yaml` — application data PVC only
- `pvc-database.yaml` — PostgreSQL data and backup PVCs
- `application.yaml` — application Deployment and Service
- `database.yaml` — PostgreSQL Deployment and Service
- `backup.yaml` — PostgreSQL backup CronJob
- `network-policy.yaml` — PostgreSQL ingress policy
- `ingress.yaml` — public ingress
- `kustomization.yaml` — complete installation convenience manifest

## Important persistence behavior

Deleting `application.yaml` removes only the application Deployment and Service.
It does not remove `app-data`.

Deleting `database.yaml` removes only the PostgreSQL Deployment and Service.
It does not remove `postgres-data` or `backup-data`.

To remove only application persistent data:

```bash
kubectl delete -f kubernetes/pvc-application.yaml
```

This does not touch PostgreSQL or backup PVCs.

To remove database persistent data (destructive):

```bash
kubectl delete -f kubernetes/pvc-database.yaml
```

Do not use `kubectl delete -k kubernetes` unless you intend to remove **all**
resources including both application and database PVCs.

## Install

Edit both Secret files before applying them.

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

Or install everything with:

```bash
kubectl apply -k kubernetes
```

## Independent removal

Application workloads only:

```bash
kubectl delete -f kubernetes/application.yaml
```

Database workload only:

```bash
kubectl delete -f kubernetes/database.yaml
```

Application PVC only:

```bash
kubectl delete -f kubernetes/pvc-application.yaml
```

Database PVCs only (destructive):

```bash
kubectl delete -f kubernetes/pvc-database.yaml
```

Application Secret only:

```bash
kubectl delete -f kubernetes/secret-application.yaml
```

Database Secret only:

```bash
kubectl delete -f kubernetes/secret-database.yaml
```
