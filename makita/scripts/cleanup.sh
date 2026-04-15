#!/usr/bin/env bash
set -euo pipefail

# MAKITA Cleanup Script — removes all orphaned resources
REGION="us-east-1"

echo "=== MAKITA Cleanup ==="

# 1. Force delete stuck stacks
echo "[1] Cleaning up CloudFormation stacks..."
for stack in $(aws cloudformation list-stacks --region $REGION \
  --query 'StackSummaries[?starts_with(StackName, `Makita`) && StackStatus!=`DELETE_COMPLETE`].StackName' \
  --output text); do
  echo "  Deleting $stack (status: $(aws cloudformation describe-stacks --stack-name $stack --region $REGION --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo UNKNOWN))"
  STATUS=$(aws cloudformation describe-stacks --stack-name $stack --region $REGION --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo GONE)
  if [ "$STATUS" = "DELETE_FAILED" ] || [ "$STATUS" = "ROLLBACK_FAILED" ]; then
    aws cloudformation delete-stack --stack-name $stack --region $REGION --deletion-mode FORCE_DELETE_STACK || true
  elif [ "$STATUS" != "GONE" ]; then
    aws cloudformation delete-stack --stack-name $stack --region $REGION || true
  fi
done
echo "  Waiting for stack deletions..."
sleep 15

# 2. Delete gateway targets + gateway
echo "[2] Cleaning up AgentCore gateway..."
GW_ID=$(aws bedrock-agentcore-control list-gateways --region $REGION \
  --query 'items[?starts_with(name, `makita`)].gatewayId' --output text 2>/dev/null || echo "")
if [ -n "$GW_ID" ] && [ "$GW_ID" != "None" ]; then
  for tid in $(aws bedrock-agentcore-control list-gateway-targets \
    --gateway-identifier $GW_ID --region $REGION \
    --query 'items[].targetId' --output text 2>/dev/null || echo ""); do
    echo "  Deleting target $tid"
    aws bedrock-agentcore-control delete-gateway-target \
      --gateway-identifier $GW_ID --target-id $tid --region $REGION 2>/dev/null || true
  done
  sleep 10
  echo "  Deleting gateway $GW_ID"
  aws bedrock-agentcore-control delete-gateway \
    --gateway-identifier $GW_ID --region $REGION 2>/dev/null || true
fi

# 3. Delete runtimes
echo "[3] Cleaning up AgentCore runtimes..."
for rt in $(aws bedrock-agentcore-control list-agent-runtimes --region $REGION \
  --query 'agentRuntimes[?starts_with(agentRuntimeName, `makita`)].agentRuntimeId' \
  --output text 2>/dev/null || echo ""); do
  echo "  Deleting runtime $rt"
  aws bedrock-agentcore-control delete-agent-runtime \
    --agent-runtime-id $rt --region $REGION 2>/dev/null || true
done

# 4. Delete guardrails
echo "[4] Cleaning up Bedrock guardrails..."
for gid in $(aws bedrock list-guardrails --region $REGION \
  --query 'guardrails[?starts_with(name, `makita`)].guardrailId' \
  --output text 2>/dev/null || echo ""); do
  echo "  Deleting guardrail $gid"
  aws bedrock delete-guardrail --guardrail-identifier $gid --region $REGION 2>/dev/null || true
done

# 5. Delete IAM roles
echo "[5] Cleaning up IAM roles..."
for role in makita-devops-agent-operator-role makita-failover-role makita-precheck-role makita-postcheck-role; do
  if aws iam get-role --role-name $role 2>/dev/null; then
    for policy_arn in $(aws iam list-attached-role-policies --role-name $role \
      --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || echo ""); do
      aws iam detach-role-policy --role-name $role --policy-arn $policy_arn 2>/dev/null || true
    done
    for policy_name in $(aws iam list-role-policies --role-name $role \
      --query 'PolicyNames[]' --output text 2>/dev/null || echo ""); do
      aws iam delete-role-policy --role-name $role --policy-name $policy_name 2>/dev/null || true
    done
    aws iam delete-role --role-name $role 2>/dev/null || true
    echo "  Deleted role $role"
  fi
done

# 6. Delete log group
echo "[6] Cleaning up CloudWatch log groups..."
aws logs delete-log-group --log-group-name /makita/devops-agent --region $REGION 2>/dev/null || true

# 7. Delete SSM parameters
echo "[7] Cleaning up SSM parameters..."
aws ssm delete-parameters --region $REGION --names \
  /makita/db/primary-endpoint /makita/db/replica-endpoint \
  /makita/db/primary-region /makita/db/dr-region \
  /makita/db/cluster-name /makita/db/replication-status \
  /makita/db/port /makita/mcp/failover-server-arn \
  /makita/mcp/precheck-server-arn /makita/mcp/postcheck-server-arn \
  2>/dev/null || true

# 8. Verify
echo ""
echo "=== Verification ==="
echo "Stacks:"
aws cloudformation list-stacks --region $REGION \
  --query 'StackSummaries[?starts_with(StackName, `Makita`) && StackStatus!=`DELETE_COMPLETE`].{name:StackName, status:StackStatus}'
echo "Runtimes:"
aws bedrock-agentcore-control list-agent-runtimes --region $REGION \
  --query 'agentRuntimes[?starts_with(agentRuntimeName, `makita`)].agentRuntimeName' 2>/dev/null || echo "[]"
echo "Gateways:"
aws bedrock-agentcore-control list-gateways --region $REGION \
  --query 'items[?starts_with(name, `makita`)].name' 2>/dev/null || echo "[]"
echo "Guardrails:"
aws bedrock list-guardrails --region $REGION \
  --query 'guardrails[?starts_with(name, `makita`)].name' 2>/dev/null || echo "[]"
echo ""
echo "=== Cleanup complete ==="
