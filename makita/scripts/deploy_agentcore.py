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
        "name": "makita_postgresql_failover_mcp",
        "description": "Failover MCP Server — promotes DR replica to primary",
        "module_path": "mcp-servers/workloads/postgresql/failover",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/postgresql-failover.cedar",
        "guardrail_file": "policies/guardrails/postgresql-failover-guardrail.json",
    },
    {
        "name": "makita_postgresql_precheck_mcp",
        "description": "Pre-Check MCP Server — verifies cluster health before failover",
        "module_path": "mcp-servers/workloads/postgresql/precheck",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/postgresql-precheck.cedar",
        "guardrail_file": "policies/guardrails/postgresql-precheck-guardrail.json",
    },
    {
        "name": "makita_postgresql_postcheck_mcp",
        "description": "Post-Check MCP Server — verifies cluster state after failover",
        "module_path": "mcp-servers/workloads/postgresql/postcheck",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/postgresql-postcheck.cedar",
        "guardrail_file": "policies/guardrails/postgresql-postcheck-guardrail.json",
    },
    {
        "name": "makita_aws_support_stub",
        "description": "AWS Support Stub Server — simulates AWS Support API",
        "module_path": "mcp-servers/aws-support-stub",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/aws-support-stub.cedar",
        "guardrail_file": "policies/guardrails/aws-support-stub-guardrail.json",
    },
    {
        "name": "makita_servicenow_stub",
        "description": "ServiceNow Stub Server — simulates ServiceNow API",
        "module_path": "mcp-servers/servicenow-stub",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/servicenow-stub.cedar",
        "guardrail_file": "policies/guardrails/servicenow-stub-guardrail.json",
    },
]

GATEWAY_NAME = "makita-mcp-gateway"

TAGS = {
    "auto-delete": "no",
    "Env": "prod1",
    "proj": "makita",
}

client = boto3.client("bedrock-agentcore-control", region_name=REGION)
bedrock_client = boto3.client("bedrock", region_name=REGION)
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
        resp = client.list_agent_runtimes()
        runtimes = resp.get("agentRuntimeSummaries", [])
        if not runtimes:
            # Try alternate response key
            runtimes = resp.get("items", resp.get("agentRuntimes", []))
        log(f"  Found {len(runtimes)} runtimes")
        for r in runtimes:
            rt_name = r.get("agentRuntimeName", r.get("name", ""))
            log(f"  Checking runtime: {rt_name}")
            if rt_name == name:
                rid = r.get("agentRuntimeId", r.get("id", ""))
                log(f"  Match! Deleting {name} ({rid})")
                # Delete endpoints first — try listing them
                try:
                    ep_resp = client.list_agent_runtime_endpoints(agentRuntimeId=rid)
                    log(f"  Endpoint response keys: {list(ep_resp.keys())}")
                    # Try all possible response keys
                    eps = (ep_resp.get("runtimeEndpoints", [])
                           or ep_resp.get("agentRuntimeEndpoints", [])
                           or ep_resp.get("items", [])
                           or ep_resp.get("endpoints", []))
                    log(f"  Found {len(eps)} endpoints")
                    for ep in eps:
                        ep_name = ep.get("name", ep.get("endpointName", ""))
                        ep_id = ep.get("id", ep.get("endpointId", ""))
                        # Skip DEFAULT — it's auto-deleted with the runtime
                        if ep_name == "DEFAULT" or ep_id == "DEFAULT":
                            log(f"  Skipping DEFAULT endpoint (auto-deleted with runtime)")
                            continue
                        log(f"  Deleting endpoint: {ep_name}")
                        try:
                            client.delete_agent_runtime_endpoint(
                                agentRuntimeId=rid,
                                endpointName=ep_name,
                            )
                            log(f"  Deleted endpoint: {ep_name}")
                        except Exception as e:
                            log(f"  Error deleting endpoint {ep_name}: {e}")
                    # Wait for non-DEFAULT endpoints to fully delete
                    if eps:
                        log("  Waiting for endpoints to delete...")
                        for _ in range(30):
                            try:
                                check = client.list_agent_runtime_endpoints(agentRuntimeId=rid)
                                remaining = [
                                    e for e in (check.get("runtimeEndpoints", [])
                                                or check.get("agentRuntimeEndpoints", [])
                                                or check.get("items", [])
                                                or check.get("endpoints", []))
                                    if e.get("name", "") != "DEFAULT" and e.get("id", "") != "DEFAULT"
                                ]
                                if not remaining:
                                    break
                                log(f"  Still {len(remaining)} endpoints remaining...")
                            except Exception:
                                break
                            time.sleep(10)
                except Exception as e:
                    log(f"  Error listing endpoints: {e}")
                # Delete runtime
                try:
                    client.delete_agent_runtime(agentRuntimeId=rid)
                    log(f"  Deleted runtime: {name} ({rid})")
                except Exception as e:
                    log(f"  Error deleting runtime: {e}")
                    return False
                # Wait for deletion
                for _ in range(30):
                    try:
                        client.get_agent_runtime(agentRuntimeId=rid)
                        time.sleep(10)
                    except Exception:
                        break
                return True
        log(f"  Runtime {name} not found in list")
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
        s3.put_bucket_tagging(
            Bucket=BUCKET,
            Tagging={"TagSet": [
                {"Key": "auto-delete", "Value": "no"},
                {"Key": "Env", "Value": "prod1"},
                {"Key": "proj", "Value": "makita"},
            ]},
        )

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
        tags=TAGS,
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
        return None, None

    # Create Endpoint
    endpoint_name = f"{name}_endpoint"
    log(f"Creating Runtime Endpoint: {endpoint_name}")
    ep = safe_create(
        client.create_agent_runtime_endpoint,
        f"Endpoint {endpoint_name}",
        agentRuntimeId=runtime_id,
        name=endpoint_name,
        description=f"Endpoint for {name}",
        tags=TAGS,
    )

    # Get the endpoint URL
    endpoint_url = None
    try:
        ep_info = wait_for_status(
            lambda: client.get_agent_runtime_endpoint(
                agentRuntimeId=runtime_id, endpointName=endpoint_name
            ),
            "READY",
        )
        if ep_info:
            endpoint_url = ep_info.get("endpointUrl", ep_info.get("url", ""))
            log(f"Endpoint URL: {endpoint_url}")
    except Exception as e:
        log(f"Error getting endpoint URL: {e}")

    return runtime_id, endpoint_url


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
        tags=TAGS,
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

