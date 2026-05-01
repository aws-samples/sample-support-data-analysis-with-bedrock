#!/bin/bash
# MAKITA MCP Server Deployment Script
#
# Deploys a single MCP server to AgentCore Runtime using the agentcore CLI.
# Uses CodeZip/direct_code_deploy builds (no Docker required).
#
# Usage: ./scripts/deploy-mcp-server.sh <server-dir>
#
# Examples:
#   ./scripts/deploy-mcp-server.sh failover
#   ./scripts/deploy-mcp-server.sh precheck
#   ./scripts/deploy-mcp-server.sh postcheck

set -euo pipefail

SERVER_NAME="${1:?Usage: $0 <failover|precheck|postcheck>}"
SERVER_DIR="mcp-servers/workloads/postgresql/${SERVER_NAME}"

if [ ! -d "$SERVER_DIR" ]; then
  echo "[ERROR] Server directory not found: ${SERVER_DIR}"
  exit 1
fi

if ! command -v agentcore &> /dev/null; then
  echo "[ERROR] agentcore CLI not found. Install with: npm install -g @aws/agentcore"
  exit 1
fi

echo "=== Deploying MCP server: ${SERVER_NAME} ==="
echo "  Directory: ${SERVER_DIR}"
echo ""

pushd "${SERVER_DIR}" > /dev/null
agentcore deploy --auto-update-on-conflict
popd > /dev/null

echo ""
echo "=== ${SERVER_NAME} deployed ==="
