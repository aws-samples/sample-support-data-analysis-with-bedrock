#!/usr/bin/env bash
set -euo pipefail

# MAKITA Deploy Script
# Deploys both CloudFormation stacks in order:
#   1. Primary stack (us-east-1) — RDS primary, SSM, IAM, AgentCore, Guardrails, Dashboard
#   2. Replica stack (us-west-2) — Cross-region RDS read replica
#   3. Updates primary stack with the replica endpoint

PRIMARY_REGION="us-east-1"
DR_REGION="us-west-2"
PRIMARY_STACK="makita-stack"
REPLICA_STACK="makita-replica-stack"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${SCRIPT_DIR}/../infrastructure"

echo "=== MAKITA Deployment ==="
echo ""

# --- Step 1: Deploy primary stack ---
echo "[1/4] Deploying primary stack to ${PRIMARY_REGION}..."
aws cloudformation deploy \
  --template-file "${INFRA_DIR}/makita-stack.yaml" \
  --stack-name "${PRIMARY_STACK}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${PRIMARY_REGION}" \
  --no-fail-on-empty-changeset

echo "       Waiting for primary stack to complete..."
aws cloudformation wait stack-create-complete \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}" 2>/dev/null || true

# --- Step 2: Get primary instance ARN ---
echo "[2/4] Retrieving primary instance ARN..."
PRIMARY_ARN=$(aws cloudformation describe-stacks \
  --stack-name "${PRIMARY_STACK}" \
  --region "${PRIMARY_REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='PrimaryInstanceArn'].OutputValue" \
  --output text)

if [ -z "${PRIMARY_ARN}" ] || [ "${PRIMARY_ARN}" = "None" ]; then
  echo "ERROR: Could not retrieve PrimaryInstanceArn from ${PRIMARY_STACK}."
  exit 1
fi
echo "       Primary ARN: ${PRIMARY_ARN}"

# --- Step 3: Deploy replica stack ---
echo "[3/4] Deploying replica stack to ${DR_REGION}..."
aws cloudformation deploy \
  --template-file "${INFRA_DIR}/makita-replica-stack.yaml" \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" \
  --parameter-overrides "PrimaryInstanceArn=${PRIMARY_ARN}" \
  --no-fail-on-empty-changeset

echo "       Waiting for replica stack to complete..."
aws cloudformation wait stack-create-complete \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" 2>/dev/null || true

# --- Step 4: Update primary stack with replica endpoint ---
echo "[4/4] Updating primary stack with replica endpoint..."
REPLICA_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name "${REPLICA_STACK}" \
  --region "${DR_REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='ReplicaEndpoint'].OutputValue" \
  --output text)

if [ -z "${REPLICA_ENDPOINT}" ] || [ "${REPLICA_ENDPOINT}" = "None" ]; then
  echo "ERROR: Could not retrieve ReplicaEndpoint from ${REPLICA_STACK}."
  exit 1
fi
echo "       Replica endpoint: ${REPLICA_ENDPOINT}"

aws cloudformation deploy \
  --template-file "${INFRA_DIR}/makita-stack.yaml" \
  --stack-name "${PRIMARY_STACK}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${PRIMARY_REGION}" \
  --parameter-overrides "ReplicaEndpoint=${REPLICA_ENDPOINT}" \
  --no-fail-on-empty-changeset

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Primary endpoint:  $(aws cloudformation describe-stacks \
  --stack-name "${PRIMARY_STACK}" --region "${PRIMARY_REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='PrimaryEndpoint'].OutputValue" --output text)"
echo "Replica endpoint:  ${REPLICA_ENDPOINT}"
echo "Dashboard URL:     $(aws cloudformation describe-stacks \
  --stack-name "${PRIMARY_STACK}" --region "${PRIMARY_REGION}" \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" --output text)"
