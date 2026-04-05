#!/usr/bin/env bash
set -euo pipefail

# Builds a Lambda layer with the latest boto3/botocore and uploads to S3.
# Returns the layer ARN.

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="makita-artifacts-${ACCOUNT_ID}"
LAYER_KEY="layers/boto3-latest.zip"
TEMP_DIR=$(mktemp -d)

echo "[layer] Building boto3 Lambda layer..."

mkdir -p "${TEMP_DIR}/python"
pip install --quiet --target "${TEMP_DIR}/python" boto3 botocore --upgrade

cd "${TEMP_DIR}"
zip -r -q boto3-latest.zip python/

echo "[layer] Uploading to s3://${BUCKET}/${LAYER_KEY}"
aws s3 cp boto3-latest.zip "s3://${BUCKET}/${LAYER_KEY}" --region "${REGION}"

echo "[layer] Publishing Lambda layer..."
LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name makita-boto3-latest \
  --content "S3Bucket=${BUCKET},S3Key=${LAYER_KEY}" \
  --compatible-runtimes python3.11 \
  --region "${REGION}" \
  --query LayerVersionArn \
  --output text)

rm -rf "${TEMP_DIR}"

echo "[layer] Done."
echo "LAYER_ARN=${LAYER_ARN}"
