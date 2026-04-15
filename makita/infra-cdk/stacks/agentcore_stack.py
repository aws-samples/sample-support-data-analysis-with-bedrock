"""
MAKITA AgentCore CDK Stack

Deploys the full AgentCore infrastructure:
- AgentCore Runtimes (5 MCP servers) as Docker containers on ECR
- AgentCore Gateway with JWT auth
- Bedrock Guardrails for each MCP server

Prerequisites:
- PostgreSQL stacks must be deployed (provides the failover IAM role)
- Docker must be available for building ARM64 images

Usage:
    cdk deploy MakitaAgentCore --app "python3 app.py"
"""

import json
import os
from constructs import Construct
from aws_cdk import Stack, CfnOutput

from config import (
    PROJECT,
    PRIMARY_REGION,
    FAILOVER_ROLE_NAME,
)
from resources.agentcore import (
    AgentCoreRuntime,
    AgentCoreGateway,
    AgentCoreGatewayTarget,
    BedrockGuardrail,
    MCP_SERVERS,
    GATEWAY_NAME,
    _load_file,
)


class MakitaAgentCoreStack(Stack):
    """Stack for MAKITA AgentCore resources."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_id = self.account
        role_arn = f"arn:aws:iam::{account_id}:role/{FAILOVER_ROLE_NAME}"

        # Project root is two levels up from infra-cdk/stacks/
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Deploy each MCP server as a Docker container on AgentCore Runtime
        runtimes = {}
        for server_def in MCP_SERVERS:
            name = server_def["name"]
            runtime = AgentCoreRuntime(
                self, f"Runtime-{name}",
                server_def=server_def,
                role_arn=role_arn,
                project_root=project_root,
            )
            runtimes[name] = runtime

        # AgentCore Gateway
        gateway = AgentCoreGateway(
            self, "Gateway",
            role_arn=role_arn,
        )
        for runtime in runtimes.values():
            gateway.node.add_dependency(runtime)

        # Gateway Targets — wire each runtime to the gateway
        for server_def in MCP_SERVERS:
            name = server_def["name"]
            runtime = runtimes[name]

            # Load Cedar policy if available
            cedar_policy = None
            policy_file = server_def.get("policy_file")
            if policy_file:
                policy_path = os.path.join(project_root, policy_file)
                if os.path.exists(policy_path):
                    cedar_policy = _load_file(project_root, policy_file)

            target = AgentCoreGatewayTarget(
                self, f"Target-{name}",
                gateway_id=gateway.gateway_id,
                runtime=runtime,
                cedar_policy=cedar_policy,
            )
            target.node.add_dependency(gateway)

        # Bedrock Guardrails for each MCP server
        for server_def in MCP_SERVERS:
            guardrail_file = server_def.get("guardrail_file")
            if not guardrail_file:
                continue
            config_path = os.path.join(project_root, guardrail_file)
            if not os.path.exists(config_path):
                continue
            with open(config_path) as f:
                guardrail_config = json.load(f)
            BedrockGuardrail(
                self, f"Guardrail-{server_def['name']}",
                guardrail_config=guardrail_config,
            )

        # Outputs
        CfnOutput(self, "GatewayName",
                  value=GATEWAY_NAME,
                  description="AgentCore Gateway name")

        CfnOutput(self, "RuntimeCount",
                  value=str(len(MCP_SERVERS)),
                  description="Number of AgentCore Runtimes deployed")

        CfnOutput(self, "McpServers",
                  value=", ".join(s["name"] for s in MCP_SERVERS),
                  description="Deployed MCP server names")
