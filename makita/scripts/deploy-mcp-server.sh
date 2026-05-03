#!/bin/bash
# MAKITA MCP Server Deployment Script
#
# Deploys a single MCP server to AgentCore Runtime using the agentcore CLI.
# Pre-installs pip dependencies into the code directory so there's no
# cold-start pip install on AgentCore Runtime.
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
AGENT_NAME="makitapg${SERVER_NAME}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

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

# Check if agentcore project has a configured runtime
if [ ! -f "${SERVER_DIR}/agentcore/agentcore.json" ] || \
   ! python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('runtimes') else 1)" "${SERVER_DIR}/agentcore/agentcore.json" 2>/dev/null; then

  echo "  Initializing agentcore project '${AGENT_NAME}'..."

  # Clean up empty/broken agentcore dir
  rm -rf "${SERVER_DIR}/agentcore"

  # Create project in staging area
  STAGING=".build/agentcore-init"
  mkdir -p "$STAGING"
  pushd "$STAGING" > /dev/null
  rm -rf "$AGENT_NAME"
  agentcore create \
    --name "$AGENT_NAME" \
    --defaults \
    --no-agent \
    --build CodeZip \
    --protocol MCP
  popd > /dev/null

  # Copy the agentcore/ config into our server directory
  cp -r "${STAGING}/${AGENT_NAME}/agentcore" "${SERVER_DIR}/agentcore"

  # Configure the runtime in agentcore.json
  python3 -c "
import json, sys
config_path = sys.argv[1]
agent_name = sys.argv[2]
with open(config_path) as f:
    config = json.load(f)
config['runtimes'] = [{
    'name': agent_name,
    'build': 'CodeZip',
    'entrypoint': 'server.py',
    'codeLocation': '.',
    'runtimeVersion': 'PYTHON_3_11',
    'networkMode': 'PUBLIC',
    'protocol': 'MCP',
    'instrumentation': {'enableOtel': False},
}]
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
" "${SERVER_DIR}/agentcore/agentcore.json" "$AGENT_NAME"

  # Configure the deployment target in aws-targets.json
  python3 -c "
import json, sys
targets_path = sys.argv[1]
account_id = sys.argv[2]
region = sys.argv[3]
targets = [{
    'name': 'default',
    'account': account_id,
    'region': region,
}]
with open(targets_path, 'w') as f:
    json.dump(targets, f, indent=2)
" "${SERVER_DIR}/agentcore/aws-targets.json" "$ACCOUNT_ID" "$REGION"

  echo "  ✓ Project initialized"
fi

pushd "${SERVER_DIR}" > /dev/null

# Ensure CDK node_modules are properly installed
if [ -d "agentcore/cdk" ]; then
  echo "  Ensuring CDK dependencies..."
  pushd agentcore/cdk > /dev/null
  rm -rf node_modules
  npm install --silent 2>&1 | tail -1
  popd > /dev/null
fi

echo "  Packaging..."
agentcore package

echo "  Deploying..."
agentcore deploy --yes
popd > /dev/null

echo ""
echo "=== ${SERVER_NAME} deployed ==="
