#!/usr/bin/env bash
set -euo pipefail

# MAKITA Teardown Script
# Deletes both CloudFormation stacks in the correct order:
#   1. Replica stack (us-west-2) first — must be deleted before primary
#   2. Primary stack (us-east-1)

PRIMARY_REGION="us-east-1"
DR_REGION="us-west-2"
PRIMARY_STACK="makita-stack"
REPLICA_STACK="makita-replica-stack"

echo "=== MAKITA Teardown ==="
echo ""

# --- Step 0: Delete AgentCore resources ---
echo "[0/2] Tearing down AgentCore resources..."
if [ -f ".venv/bin/python" ]; then
  .venv/bin/python scripts/deploy_agentcore.py --teardown 2>/dev/null || true
fi

# Also delete the CloudFormation stack if it exists
AGENTCORE_STACK="makita-agentcore-stack"
if aws cloudformation describe-stacks --stack-name "${AGENTCORE_STACK}" --region "${PRIMARY_REGION}" >/dev/null 2>&1; then
  echo "       Deleting AgentCore stack in ${PRIMARY_REGION}..."
  aws cloudformation delete-stack \
    --stack-name "${AGENTCORE_STACK}" \
    --region "${PRIMARY_REGION}"
  aws cloudformation wait stack-delete-complete \
    --stack-name "${AGENTCORE_STACK}" \
    --region "${PRIMARY_REGION}"
  echo "       AgentCore stack deleted."
else
  echo "       No AgentCore stack found, skipping."
fi

# --- Step 1: Delete replica stack ---
echo "[1/2] Deleting replica stack in ${DR_REGION}..."
aws cloudformation delete-stack \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" 2>/dev/null || true

echo "       Waiting for replica stack deletion..."
aws cloudformation wait stack-delete-complete \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" 2>/dev/null || true

echo "       Replica stack deleted."

# --- Step 2: Delete primary stack ---
echo "[2/2] Deleting primary stack in ${PRIMARY_REGION}..."
aws cloudformation delete-stack \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}"

echo "       Waiting for primary stack deletion..."
aws cloudformation wait stack-delete-complete \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}"

echo ""
echo "=== Teardown complete ==="
