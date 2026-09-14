#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "WARNING: this permanently deletes PostgreSQL data and backup PVCs." >&2
kubectl delete -f kubernetes/pvc-database.yaml --ignore-not-found
