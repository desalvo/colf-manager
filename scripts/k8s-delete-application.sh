#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
kubectl delete -f kubernetes/application.yaml --ignore-not-found
