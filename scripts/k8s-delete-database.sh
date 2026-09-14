#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
kubectl delete -f kubernetes/database.yaml --ignore-not-found
