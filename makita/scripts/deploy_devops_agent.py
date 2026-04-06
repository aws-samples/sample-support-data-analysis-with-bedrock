#!/usr/bin/env python3 -u
"""
MAKITA DevOps Agent Space Deployment Script

Creates a DevOps Agent Space and associates the AgentCore Gateway.

Usage:
    python3 scripts/deploy_devops_agent.py
    python3 scripts/deploy_devops_agent.py --teardown
"""

import argparse
import sys
import time

import boto3

REGION = "us-east-1"
ACCOUNT_ID = boto3.client("sts").get_caller_identity()["Account"]
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/makita-failover-role"
OPERATOR_ROLE_NAME = "makita-devops-agent-operator-role"
OPERATOR_ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/{OPERATOR_ROLE_NAME}"
AGENT_SPACE_NAME = "makita-agentspace"
GATEWAY_NAME = "makita-mcp-gateway"

TAGS = {
    "auto-delete": "no",
    "Env": "prod1",
    "proj": "makita",
}

devops_client = boto3.client("devops-agent", region_name=REGION)
agentcore_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
iam_client = boto3.client("iam")
logs_client = boto3.client("logs", region_name=REGION)

LOG_GROUP_NAME = "/makita/devops-agent"


def log(msg):
    print(f"[makita] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_agent_space():
    """Find the makita agent space by name, return agentSpaceId or None."""
    try:
        resp = devops_client.list_agent_spaces()
        spaces = resp.get("agentSpaces", resp.get("items", []))
        for s in spaces:
            if s.get("name") == AGENT_SPACE_NAME:
                return s.get("agentSpaceId", s.get("id", ""))
    except Exception as e:
        log(f"Error listing agent spaces: {e}")
    return None


def delete_agent_space(space_id):
    """Delete an agent space by ID."""
    try:
        devops_client.delete_agent_space(agentSpaceId=space_id)
        log(f"Deleted agent space: {AGENT_SPACE_NAME} ({space_id})")
        # Wait for deletion
        for _ in range(30):
            try:
                devops_client.get_agent_space(agentSpaceId=space_id)
                time.sleep(5)
            except Exception:
                break
        return True
    except Exception as e:
        log(f"Error deleting agent space: {e}")
        return False


def find_gateway_id():
    """Find the makita gateway ID."""
    try:
        gateways = agentcore_client.list_gateways().get("items", [])
        for g in gateways:
            if g.get("name") == GATEWAY_NAME:
                return g.get("gatewayId", "")
    except Exception as e:
        log(f"Error finding gateway: {e}")
    return None


def ensure_operator_role(space_id=None):
    """Create the IAM role for the DevOps Agent web app operator, or return existing."""
    import json

    source_arn = f"arn:aws:aidevops:{REGION}:{ACCOUNT_ID}:agentspace/{space_id}" if space_id else f"arn:aws:aidevops:{REGION}:{ACCOUNT_ID}:agentspace/*"

    trust_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "aidevops.amazonaws.com"
                },
                "Action": [
                    "sts:AssumeRole",
                    "sts:TagSession"
                ],
                "Condition": {
                    "StringEquals": {
                        "aws:SourceAccount": ACCOUNT_ID
                    },
                    "ArnLike": {
                        "aws:SourceArn": source_arn
                    }
                }
            }
        ]
    })

    # Service principals to try for DevOps Agent trust
    # We'll attempt to add each one after role creation
    service_principals = [
        "aidevops.amazonaws.com",
        "devopsagent.amazonaws.com",
        "devops-agent.us-east-1.amazonaws.com",
    ]

    operator_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "devops-agent:*",
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:*",
                    "bedrock-agentcore-control:*",
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "rds:DescribeDBInstances",
                    "rds:DescribeDBClusters",
                    "ssm:GetParameter",
                    "cloudwatch:GetMetricData",
                    "cloudwatch:DescribeAlarms",
                    "logs:GetLogEvents",
                    "logs:DescribeLogGroups",
                ],
                "Resource": "*"
            }
        ]
    })

    # Check if role exists — delete it to recreate with correct trust policy
    try:
        iam_client.get_role(RoleName=OPERATOR_ROLE_NAME)
        log(f"Deleting existing operator role: {OPERATOR_ROLE_NAME}")
        delete_operator_role()
    except iam_client.exceptions.NoSuchEntityException:
        pass

    # Create role
    log(f"Creating operator role: {OPERATOR_ROLE_NAME}")
    try:
        iam_client.create_role(
            RoleName=OPERATOR_ROLE_NAME,
            AssumeRolePolicyDocument=trust_policy,
            Description="MAKITA DevOps Agent web app operator role",
            Tags=[
                {"Key": "auto-delete", "Value": "no"},
                {"Key": "Env", "Value": "prod1"},
                {"Key": "proj", "Value": "makita"},
            ],
        )
        # Attach managed policy
        iam_client.attach_role_policy(
            RoleName=OPERATOR_ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/AIDevOpsOperatorAppAccessPolicy",
        )
        # Also attach inline policy for additional permissions
        iam_client.put_role_policy(
            RoleName=OPERATOR_ROLE_NAME,
            PolicyName="makita-devops-agent-operator-policy",
            PolicyDocument=operator_policy,
        )
        log(f"Created operator role: {OPERATOR_ROLE_ARN}")
        # Wait for IAM propagation
        log("  Waiting for IAM propagation...")
        time.sleep(10)
        return OPERATOR_ROLE_ARN
    except Exception as e:
        log(f"Error creating operator role: {e}")
        return None


