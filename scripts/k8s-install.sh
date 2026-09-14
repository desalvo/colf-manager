#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

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
