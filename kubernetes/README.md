# Kubernetes deployment notes

Before applying `colf-manager.yaml`, replace every `CHANGE_ME`, set the Ingress hostname/class and create the TLS secret named `colf-manager-tls` (or change `secretName`). To select a non-default StorageClass, uncomment and set `storageClassName` on all three PVCs before their first creation.

The manifest includes a daily PostgreSQL backup CronJob at 02:17 with 14-day retention on the `backup-data` PVC. Copy backups off-cluster as part of the disaster-recovery policy; a PVC is not an independent backup if the storage backend itself is lost.

For an existing original 1.0.0 database, back it up before deploying this hardened build. The application performs the small compatibility upgrade required for the new security/audit columns. After confirming the application is healthy, establish the Alembic baseline with `flask --app colf_manager.app:create_app db stamp 1000_hardened_baseline` inside an application pod. Future releases should use reviewed Alembic migrations and `flask db upgrade`.

If the ingress controller runs outside the usual setup, adjust ingress class/annotations as required. `COLF_MANAGER_SECURE_COOKIES=1` assumes HTTPS termination at the ingress.