def delete_operator_role():
    """Delete the operator IAM role."""
    try:
        # Detach managed policies
        attached = iam_client.list_attached_role_policies(
            RoleName=OPERATOR_ROLE_NAME
        ).get("AttachedPolicies", [])
        for p in attached:
            iam_client.detach_role_policy(
                RoleName=OPERATOR_ROLE_NAME, PolicyArn=p["PolicyArn"]
            )
        # Delete inline policies
        policies = iam_client.list_role_policies(
            RoleName=OPERATOR_ROLE_NAME
        ).get("PolicyNames", [])
        for p in policies:
            iam_client.delete_role_policy(
                RoleName=OPERATOR_ROLE_NAME, PolicyName=p
            )
        iam_client.delete_role(RoleName=OPERATOR_ROLE_NAME)
        log(f"Deleted operator role: {OPERATOR_ROLE_NAME}")
    except iam_client.exceptions.NoSuchEntityException:
        pass
    except Exception as e:
        log(f"Error deleting operator role: {e}")


def ensure_log_group():
    """Create the CloudWatch log group for DevOps Agent, return its ARN."""
    try:
        logs_client.create_log_group(
            logGroupName=LOG_GROUP_NAME,
            tags=TAGS,
        )
        log(f"Created log group: {LOG_GROUP_NAME}")
    except logs_client.exceptions.ResourceAlreadyExistsException:
        log(f"Log group already exists: {LOG_GROUP_NAME}")
    except Exception as e:
        log(f"Error creating log group: {e}")
        return None

    # Set retention to 30 days
    try:
        logs_client.put_retention_policy(
            logGroupName=LOG_GROUP_NAME,
            retentionInDays=30,
        )
    except Exception:
        pass

    return f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:log-group:{LOG_GROUP_NAME}"


