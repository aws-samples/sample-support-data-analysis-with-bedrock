#!/bin/bash
# Register AgentCore CLI-deployed runtimes as gateway targets.
#
# Run this after `make deploy` (creates gateway) and `make deploy-mcp-servers`
# (creates runtimes). It connects the runtimes to the gateway so DevOps Agent
# can discover the MCP tools.
#
# Usage: ./scripts/register-gateway-targets.sh

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
PROJECT="makita"

echo "=== Registering gateway targets ==="

# Find the gateway
GATEWAY_ID=$(aws bedrock-agentcore-control list-gateways --region "$REGION" \
  --query "items[?starts_with(name, '${PROJECT}')].gatewayId" --output text 2>/dev/null || echo "")

if [ -z "$GATEWAY_ID" ] || [ "$GATEWAY_ID" = "None" ]; then
  echo "[ERROR] No makita gateway found. Run 'make deploy' first."
  exit 1
fi
echo "  Gateway: $GATEWAY_ID"

# Find the OAuth provider ARN
OAUTH_PROVIDER_ARN=$(aws bedrock-agentcore-control list-oauth2-credential-providers --region "$REGION" \
  --query "oauth2CredentialProviders[?starts_with(name, '${PROJECT}')].credentialProviderArn" --output text 2>/dev/null || echo "")

# Get existing targets to avoid duplicates
EXISTING_TARGETS=$(aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier "$GATEWAY_ID" --region "$REGION" \
  --query "items[].name" --output text 2>/dev/null || echo "")

for NAME in makitapgfailover makitapgprecheck makitapgpostcheck; do
  # Find the runtime created by agentcore CLI
  RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes --region "$REGION" \
    --query "agentRuntimes[?starts_with(agentRuntimeName, '${NAME}')].agentRuntimeId" --output text 2>/dev/null || echo "")

  if [ -z "$RUNTIME_ID" ] || [ "$RUNTIME_ID" = "None" ]; then
    echo "  SKIP: runtime ${NAME} not found"
    continue
  fi

  TARGET_NAME="${NAME}-target"

  # Skip if target already exists
  if echo "$EXISTING_TARGETS" | grep -q "$TARGET_NAME"; then
    echo "  EXISTS: $TARGET_NAME"
    continue
  fi

  # Build the runtime endpoint URL
  ENCODED_ARN="arn%3Aaws%3Abedrock-agentcore%3A${REGION}%3A${ACCOUNT}%3Aruntime%2F${RUNTIME_ID}"
  ENDPOINT_URL="https://bedrock-agentcore.${REGION}.amazonaws.com/runtimes/${ENCODED_ARN}/invocations"

  # Build target params
  CRED_CONFIG='[{"credentialProviderType":"GATEWAY_IAM_ROLE","credentialProvider":{"iamCredentialProvider":{"service":"bedrock-agentcore","region":"'${REGION}'"}}}]'

  if [ -n "$OAUTH_PROVIDER_ARN" ] && [ "$OAUTH_PROVIDER_ARN" != "None" ]; then
    CRED_CONFIG='[{"credentialProviderType":"OAUTH","credentialProvider":{"oauthCredentialProvider":{"providerArn":"'${OAUTH_PROVIDER_ARN}'","scopes":["'${PROJECT}'-mcp/invoke"]}}}]'
  fi

  echo "  Creating target: $TARGET_NAME → $RUNTIME_ID"
  aws bedrock-agentcore-control create-gateway-target \
    --gateway-identifier "$GATEWAY_ID" \
    --name "$TARGET_NAME" \
    --description "Gateway target for ${NAME}" \
    --target-configuration '{"mcp":{"mcpServer":{"endpoint":"'${ENDPOINT_URL}'"}}}' \
    --credential-provider-configurations "$CRED_CONFIG" \
    --region "$REGION" \
    --output text --query "targetId" 2>&1 && echo "" || echo "  FAILED"
done

echo ""
echo "=== Done ==="
echo ""
echo "Targets:"
aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier "$GATEWAY_ID" --region "$REGION" \
  --query "items[].{name:name, status:status}" --output table 2>/dev/null || echo "  (none)"
