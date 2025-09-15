#!/bin/bash

# MAKI Codebase Packaging Script
# This script packages the MAKI CDK codebase into a tar.gz file for deployment to another account
# Run in the root CDK directory, same directory as cdk.out

# in the target account, if CUR does not exists, enable CUR_SKIP in config.py

set -e  # Exit on any error

# Configuration
PACKAGE_NAME="maki-codebase-$(date +%Y%m%d-%H%M%S).tar.gz"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting MAKI codebase packaging..."
echo "📁 Working directory: $SCRIPT_DIR"
echo "📦 Package name: $PACKAGE_NAME"

# Change to the project directory
cd "$SCRIPT_DIR"

# Create the package with exclusions
echo "📦 Creating tar.gz package with exclusions..."
tar -czf "$PACKAGE_NAME" \
  --exclude='node_modules' \
  --exclude='cdk.out' \
  --exclude='.git' \
  --exclude='.gitignore' \
  --exclude='*.pyc' \
  --exclude='__pycache__' \
  --exclude='.DS_Store' \
  --exclude='*.log' \
  --exclude='*.tmp' \
  --exclude='.env' \
  --exclude='.env.local' \
  --exclude='coverage' \
  --exclude='.nyc_output' \
  --exclude='dist' \
  --exclude='build' \
  --exclude='.vscode' \
  --exclude='.idea' \
  --exclude='*.swp' \
  --exclude='*.swo' \
  --exclude='.terraform' \
  --exclude='terraform.tfstate*' \
  --exclude='package-maki.sh' \
  .

# Get package size
PACKAGE_SIZE=$(du -h "$PACKAGE_NAME" | cut -f1)

echo "✅ Package created successfully!"
echo "📊 Package size: $PACKAGE_SIZE"
echo "📍 Package location: $SCRIPT_DIR/$PACKAGE_NAME"
echo ""
echo "🚀 To deploy in target account:"
echo "   1. Transfer $PACKAGE_NAME to target environment"
echo "   2. Extract: tar -xzf $PACKAGE_NAME"
echo "   3. Install dependencies (npm install or pip install -r requirements.txt)"
echo "   4. Bootstrap CDK: cdk bootstrap --profile target-account"
echo "   5. Deploy stacks in order:"
echo "      - cdk deploy MakiFoundations --profile target-account"
echo "      - cdk deploy MakiData --profile target-account"
echo "      - cdk deploy MakiGenAI --profile target-account"
echo ""