def setup_log_delivery(space_id, log_group_arn):
    """Configure vended log delivery from the agent space to CloudWatch Logs."""
    agent_space_arn = f"arn:aws:devops-agent:{REGION}:{ACCOUNT_ID}:agent-space/{space_id}"

    # Authorize vended log delivery
    log("Authorizing vended log delivery...")
    try:
        resp = devops_client.allow_vended_log_delivery_for_resource(
            resourceArnBeingAuthorized=log_group_arn,
            deliverySourceArn=agent_space_arn,
        )
        log(f"  {resp.get('message', 'Authorized')}")
    except Exception as e:
        log(f"  Error authorizing log delivery: {e}")

    # Create delivery source + destination + delivery via CloudWatch Logs API
    log("Creating CloudWatch log delivery...")
    try:
        # Create delivery source
        try:
            logs_client.put_delivery_source(
                name=f"makita-devops-agent-source",
                resourceArn=agent_space_arn,
                logType="APPLICATION_LOGS",
            )
            log("  Created delivery source")
        except Exception as e:
            if "already exists" in str(e).lower() or "Conflict" in str(type(e).__name__):
                log("  Delivery source already exists")
            else:
                log(f"  Error creating delivery source: {e}")

        # Create delivery destination
        try:
            logs_client.put_delivery_destination(
                name=f"makita-devops-agent-destination",
                outputFormat="json",
                deliveryDestinationConfiguration={
                    "destinationResourceArn": log_group_arn,
                },
            )
            log("  Created delivery destination")
        except Exception as e:
            if "already exists" in str(e).lower() or "Conflict" in str(type(e).__name__):
                log("  Delivery destination already exists")
            else:
                log(f"  Error creating delivery destination: {e}")

        # Create delivery
        try:
            logs_client.create_delivery(
                deliverySourceName=f"makita-devops-agent-source",
                deliveryDestinationArn=f"arn:aws:logs:{REGION}:{ACCOUNT_ID}:delivery-destination:makita-devops-agent-destination",
            )
            log("  Created delivery")
        except Exception as e:
            if "already exists" in str(e).lower() or "Conflict" in str(type(e).__name__):
                log("  Delivery already exists")
            else:
                log(f"  Error creating delivery: {e}")

    except Exception as e:
        log(f"  Error setting up log delivery: {e}")


def delete_log_group():
    """Delete the CloudWatch log group."""
    try:
        logs_client.delete_log_group(logGroupName=LOG_GROUP_NAME)
        log(f"Deleted log group: {LOG_GROUP_NAME}")
    except logs_client.exceptions.ResourceNotFoundException:
        pass
    except Exception as e:
        log(f"Error deleting log group: {e}")


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

def _print_manual_mcp_instructions(space_id, gw_url):
    """Print manual instructions for registering the AgentCore Gateway in the console."""
    log("")
    log("=" * 60)
    log("MANUAL MCP SERVER REGISTRATION")
    log("=" * 60)
    log("")
    log("The register_service API is restricted to external/exempted")
    log("accounts. Register the AgentCore Gateway manually:")
    log("")
    log(f"  1. Open the DevOps Agent console:")
    log(f"     https://{REGION}.console.aws.amazon.com/devops-agent/home?region={REGION}#/spaces/{space_id}")
    log("")
    log(f"  2. Go to 'MCP Servers' or 'Tools' section")
    log("")
    log(f"  3. Add the AgentCore Gateway as an MCP server:")
    log(f"     Name:     {GATEWAY_NAME}")
    log(f"     Endpoint: {gw_url}")
    log("")
    log("  All MCP server runtimes are behind this single gateway.")
    log("  You only need to register the gateway — not individual servers.")
    log("")
    log("=" * 60)


