#!/bin/bash
# Attach MAKITA IAM permissions to AgentCore runtime roles.
#
# The agentcore CLI creates its own IAM roles for each runtime.
# This script attaches the RDS/SSM permissions needed by the MCP servers.

set -euo pipefail

REGION="us-east-1"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

POLICY_DOC=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SSMReadWrite",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter"],
      "Resource": "arn:aws:ssm:*:${ACCOUNT}:parameter/makita/*"
    },
    {
      "Sid": "RDS",
      "Effect": "Allow",
      "Action": ["rds:DescribeDBInstances", "rds:DescribeDBClusters", "rds:PromoteReadReplica", "rds:RebootDBInstance"],
      "Resource": ["arn:aws:rds:*:${ACCOUNT}:db:makita-*", "arn:aws:rds:*:${ACCOUNT}:cluster:makita-*"]
    }
  ]
}
EOF
)

echo "Attaching makita-db-permissions to AgentCore runtime roles..."
for NAME in makitapgfailover makitapgprecheck makitapgpostcheck; do
  RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes --region $REGION \
    --query "agentRuntimes[?agentRuntimeName=='${NAME}'].agentRuntimeId" --output text 2>/dev/null)
  [ -z "$RUNTIME_ID" ] || [ "$RUNTIME_ID" = "None" ] && { echo "  SKIP: ${NAME} not found"; continue; }

  ROLE_ARN=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$RUNTIME_ID" --region $REGION --query "roleArn" --output text)
  ROLE_NAME=$(echo "$ROLE_ARN" | sed 's|.*/||')

  aws iam put-role-policy --role-name "$ROLE_NAME" \
    --policy-name "makita-db-permissions" --policy-document "$POLICY_DOC"
  echo "  OK: ${NAME} → ${ROLE_NAME}"
done
echo "Done"
