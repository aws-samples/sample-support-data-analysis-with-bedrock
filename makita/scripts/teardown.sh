#!/usr/bin/env bash
set -euo pipefail

# MAKITA Teardown Script
#
# Deletes all MAKITA resources in reverse deployment order:
#   1. DevOps Agent Space via deploy_devops_agent.py --teardown
#   2. AgentCore resources (Runtimes, Gateway) via deploy_agentcore.py --teardown
#   3. PostgreSQL replica stack (us-west-2) — must be deleted before primary
#   4. PostgreSQL primary stack (us-east-1)
#
# Usage:
#   ./scripts/teardown.sh

PRIMARY_REGION="us-east-1"
DR_REGION="us-west-2"
PRIMARY_STACK="makita-postgresql-stack"
REPLICA_STACK="makita-postgresql-replica-stack"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${SCRIPT_DIR}/../.venv/bin/python"

echo "=== MAKITA Teardown ==="
echo ""

# --- Step 1: Delete DevOps Agent Space ---
echo "[1/4] Tearing down DevOps Agent Space..."
if [ -f "${PYTHON}" ]; then
  "${PYTHON}" "${SCRIPT_DIR}/deploy_devops_agent.py" --teardown || true
else
  echo "       Python venv not found, skipping."
fi

# --- Step 2: Delete AgentCore resources ---
echo "[2/4] Tearing down AgentCore resources..."
if [ -f "${PYTHON}" ]; then
  "${PYTHON}" "${SCRIPT_DIR}/deploy_agentcore.py" --teardown || true
else
  echo "       Python venv not found, skipping AgentCore teardown."
fi

# --- Step 3: Delete PostgreSQL replica stack ---
echo "[3/4] Deleting PostgreSQL replica stack in ${DR_REGION}..."
aws cloudformation delete-stack \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" 2>/dev/null || true

echo "       Waiting for replica stack deletion..."
aws cloudformation wait stack-delete-complete \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" 2>/dev/null || true

echo "       Replica stack deleted."

# --- Step 4: Delete PostgreSQL primary stack ---
echo "[4/4] Deleting PostgreSQL primary stack in ${PRIMARY_REGION}..."
aws cloudformation delete-stack \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}"

echo "       Waiting for primary stack deletion..."
aws cloudformation wait stack-delete-complete \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}"

echo ""
echo "=== Teardown complete ==="
