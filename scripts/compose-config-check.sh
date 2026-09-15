#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

env \
  POSTGRES_PASSWORD='validation-only-postgres-password' \
  COLF_MANAGER_SECRET_KEY='validation-only-secret-key-0123456789abcdef0123456789abcdef' \
  COLF_MANAGER_ADMIN_PASSWORD='Validation-admin-password-1234' \
  docker compose config --quiet
