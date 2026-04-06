#!/usr/bin/env python3 -u
"""
MAKITA AgentCore Deployment Script

Deploys each MCP server as an AgentCore Runtime, creates endpoints,
sets up an AgentCore Gateway, and connects them via Gateway Targets.

Usage:
    python3 scripts/deploy_agentcore.py
    python3 scripts/deploy_agentcore.py --teardown
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile

import boto3

REGION = "us-east-1"
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
BUCKET = f"makita-artifacts-{ACCOUNT_ID}"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/makita-failover-role"

# MCP server definitions
MCP_SERVERS = [
    {
        "name": "makita_failover_mcp",
        "description": "Failover MCP Server — promotes DR replica to primary",
        "module_path": "mcp-servers/failover",
        "entry_point": ["server.py"],
    },
    {
        "name": "makita_precheck_mcp",
        "description": "Pre-Check MCP Server — verifies cluster health before failover",
        "module_path": "mcp-servers/precheck",
        "entry_point": ["server.py"],
    },
    {
        "name": "makita_postcheck_mcp",
        "description": "Post-Check MCP Server — verifies cluster state after failover",
        "module_path": "mcp-servers/postcheck",
        "entry_point": ["server.py"],
    },
    {
        "name": "makita_aws_support_stub",
        "description": "AWS Support Stub Server — simulates AWS Support API",
        "module_path": "mcp-servers/aws-support-stub",
        "entry_point": ["server.py"],
    },
    {
        "name": "makita_servicenow_stub",
        "description": "ServiceNow Stub Server — simulates ServiceNow API",
        "module_path": "mcp-servers/servicenow-stub",
        "entry_point": ["server.py"],
    },
]

GATEWAY_NAME = "makita-mcp-gateway"

client = boto3.client("bedrock-agentcore-control", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg):
    print(f"[makita] {msg}", flush=True)


def wait_for_status(get_fn, target_status, max_wait=600, interval=10):
    """Poll until status reaches target or FAILED."""
    for _ in range(max_wait // interval):
        try:
            resp = get_fn()
            status = resp.get("status", "")
            log(f"  Status: {status}")
            if status == target_status:
                return resp
            if "FAILED" in status:
                log(f"  FAILED: {resp}")
                return None
        except Exception as e:
            log(f"  Wait error: {e}")
        time.sleep(interval)
    log("  Timed out waiting")
    return None


def safe_create(fn, label, **kwargs):
    """Call a create API, handling ConflictException."""
    try:
        resp = fn(**kwargs)
        log(f"Created: {label}")
        return resp
    except client.exceptions.ConflictException:
        log(f"Already exists: {label}")
        return None
    except Exception as e:
        log(f"Error creating {label}: {e}")
        return None


def delete_runtime_by_name(name):
    """Find and delete an AgentCore Runtime by name, including its endpoints."""
    try:
        runtimes = client.list_agent_runtimes().get("agentRuntimeSummaries", [])
        for r in runtimes:
            if r.get("agentRuntimeName") == name:
                rid = r["agentRuntimeId"]
                # Delete endpoints first
                try:
                    eps = client.list_agent_runtime_endpoints(
                        agentRuntimeId=rid
                    ).get("agentRuntimeEndpoints", [])
                    for ep in eps:
                        try:
                            client.delete_agent_runtime_endpoint(
                                agentRuntimeId=rid,
                                endpointName=ep["endpointName"],
                            )
                            log(f"  Deleted endpoint: {ep['endpointName']}")
                        except Exception as e:
                            log(f"  Error deleting endpoint: {e}")
                except Exception:
                    pass
                # Delete runtime
                client.delete_agent_runtime(agentRuntimeId=rid)
                log(f"  Deleted runtime: {name} ({rid})")
                # Wait for deletion
                for _ in range(30):
                    try:
                        client.get_agent_runtime(agentRuntimeId=rid)
                        time.sleep(10)
                    except Exception:
                        break
                return True
    except Exception as e:
        log(f"  Error looking up runtime {name}: {e}")
    return False


def delete_gateway_by_name(gw_name):
    """Find and delete a Gateway by name, including its targets."""
    try:
        gateways = client.list_gateways().get("items", [])
        for g in gateways:
            if g.get("name") == gw_name:
                gw_id = g["gatewayId"]
                # Delete targets first
                try:
                    targets = client.list_gateway_targets(
                        gatewayIdentifier=gw_id
                    ).get("items", [])
                    for t in targets:
                        try:
                            client.delete_gateway_target(
                                gatewayIdentifier=gw_id,
                                targetId=t["targetId"],
                            )
                            log(f"  Deleted target: {t.get('name', t['targetId'])}")
                        except Exception as e:
                            log(f"  Error deleting target: {e}")
                except Exception:
                    pass
                # Delete gateway
                client.delete_gateway(gatewayIdentifier=gw_id)
                log(f"  Deleted gateway: {gw_name} ({gw_id})")
                # Wait for deletion
                for _ in range(30):
                    try:
                        client.get_gateway(gatewayIdentifier=gw_id)
                        time.sleep(10)
                    except Exception:
                        break
                return True
    except Exception as e:
        log(f"  Error looking up gateway {gw_name}: {e}")
    return False


# ---------------------------------------------------------------------------
# Package MCP server code
# ---------------------------------------------------------------------------

def package_server(server_def):
    """Package a single MCP server as a ZIP and upload to S3."""
    name = server_def["name"]
    module_path = server_def["module_path"]
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(project_root, module_path)
    s3_key = f"agentcore-runtimes/{name}/deployment.zip"

    log(f"Packaging {name} from {module_path}...")

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src_dir):
            # Skip __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith(".pyc"):
                    continue
                full_path = os.path.join(root, f)
                arc_name = os.path.relpath(full_path, src_dir)
                zf.write(full_path, arc_name)

    # Ensure bucket exists
    try:
        s3.head_bucket(Bucket=BUCKET)
    except Exception:
        log(f"Creating S3 bucket: {BUCKET}")
        s3.create_bucket(Bucket=BUCKET)

    log(f"Uploading to s3://{BUCKET}/{s3_key}")
    s3.upload_file(zip_path, BUCKET, s3_key)
    os.unlink(zip_path)

    return BUCKET, s3_key


# ---------------------------------------------------------------------------
# Deploy a single MCP server to AgentCore Runtime
# ---------------------------------------------------------------------------

def deploy_runtime(server_def):
    """Create an AgentCore Runtime + Endpoint for one MCP server."""
    name = server_def["name"]
    bucket, key = package_server(server_def)

    # Delete existing runtime if present
    log(f"Checking for existing Runtime: {name}")
    delete_runtime_by_name(name)

    # Create Runtime
    log(f"Creating AgentCore Runtime: {name}")
    rt = safe_create(
        client.create_agent_runtime,
        f"Runtime {name}",
        agentRuntimeName=name,
        description=server_def["description"],
        roleArn=ROLE_ARN,
        agentRuntimeArtifact={
            "codeConfiguration": {
                "code": {"s3": {"bucket": bucket, "prefix": key}},
                "runtime": "PYTHON_3_12",
                "entryPoint": server_def["entry_point"],
            }
        },
        networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "MCP"},
    )

    runtime_id = None
    if rt:
        runtime_id = rt.get("agentRuntimeId")
        log(f"Runtime ID: {runtime_id}")
        # Wait for READY
        wait_for_status(
            lambda: client.get_agent_runtime(agentRuntimeId=runtime_id),
            "READY",
        )

    if not runtime_id:
        log(f"Could not get Runtime ID for {name}")
        return None

    # Create Endpoint
    endpoint_name = f"{name}_endpoint"
    log(f"Creating Runtime Endpoint: {endpoint_name}")
    safe_create(
        client.create_agent_runtime_endpoint,
        f"Endpoint {endpoint_name}",
        agentRuntimeId=runtime_id,
        name=endpoint_name,
        description=f"Endpoint for {name}",
    )

    return runtime_id


# ---------------------------------------------------------------------------
# Deploy Gateway
# ---------------------------------------------------------------------------

def deploy_gateway():
    """Create the AgentCore Gateway."""
    # Delete existing gateway if present
    log(f"Checking for existing Gateway: {GATEWAY_NAME}")
    delete_gateway_by_name(GATEWAY_NAME)

    log(f"Creating Gateway: {GATEWAY_NAME}")
    gw = safe_create(
        client.create_gateway,
        f"Gateway {GATEWAY_NAME}",
        name=GATEWAY_NAME,
        description="MAKITA MCP Gateway for DR operations",
        roleArn=ROLE_ARN,
        protocolType="MCP",
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration={
            "customJWTAuthorizer": {
                "discoveryUrl": "https://token.actions.githubusercontent.com/.well-known/openid-configuration",
                "allowedAudience": ["makita-gateway"],
            }
        },
    )

    gw_id = None
    if gw:
        gw_id = gw.get("gatewayId")

    if gw_id:
        log(f"Gateway ID: {gw_id}")
        wait_for_status(
            lambda: client.get_gateway(gatewayIdentifier=gw_id),
            "READY",
        )

    return gw_id


# ---------------------------------------------------------------------------
# Create Gateway Targets pointing to Runtimes
# ---------------------------------------------------------------------------

def create_gateway_targets(gw_id, runtime_ids):
    """Create Gateway Targets for each MCP server Runtime."""
    for server_def in MCP_SERVERS:
        name = server_def["name"]
        runtime_id = runtime_ids.get(name)
        if not runtime_id:
            log(f"Skipping target for {name} — no Runtime ID")
            continue

        target_name = f"{name}-target"
        endpoint = f"agentcore://{runtime_id}"

        log(f"Creating Gateway Target: {target_name} -> {endpoint}")

        # Try mcpServer target type first
        try:
            client.create_gateway_target(
                gatewayIdentifier=gw_id,
                name=target_name,
                description=server_def["description"],
                targetConfiguration={
                    "mcp": {
                        "mcpServer": {"endpoint": endpoint}
                    }
                },
                credentialProviderConfigurations=[{
                    "credentialProviderType": "GATEWAY_IAM_ROLE",
                    "credentialProvider": {
                        "iamCredentialProvider": {
                            "service": "bedrock-agentcore",
                            "region": REGION,
                        }
                    },
                }],
            )
            log(f"Created target: {target_name}")
        except client.exceptions.ConflictException:
            log(f"Target already exists: {target_name}")
        except Exception as e:
            log(f"Error creating target {target_name}: {e}")


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

def teardown():
    """Delete all MAKITA AgentCore resources."""
    log("=== Teardown ===")

    # Delete gateway (includes targets)
    delete_gateway_by_name(GATEWAY_NAME)

    # Delete all makita runtimes (includes endpoints)
    for server_def in MCP_SERVERS:
        delete_runtime_by_name(server_def["name"])

    log("Teardown complete")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MAKITA AgentCore Deployment")
    parser.add_argument("--teardown", action="store_true", help="Delete all AgentCore resources")
    args = parser.parse_args()

    if args.teardown:
        teardown()
        return

    log("=== MAKITA AgentCore Deployment ===")
    log(f"Account: {ACCOUNT_ID}")
    log(f"Region: {REGION}")
    log(f"Role: {ROLE_ARN}")
    log("")

    # 1. Deploy each MCP server as an AgentCore Runtime
    runtime_ids = {}
    for server_def in MCP_SERVERS:
        rid = deploy_runtime(server_def)
        if rid:
            runtime_ids[server_def["name"]] = rid
        log("")

    log(f"Deployed {len(runtime_ids)}/{len(MCP_SERVERS)} Runtimes")
    log("")

    # 2. Deploy Gateway
    gw_id = deploy_gateway()
    log("")

    # 3. Create Gateway Targets
    if gw_id and runtime_ids:
        create_gateway_targets(gw_id, runtime_ids)
    log("")

    # Summary
    log("=== Deployment Summary ===")
    for name, rid in runtime_ids.items():
        log(f"  Runtime: {name} -> {rid}")
    if gw_id:
        log(f"  Gateway: {GATEWAY_NAME} -> {gw_id}")
    log("Done.")


if __name__ == "__main__":
    main()
