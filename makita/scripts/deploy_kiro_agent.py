#!/usr/bin/env python3 -u
"""
MAKITA Kiro Agent Deployment Script

Looks up the makita-mcp-gateway AgentCore Gateway, resolves its
endpoint, patches the Kiro agent config, and validates the setup.

Usage:
    python3 scripts/deploy_kiro_agent.py
"""

import json
import subprocess
import sys
from pathlib import Path

import boto3

REGION = "us-east-1"
GATEWAY_NAME = "makita-mcp-gateway"
PROJECT_DIR = Path(__file__).resolve().parent.parent
AGENT_CONFIG = PROJECT_DIR / ".kiro" / "agents" / "makita-ops.json"
PROXY_SCRIPT = PROJECT_DIR / "mcp-servers" / "agentcore_gateway_proxy.py"
PLACEHOLDER = "__GATEWAY_URL__"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg):
    print(f"[kiro-agent] {msg}", flush=True)


def fail(msg):
    print(f"[kiro-agent] FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log("Starting Kiro agent deployment...")

    # Preflight
    if not PROXY_SCRIPT.exists():
        fail(f"Proxy script not found: {PROXY_SCRIPT}")
    if not AGENT_CONFIG.exists():
        fail(f"Agent config not found: {AGENT_CONFIG}")

    # Verify IAM identity
    sts = boto3.client("sts")
    caller = sts.get_caller_identity()["Arn"]
    log(f"IAM identity: {caller}")

    # Look up gateway
    log(f"Looking up AgentCore Gateway '{GATEWAY_NAME}' in {REGION}...")
    ac = boto3.client("bedrock-agentcore-control", region_name=REGION)
    gateways = ac.list_gateways().get("items", [])
    gateway = next((g for g in gateways if g["name"] == GATEWAY_NAME), None)
    if not gateway:
        fail(f"Gateway '{GATEWAY_NAME}' not found in {REGION}.")

    gateway_id = gateway["gatewayId"]
    gateway_url = f"https://{gateway_id}.gateway.bedrock-agentcore.{REGION}.amazonaws.com/mcp"
    log(f"Found gateway: {gateway_id}")
    log(f"Gateway URL:   {gateway_url}")

    # Patch agent config
    log("Patching agent config...")
    config = AGENT_CONFIG.read_text()
    if PLACEHOLDER in config:
        config = config.replace(PLACEHOLDER, gateway_url)
        AGENT_CONFIG.write_text(config)
        log("Replaced placeholder with gateway URL.")
    elif gateway_url in config:
        log("Agent config already has correct gateway URL.")
    else:
        log("WARNING: Neither placeholder nor expected URL found; skipping patch.")

    # Validate JSON
    try:
        json.loads(AGENT_CONFIG.read_text())
    except json.JSONDecodeError as e:
        fail(f"Agent config is not valid JSON: {e}")
    log("Agent config is valid JSON.")

    # Check Python deps
    missing = []
    for mod in ("mcp", "httpx", "boto3", "botocore"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        fail(f"Missing Python deps: {', '.join(missing)}. Run: pip install {' '.join(missing)}")
    log("Python dependencies OK.")

    # Summary
    print()
    log("=== Deployment Complete ===")
    log(f"  Gateway:  {GATEWAY_NAME} ({gateway_id})")
    log(f"  Endpoint: {gateway_url}")
    log(f"  Agent:    .kiro/agents/makita-ops.json")
    log(f"  Proxy:    mcp-servers/agentcore_gateway_proxy.py")
    print()
    log("  To use:   kiro-cli chat, then /agent swap makita-ops")
    print()


if __name__ == "__main__":
    main()
