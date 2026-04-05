#!/usr/bin/env bash
set -euo pipefail

# MAKITA MCP Server Packaging Script
# Packages the mcp-servers/ directory into a ZIP and uploads to S3.
#
# Usage: ./scripts/package-mcp.sh
# Outputs: S3 bucket and key to stdout for use by deploy.sh

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="makita-artifacts-${ACCOUNT_ID}"
KEY="mcp-servers/makita-mcp-servers.zip"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."
TEMP_DIR=$(mktemp -d)

echo "[package] Packaging MCP server code..."

# Create the ZIP artifact
cd "${PROJECT_DIR}"
zip -r "${TEMP_DIR}/makita-mcp-servers.zip" \
  mcp-servers/ \
  orchestrator/ \
  event-logs/event_logger.py \
  pyproject.toml \
  -x "*__pycache__*" "*.pyc" "*/.DS_Store"

# Ensure S3 bucket exists
if ! aws s3api head-bucket --bucket "${BUCKET}" --region "${REGION}" 2>/dev/null; then
  echo "[package] Creating S3 bucket: ${BUCKET}"
  aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}"
  aws s3api put-bucket-tagging --bucket "${BUCKET}" --tagging 'TagSet=[{Key=auto-delete,Value=no},{Key=Env,Value=prod1}]'
fi

# Upload
echo "[package] Uploading to s3://${BUCKET}/${KEY}"
aws s3 cp "${TEMP_DIR}/makita-mcp-servers.zip" "s3://${BUCKET}/${KEY}"

# Cleanup
rm -rf "${TEMP_DIR}"

echo "[package] Done."
echo "BUCKET=${BUCKET}"
echo "KEY=${KEY}"