def create_gateway_targets(gw_id, runtime_ids, endpoint_urls):
    """Create Gateway Targets for each MCP server Runtime with Cedar policies."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for server_def in MCP_SERVERS:
        name = server_def["name"]
        runtime_id = runtime_ids.get(name)
        endpoint_url = endpoint_urls.get(name)
        if not runtime_id or not endpoint_url:
            log(f"Skipping target for {name} — no Runtime ID or endpoint URL")
            continue

        target_name = f"{name.replace('_', '-')}-target"

        # Load Cedar policy from file
        policy_statement = None
        policy_file = server_def.get("policy_file")
        if policy_file:
            policy_path = os.path.join(project_root, policy_file)
            try:
                with open(policy_path) as f:
                    policy_statement = f.read()
                log(f"Loaded Cedar policy: {policy_file}")
            except FileNotFoundError:
                log(f"Warning: policy file not found: {policy_file}")

        log(f"Creating Gateway Target: {target_name} -> {endpoint_url}")

        # Build target kwargs
        target_kwargs = dict(
            gatewayIdentifier=gw_id,
            name=target_name,
            description=server_def["description"],
            targetConfiguration={
                "mcp": {
                    "mcpServer": {"endpoint": endpoint_url}
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

        # Attach Cedar policy if available
        if policy_statement:
            target_kwargs["authorizationConfiguration"] = {
                "cedar": {
                    "statement": policy_statement,
                }
            }

        try:
            client.create_gateway_target(**target_kwargs)
            log(f"Created target: {target_name}" + (" (with Cedar policy)" if policy_statement else ""))
        except client.exceptions.ConflictException:
            log(f"Target already exists: {target_name}")
        except Exception as e:
            log(f"Error creating target {target_name}: {e}")


# ---------------------------------------------------------------------------
# Deploy Bedrock Guardrails
# ---------------------------------------------------------------------------

def deploy_guardrails(runtime_ids):
    """Create or update Bedrock Guardrails for each MCP server from config files."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    guardrail_ids = {}

    for server_def in MCP_SERVERS:
        name = server_def["name"]
        guardrail_file = server_def.get("guardrail_file")
        if not guardrail_file:
            continue

        config_path = os.path.join(project_root, guardrail_file)
        try:
            with open(config_path) as f:
                config = json.load(f)
        except FileNotFoundError:
            log(f"Warning: guardrail config not found: {guardrail_file}")
            continue

        guardrail_name = config["name"]
        log(f"Deploying Bedrock Guardrail: {guardrail_name}")

        # Check if guardrail already exists
        existing_id = None
        try:
            resp = bedrock_client.list_guardrails()
            for g in resp.get("guardrails", []):
                if g.get("name") == guardrail_name:
                    existing_id = g.get("id")
                    break
        except Exception as e:
            log(f"  Error listing guardrails: {e}")

        # Delete existing guardrail to recreate
        if existing_id:
            log(f"  Deleting existing guardrail: {guardrail_name} ({existing_id})")
            try:
                bedrock_client.delete_guardrail(guardrailIdentifier=existing_id)
                # Wait for deletion
                for _ in range(30):
                    try:
                        bedrock_client.get_guardrail(guardrailIdentifier=existing_id)
                        time.sleep(5)
                    except Exception:
                        break
            except Exception as e:
                log(f"  Error deleting guardrail: {e}")

        # Create guardrail
        try:
            create_kwargs = {
                "name": guardrail_name,
                "description": config.get("description", ""),
                "blockedInputMessaging": config["blockedInputMessaging"],
                "blockedOutputsMessaging": config["blockedOutputsMessaging"],
                "tags": [{"key": t["key"], "value": t["value"]} for t in config.get("tags", [])],
            }
            if "contentPolicyConfig" in config:
                create_kwargs["contentPolicyConfig"] = config["contentPolicyConfig"]
            if "topicPolicyConfig" in config:
                create_kwargs["topicPolicyConfig"] = config["topicPolicyConfig"]

            resp = bedrock_client.create_guardrail(**create_kwargs)
            gid = resp.get("guardrailId", "")
            log(f"  Created guardrail: {guardrail_name} ({gid})")
            guardrail_ids[name] = gid
        except Exception as e:
            log(f"  Error creating guardrail {guardrail_name}: {e}")

    return guardrail_ids


