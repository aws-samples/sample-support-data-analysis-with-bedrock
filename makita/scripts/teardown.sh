#!/usr/bin/env bash
set -euo pipefail

# MAKITA Teardown Script
# Deletes all MAKITA resources:
#   0. AgentCore resources (Runtimes, Gateway) via deploy_agentcore.py --teardown
#   1. Replica stack (us-west-2) — must be deleted before primary
#   2. Primary stack (us-east-1)

PRIMARY_REGION="us-east-1"
DR_REGION="us-west-2"
PRIMARY_STACK="makita-stack"
REPLICA_STACK="makita-replica-stack"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== MAKITA Teardown ==="
echo ""

# --- Step 0: Delete AgentCore resources ---
echo "[0/3] Tearing down DevOps Agent Space..."
PYTHON="${SCRIPT_DIR}/../.venv/bin/python"
if [ -f "${PYTHON}" ]; then
  "${PYTHON}" "${SCRIPT_DIR}/deploy_devops_agent.py" --teardown || true
else
  echo "       Python venv not found, skipping."
fi

echo "[1/3] Tearing down AgentCore resources..."
if [ -f "${PYTHON}" ]; then
  "${PYTHON}" "${SCRIPT_DIR}/deploy_agentcore.py" --teardown || true
else
  echo "       Python venv not found, skipping AgentCore teardown."
fi

# --- Step 2: Delete replica stack ---
echo "[2/3] Deleting replica stack in ${DR_REGION}..."
aws cloudformation delete-stack \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" 2>/dev/null || true

echo "       Waiting for replica stack deletion..."
aws cloudformation wait stack-delete-complete \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" 2>/dev/null || true

echo "       Replica stack deleted."

# --- Step 3: Delete primary stack ---
echo "[3/3] Deleting primary stack in ${PRIMARY_REGION}..."
aws cloudformation delete-stack \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}"

echo "       Waiting for primary stack deletion..."
aws cloudformation wait stack-delete-complete \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}"

echo ""
echo "=== Teardown complete ==="
