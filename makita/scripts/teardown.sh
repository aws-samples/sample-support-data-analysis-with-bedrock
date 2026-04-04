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