def delete_guardrails():
    """Delete all MAKITA Bedrock Guardrails."""
    for server_def in MCP_SERVERS:
        guardrail_file = server_def.get("guardrail_file")
        if not guardrail_file:
            continue
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            guardrail_file,
        )
        try:
            with open(config_path) as f:
                config = json.load(f)
            guardrail_name = config["name"]
        except Exception:
            continue

        try:
            resp = bedrock_client.list_guardrails()
            for g in resp.get("guardrails", []):
                if g.get("name") == guardrail_name:
                    gid = g.get("id")
                    bedrock_client.delete_guardrail(guardrailIdentifier=gid)
                    log(f"  Deleted guardrail: {guardrail_name} ({gid})")
                    break
        except Exception as e:
            log(f"  Error deleting guardrail {guardrail_name}: {e}")


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

    # Delete Bedrock Guardrails
    delete_guardrails()

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
    endpoint_urls = {}
    for server_def in MCP_SERVERS:
        rid, url = deploy_runtime(server_def)
        if rid:
            runtime_ids[server_def["name"]] = rid
        if url:
            endpoint_urls[server_def["name"]] = url
        log("")

    log(f"Deployed {len(runtime_ids)}/{len(MCP_SERVERS)} Runtimes")
    log("")

    # 2. Deploy Gateway
    gw_id = deploy_gateway()
    log("")

    # 3. Create Gateway Targets
    if gw_id and endpoint_urls:
        create_gateway_targets(gw_id, runtime_ids, endpoint_urls)
    log("")

    # 4. Deploy Bedrock Guardrails
    log("Deploying Bedrock Guardrails...")
    guardrail_ids = deploy_guardrails(runtime_ids)
    log("")

    # Summary
    log("=== Deployment Summary ===")
    for name, rid in runtime_ids.items():
        log(f"  Runtime: {name} -> {rid}")
    if gw_id:
        log(f"  Gateway: {GATEWAY_NAME} -> {gw_id}")
    for name, gid in guardrail_ids.items():
        log(f"  Guardrail: {name} -> {gid}")
    log("Done.")


if __name__ == "__main__":
    main()
