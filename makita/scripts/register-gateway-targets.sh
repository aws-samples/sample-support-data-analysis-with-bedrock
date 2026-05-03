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

  # Check runtime status
  RT_STATUS=$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$RUNTIME_ID" --region "$REGION" \
    --query "status" --output text 2>/dev/null || echo "UNKNOWN")
  echo "  Runtime ${NAME}: ${RUNTIME_ID} (${RT_STATUS})"

  TARGET_NAME="${NAME}-target"

  # Delete existing target if present (to update endpoint)
  if echo "$EXISTING_TARGETS" | grep -q "$TARGET_NAME"; then
    echo "  Removing existing target $TARGET_NAME..."
    EXISTING_TID=$(aws bedrock-agentcore-control list-gateway-targets \
      --gateway-identifier "$GATEWAY_ID" --region "$REGION" \
      --query "items[?name=='${TARGET_NAME}'].targetId" --output text 2>/dev/null || echo "")
    if [ -n "$EXISTING_TID" ] && [ "$EXISTING_TID" != "None" ]; then
      aws bedrock-agentcore-control delete-gateway-target \
        --gateway-identifier "$GATEWAY_ID" --target-id "$EXISTING_TID" \
        --region "$REGION" 2>/dev/null || true
      sleep 3
    fi
  fi

  # Get the runtime endpoint from the runtime's endpoints list
  ENDPOINT_URL=""
  ENDPOINT_ID=$(aws bedrock-agentcore-control list-agent-runtime-endpoints \
    --agent-runtime-id "$RUNTIME_ID" --region "$REGION" \
    --query "agentRuntimeEndpoints[0].agentRuntimeEndpointId" --output text 2>/dev/null || echo "")

  if [ -n "$ENDPOINT_ID" ] && [ "$ENDPOINT_ID" != "None" ]; then
    ENDPOINT_URL=$(aws bedrock-agentcore-control get-agent-runtime-endpoint \
      --agent-runtime-id "$RUNTIME_ID" \
      --agent-runtime-endpoint-id "$ENDPOINT_ID" \
      --region "$REGION" \
      --query "agentEndpointUrl" --output text 2>/dev/null || echo "")
  fi

  # Fallback: construct the endpoint URL from the runtime ARN
  if [ -z "$ENDPOINT_URL" ] || [ "$ENDPOINT_URL" = "None" ]; then
    RUNTIME_ARN=$(aws bedrock-agentcore-control get-agent-runtime \
      --agent-runtime-id "$RUNTIME_ID" --region "$REGION" \
      --query "agentRuntimeArn" --output text 2>/dev/null || echo "")
    ENCODED_ARN=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$RUNTIME_ARN")
    ENDPOINT_URL="https://bedrock-agentcore.${REGION}.amazonaws.com/runtimes/${ENCODED_ARN}/invocations"
  fi

  echo "  Endpoint: $ENDPOINT_URL"

  # Use IAM role credentials (CLI runtimes don't have JWT auth)
  CRED_CONFIG='[{"credentialProviderType":"GATEWAY_IAM_ROLE","credentialProvider":{"iamCredentialProvider":{"service":"bedrock-agentcore","region":"'${REGION}'"}}}]'

  echo "  Creating target: $TARGET_NAME"
  aws bedrock-agentcore-control create-gateway-target \
    --gateway-identifier "$GATEWAY_ID" \
    --name "$TARGET_NAME" \
    --description "Gateway target for ${NAME}" \
    --target-configuration '{"mcp":{"mcpServer":{"endpoint":"'"${ENDPOINT_URL}"'"}}}' \
    --credential-provider-configurations "$CRED_CONFIG" \
    --region "$REGION" \
    --query "targetId" --output text 2>&1 || echo "  FAILED"
  echo ""
done

echo "=== Done ==="
echo ""
echo "Targets:"
aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier "$GATEWAY_ID" --region "$REGION" \
  --query "items[].{name:name, status:status}" --output table 2>/dev/null || echo "  (none)"
