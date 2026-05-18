#!/bin/bash
# Print all parameters needed to register the AgentCore Gateway
# with DevOps Agent (the manual step after deployment).
#
# Usage: ./scripts/show-gateway-config.sh

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "=== MAKITA Gateway Registration Parameters ==="
echo ""
echo "Use these values in the DevOps Agent console to register the MCP server."
echo "Console: https://${REGION}.console.aws.amazon.com/devops-agent/home?region=${REGION}"
echo ""

# Gateway URL
GATEWAY_ID=$(aws bedrock-agentcore-control list-gateways --region "$REGION" \
  --query "items[?starts_with(name, 'makita')].gatewayId" --output text 2>/dev/null || echo "")

if [ -n "$GATEWAY_ID" ] && [ "$GATEWAY_ID" != "None" ]; then
  GATEWAY_URL=$(aws bedrock-agentcore-control get-gateway --region "$REGION" \
    --gateway-identifier "$GATEWAY_ID" \
    --query "gatewayUrl" --output text 2>/dev/null || echo "NOT FOUND")
else
  GATEWAY_URL="NOT FOUND — run 'make deploy' first"
fi

# Cognito Client ID
CLIENT_ID=$(aws cloudformation list-exports --region "$REGION" \
  --query "Exports[?Name=='makita-CognitoClientId'].Value" --output text 2>/dev/null || echo "")

# Cognito Token Endpoint
TOKEN_ENDPOINT=$(aws cloudformation list-exports --region "$REGION" \
  --query "Exports[?Name=='makita-CognitoTokenEndpoint'].Value" --output text 2>/dev/null || echo "")

# Cognito Client Secret — retrieve command (not printed to avoid leaking to logs)
CLIENT_SECRET_CMD=""
if [ -n "$CLIENT_ID" ] && [ "$CLIENT_ID" != "None" ]; then
  POOL_ID=$(aws cognito-idp list-user-pools --max-results 60 --region "$REGION" \
    --query "UserPools[?starts_with(Name, 'makita')].Id" --output text 2>/dev/null || echo "")
  if [ -n "$POOL_ID" ] && [ "$POOL_ID" != "None" ]; then
    CLIENT_SECRET_CMD="aws cognito-idp describe-user-pool-client --region ${REGION} --user-pool-id ${POOL_ID} --client-id ${CLIENT_ID} --query UserPoolClient.ClientSecret --output text"
  fi
fi

# Print
echo "── MCP Server Registration ──────────────────────────────────"
echo ""
echo "  Name:           makita-pg"
echo "  Endpoint URL:   ${GATEWAY_URL}"
echo "  Description:    MAKITA PostgreSQL DR failover via AgentCore Gateway"
echo ""
echo "── OAuth Client Credentials ────────────────────────────────"
echo ""
echo "  Auth Flow:      OAuth Client Credentials"
echo "  Client ID:      ${CLIENT_ID:-NOT FOUND}"
echo "  Client Secret:  (not printed — run the command below to retrieve)"
echo "  Exchange URL:   ${TOKEN_ENDPOINT:-NOT FOUND}"
echo "  Scope:          makita-mcp/invoke"
echo ""
echo "  To retrieve the client secret, run:"
echo "    ${CLIENT_SECRET_CMD:-NOT AVAILABLE — Cognito pool not found}"
echo ""
echo "── Tools to Allowlist ──────────────────────────────────────"
echo ""
echo "  Failover:   execute_failover, health_check"
echo "  Pre-check:  verify_replication_health, verify_primary_status, verify_replica_readiness"
echo "  Post-check: verify_new_primary_health, verify_endpoints, verify_replication_established"
echo ""
echo "── Skill Upload ──────────────────────────────────────────"
echo ""
echo "  File:  dist/makita-postgresql-dr-skill.zip"
echo "  Type:  Generic"
echo ""
echo "============================================================"