def deploy():
    """Create the DevOps Agent Space and associate the gateway."""
    log("=== MAKITA DevOps Agent Deployment ===")
    log(f"Account: {ACCOUNT_ID}")
    log(f"Region: {REGION}")
    log("")

    # Check for existing agent space and delete if found
    log(f"Checking for existing Agent Space: {AGENT_SPACE_NAME}")
    existing_id = find_agent_space()
    if existing_id:
        log(f"Found existing: {existing_id}, deleting...")
        delete_agent_space(existing_id)
    else:
        log("No existing agent space found.")
    log("")

    # Create agent space
    log(f"Creating Agent Space: {AGENT_SPACE_NAME}")
    try:
        resp = devops_client.create_agent_space(
            name=AGENT_SPACE_NAME,
            description="MAKITA DevOps Agent Space for PostgreSQL DR operations",
            tags=TAGS,
        )
        space = resp.get("agentSpace", {})
        space_id = space.get("agentSpaceId", "")
        log(f"Created Agent Space: {space_id}")
    except Exception as e:
        log(f"Error creating agent space: {e}")
        return
    log("")

    # Associate the primary AWS account as a source
    log("Associating primary AWS account...")
    try:
        devops_client.associate_service(
            agentSpaceId=space_id,
            serviceId=f"aws-source-{ACCOUNT_ID}",
            configuration={
                "sourceAws": {
                    "accountId": ACCOUNT_ID,
                    "accountType": "source",
                    "assumableRoleArn": ROLE_ARN,
                }
            },
        )
        log(f"Associated AWS account {ACCOUNT_ID}")
    except Exception as e:
        log(f"Error associating AWS account: {e}")
    log("")

    # Find and register the gateway as an MCP server
    gw_id = find_gateway_id()
    gw_url = ""
    if gw_id:
        log(f"AgentCore Gateway available: {GATEWAY_NAME} ({gw_id})")
        try:
            gw_info = agentcore_client.get_gateway(gatewayIdentifier=gw_id)
            gw_url = gw_info.get("gatewayUrl", "")
            if gw_url:
                log(f"Gateway URL: {gw_url}")
            else:
                log("Gateway URL not available yet")
        except Exception as e:
            log(f"Error getting gateway info: {e}")

        # Attempt programmatic registration (known to fail on non-exempted accounts)
        if gw_url:
            log("Registering gateway as MCP server...")
            try:
                reg = devops_client.register_service(
                    service="mcpserver",
                    serviceDetails={
                        "mcpserver": {
                            "name": GATEWAY_NAME,
                            "endpoint": gw_url,
                            "description": "MAKITA MCP Gateway for PostgreSQL DR tools",
                            "authorizationConfig": {
                                "authorizationDiscovery": {
                                    "returnToEndpoint": f"https://{REGION}.console.aws.amazon.com/devops-agent",
                                }
                            },
                        }
                    },
                )
                service_id = reg.get("serviceId", "")
                log(f"Registered MCP server: {service_id}")
                if service_id:
                    log("Associating MCP server with agent space...")
                    try:
                        devops_client.associate_service(
                            agentSpaceId=space_id,
                            serviceId=service_id,
                            configuration={
                                "sourceAws": {
                                    "accountId": ACCOUNT_ID,
                                    "accountType": "source",
                                    "assumableRoleArn": ROLE_ARN,
                                }
                            },
                        )
                        log("Associated MCP server with agent space")
                    except Exception as e:
                        log(f"Error associating MCP server: {e}")
            except Exception as e:
                log(f"Programmatic registration not available: {e}")
                log("")
                log(">> Manual registration required. See instructions below.")
                _print_manual_mcp_instructions(space_id, gw_url)
    else:
        log("No AgentCore Gateway found. Run deploy_agentcore.py first.")
    log("")

    # Create operator IAM role for the web app (needs specific space ID)
    log("Ensuring operator IAM role...")
    delete_operator_role()  # Always recreate with correct space ID
    operator_arn = ensure_operator_role(space_id=space_id)
    log("")

    # Enable the web app
    if operator_arn:
        log("Enabling DevOps Agent Web App...")
        try:
            devops_client.enable_operator_app(
                agentSpaceId=space_id,
                authFlow="iam",
                operatorAppRoleArn=operator_arn,
            )
            log("Web App enabled with IAM auth flow.")
        except Exception as e:
            log(f"Error enabling web app: {e}")
    log("")

    # Set up CloudWatch log group
    log("Setting up CloudWatch log group...")
    log_group_arn = ensure_log_group()
    log("")

    # Summary
    log("=== Deployment Summary ===")
    log(f"  Agent Space: {AGENT_SPACE_NAME} ({space_id})")
    if operator_arn:
        log(f"  Operator Role: {OPERATOR_ROLE_NAME}")
        log(f"  Web App: Enabled (IAM auth)")
    log(f"  Log Group: {LOG_GROUP_NAME}")
    if gw_id:
        log(f"  Gateway: {GATEWAY_NAME} ({gw_id})")
        if gw_url:
            log(f"  Gateway URL: {gw_url}")
    log(f"  Console: https://{REGION}.console.aws.amazon.com/devops-agent/home?region={REGION}#/spaces/{space_id}")
    log("Done.")


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

def teardown():
    """Delete the DevOps Agent Space, operator role, and log group."""
    log("=== Teardown ===")
    existing_id = find_agent_space()
    if existing_id:
        delete_agent_space(existing_id)
    else:
        log(f"Agent space {AGENT_SPACE_NAME} not found.")
    delete_operator_role()
    delete_log_group()
    log("Teardown complete.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MAKITA DevOps Agent Deployment")
    parser.add_argument("--teardown", action="store_true", help="Delete the agent space")
    args = parser.parse_args()

    if args.teardown:
        teardown()
    else:
        deploy()


if __name__ == "__main__":
    main()
