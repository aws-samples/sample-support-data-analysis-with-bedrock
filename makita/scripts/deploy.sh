#!/usr/bin/env bash
set -euo pipefail

# MAKITA Deploy Script
#
# Usage:
#   ./scripts/deploy.sh              Deploy all stacks in order
#   ./scripts/deploy.sh primary      Deploy primary stack only (us-east-1)
#   ./scripts/deploy.sh replica      Deploy replica stack only (us-west-2)
#   ./scripts/deploy.sh agentcore    Deploy AgentCore via Python script (us-east-1)
#   ./scripts/deploy.sh devops-agent Deploy DevOps Agent Space (us-east-1)
#   ./scripts/deploy.sh kiro-agent   Deploy Kiro agent config for AgentCore Gateway
#   ./scripts/deploy.sh all          Deploy all stacks in order (same as no args)

PRIMARY_REGION="us-east-1"
DR_REGION="us-west-2"
PRIMARY_STACK="makita-stack"
REPLICA_STACK="makita-replica-stack"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${SCRIPT_DIR}/../infrastructure"
TARGET="${1:-all}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

cleanup_failed_stack() {
  local stack_name="$1"
  local region="$2"
  local status
  status=$(aws cloudformation describe-stacks \
    --stack-name "${stack_name}" \
    --region "${region}" \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

  if [[ "${status}" == "CREATE_FAILED" ]] || [[ "${status}" == "ROLLBACK_COMPLETE" ]] || [[ "${status}" == "ROLLBACK_FAILED" ]]; then
    echo "       Found ${stack_name} in ${status} state, cleaning up..."
    for i in 1 2 3; do
      aws cloudformation delete-stack \
        --stack-name "${stack_name}" \
        --region "${region}" 2>/dev/null || true
      for _ in $(seq 1 30); do
        local s
        s=$(aws cloudformation describe-stacks \
          --stack-name "${stack_name}" \
          --region "${region}" \
          --query "Stacks[0].StackStatus" \
          --output text 2>/dev/null || echo "GONE")
        if [ "${s}" = "GONE" ] || [ "${s}" = "DELETE_COMPLETE" ]; then
          return 0
        fi
        if [ "${s}" = "DELETE_FAILED" ]; then
          echo "       Delete failed (attempt ${i}), retrying..."
          break
        fi
        sleep 10
      done
    done
  fi
}

deploy_or_create_stack() {
  local stack_name="$1"
  local template="$2"
  local region="$3"
  shift 3
  # Remaining args are passed as-is to both create-stack and deploy.
  # For create-stack, convert --parameter-overrides to --parameters format.
  local deploy_args=("$@")

  local status
  status=$(aws cloudformation describe-stacks \
    --stack-name "${stack_name}" \
    --region "${region}" \
    --query "Stacks[0].StackStatus" \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

  if [ "${status}" = "DOES_NOT_EXIST" ]; then
    # Build create-stack args, converting --parameter-overrides to --parameters
    local create_args=()
    local i=0
    while [ $i -lt ${#deploy_args[@]} ]; do
      if [ "${deploy_args[$i]}" = "--parameter-overrides" ]; then
        i=$((i + 1))
        local params=()
        while [ $i -lt ${#deploy_args[@]} ] && [[ "${deploy_args[$i]}" != --* ]]; do
          local key="${deploy_args[$i]%%=*}"
          local val="${deploy_args[$i]#*=}"
          params+=("ParameterKey=${key},ParameterValue=${val}")
          i=$((i + 1))
        done
        create_args+=(--parameters "${params[@]}")
      else
        create_args+=("${deploy_args[$i]}")
        i=$((i + 1))
      fi
    done

    aws cloudformation create-stack \
      --template-body "file://${template}" \
      --stack-name "${stack_name}" \
      --region "${region}" \
      --disable-rollback \
      --tags Key=proj,Value=makita Key=auto-delete,Value=no Key=Env,Value=prod1 \
      "${create_args[@]}"
    echo "       Waiting for ${stack_name} to complete..."
    aws cloudformation wait stack-create-complete \
      --stack-name "${stack_name}" \
      --region "${region}"
  else
    aws cloudformation deploy \
      --template-file "${template}" \
      --stack-name "${stack_name}" \
      --region "${region}" \
      --no-fail-on-empty-changeset \
      --tags proj=makita auto-delete=no Env=prod1 \
      "${deploy_args[@]}"
    aws cloudformation wait stack-update-complete \
      --stack-name "${stack_name}" \
      --region "${region}" 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# Stack deploy functions
# ---------------------------------------------------------------------------

deploy_primary() {
  echo "[primary] Deploying ${PRIMARY_STACK} to ${PRIMARY_REGION}..."
  cleanup_failed_stack "${PRIMARY_STACK}" "${PRIMARY_REGION}"
  deploy_or_create_stack "${PRIMARY_STACK}" "${INFRA_DIR}/makita-stack.yaml" \
    "${PRIMARY_REGION}" --capabilities CAPABILITY_NAMED_IAM
  echo "[primary] Done."
}

deploy_replica() {
  echo "[replica] Retrieving primary instance ARN..."
  local primary_arn
  primary_arn=$(aws cloudformation describe-stacks \
    --stack-name "${PRIMARY_STACK}" \
    --region "${PRIMARY_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='PrimaryInstanceArn'].OutputValue" \
    --output text)

  if [ -z "${primary_arn}" ] || [ "${primary_arn}" = "None" ]; then
    echo "ERROR: Could not retrieve PrimaryInstanceArn. Deploy the primary stack first."
    exit 1
  fi
  echo "         Primary ARN: ${primary_arn}"

  echo "[replica] Deploying ${REPLICA_STACK} to ${DR_REGION}..."
  cleanup_failed_stack "${REPLICA_STACK}" "${DR_REGION}"
  deploy_or_create_stack "${REPLICA_STACK}" "${INFRA_DIR}/makita-replica-stack.yaml" \
    "${DR_REGION}" --parameter-overrides "PrimaryInstanceArn=${primary_arn}"
  echo "[replica] Done."

  # Update primary stack with replica endpoint
  echo "[replica] Updating primary stack with replica endpoint..."
  local replica_endpoint
  replica_endpoint=$(aws cloudformation describe-stacks \
    --stack-name "${REPLICA_STACK}" \
    --region "${DR_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='ReplicaEndpoint'].OutputValue" \
    --output text)

  if [ -z "${replica_endpoint}" ] || [ "${replica_endpoint}" = "None" ]; then
    echo "ERROR: Could not retrieve ReplicaEndpoint from ${REPLICA_STACK}."
    exit 1
  fi

  aws cloudformation deploy \
    --template-file "${INFRA_DIR}/makita-stack.yaml" \
    --stack-name "${PRIMARY_STACK}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${PRIMARY_REGION}" \
    --parameter-overrides "ReplicaEndpoint=${replica_endpoint}" \
    --no-fail-on-empty-changeset
  echo "         Replica endpoint: ${replica_endpoint}"
}

deploy_agentcore() {
  echo "[agentcore] Deploying AgentCore resources via Python script..."
  .venv/bin/python scripts/deploy_agentcore.py
  echo "[agentcore] Done."
}

deploy_devops_agent() {
  echo "[devops-agent] Deploying DevOps Agent Space via Python script..."
  .venv/bin/python scripts/deploy_devops_agent.py
  echo "[devops-agent] Done."
}

deploy_kiro_agent() {
  echo "[kiro-agent] Deploying Kiro agent config via Python script..."
  .venv/bin/python scripts/deploy_kiro_agent.py
  echo "[kiro-agent] Done."
}

print_summary() {
  echo ""
  echo "=== Deployment Summary ==="
  echo ""
  local pe re
  pe=$(aws cloudformation describe-stacks \
    --stack-name "${PRIMARY_STACK}" --region "${PRIMARY_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='PrimaryEndpoint'].OutputValue" \
    --output text 2>/dev/null || echo "N/A")
  re=$(aws cloudformation describe-stacks \
    --stack-name "${REPLICA_STACK}" --region "${DR_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='ReplicaEndpoint'].OutputValue" \
    --output text 2>/dev/null || echo "N/A")
  echo "Primary endpoint: ${pe}"
  echo "Replica endpoint: ${re}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

echo "=== MAKITA Deployment (target: ${TARGET}) ==="
echo ""

case "${TARGET}" in
  primary)
    deploy_primary
    ;;
  replica)
    deploy_replica
    ;;
  agentcore)
    deploy_agentcore
    ;;
  devops-agent)
    deploy_devops_agent
    ;;
  kiro-agent)
    deploy_kiro_agent
    ;;
  all)
    deploy_primary
    deploy_replica
    deploy_agentcore
    deploy_devops_agent
    print_summary
    ;;
  *)
    echo "Usage: $0 [primary|replica|agentcore|devops-agent|kiro-agent|all]"
    echo ""
    echo "  primary       Deploy primary stack (us-east-1)"
    echo "  replica       Deploy replica stack (us-west-2) + update primary"
    echo "  agentcore     Deploy AgentCore Runtimes + Gateway (us-east-1)"
    echo "  devops-agent  Deploy DevOps Agent Space (us-east-1)"
    echo "  kiro-agent    Deploy Kiro agent config for AgentCore Gateway"
    echo "  all           Deploy all (default)"
    exit 1
    ;;
esac
