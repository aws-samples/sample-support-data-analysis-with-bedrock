"""
MAKITA Parent Stack with Nested Stacks

Single deployable stack that contains all MAKITA infrastructure
as nested stacks with proper dependency ordering:

1. PostgresqlNestedStack — Primary PostgreSQL + IAM + SSM (us-east-1)
2. AgentCoreNestedStack  — AgentCore runtimes, gateway, guardrails
3. DevOpsAgentNestedStack — DevOps Agent Space + operator role

Note: The PostgreSQL replica (us-west-2) remains a separate top-level
stack since nested stacks cannot span regions.

Usage:
    cdk deploy Makita
"""

import json
import os
from constructs import Construct
from aws_cdk import (
    Stack,
    NestedStack,
    CfnOutput,
    Duration,
    RemovalPolicy,
)

from config import (
    PROJECT,
    PRIMARY_REGION,
    DR_REGION,
    FAILOVER_ROLE_NAME,
)
from resources.postgresql import (
    PrimaryNetworking,
    PrimaryDatabase,
    McpServerRoles,
    MakitaSsmParameters,
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
from resources.cognito import McpOAuthPool, AgentCoreOAuthProvider
from resources.devops_agent import (
    DevOpsAgentLogGroup,
    DevOpsAgentOperatorRole,
    DevOpsAgentSpace,
    AGENT_SPACE_NAME,
    OPERATOR_ROLE_NAME,
    LOG_GROUP_NAME,
)


class PostgresqlNestedStack(NestedStack):
    """Primary PostgreSQL infrastructure."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        account_id = self.account

        networking = PrimaryNetworking(self, "Networking")
        database = PrimaryDatabase(
            self, "Database",
            vpc=networking.vpc,
            security_group=networking.security_group,
        )
        roles = McpServerRoles(self, "Roles", account_id=account_id)
        MakitaSsmParameters(
            self, "SsmParams",
            primary_endpoint=database.instance.db_instance_endpoint_address,
            replica_endpoint="pending-replica-deployment",
            account_id=account_id,
        )

        # Expose for parent stack
        self.primary_instance = database.instance
        self.primary_secret = database.secret
        self.failover_role = roles.failover_role
        self.precheck_role = roles.precheck_role
        self.postcheck_role = roles.postcheck_role


class AgentCoreNestedStack(NestedStack):
    """AgentCore runtimes, gateway, Cognito OAuth, and guardrails."""

    def __init__(
        self, scope: Construct, id: str, *,
        role_arn: str,
        project_root: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Cognito for M2M OAuth between gateway and runtimes
        oauth_pool = McpOAuthPool(self, "OAuthPool")
        oauth_provider = AgentCoreOAuthProvider(
            self, "OAuthProvider",
            cognito_pool=oauth_pool,
        )

        # Expose Cognito values for parent stack outputs
        self.cognito_client_id = oauth_pool.client_id
        self.cognito_token_endpoint = oauth_pool.token_endpoint

        # Deploy each MCP server as a code zip with JWT auth
        runtimes = {}
        for server_def in MCP_SERVERS:
            name = server_def["name"]
            runtime = AgentCoreRuntime(
                self, f"Runtime-{name}",
                server_def=server_def,
                role_arn=role_arn,
                project_root=project_root,
                discovery_url=oauth_pool.discovery_url,
                allowed_clients=[oauth_pool.client_id],
            )
            runtime.node.add_dependency(oauth_pool)
            runtimes[name] = runtime

        # Gateway
        gateway = AgentCoreGateway(
            self, "Gateway",
            role_arn=role_arn,
            discovery_url=oauth_pool.discovery_url,
            allowed_clients=[oauth_pool.client_id],
            allowed_scopes=[f"{PROJECT}-mcp/invoke"],
        )
        for runtime in runtimes.values():
            gateway.node.add_dependency(runtime)

        # Gateway Targets with OAuth credentials
        for server_def in MCP_SERVERS:
            name = server_def["name"]
            runtime = runtimes[name]

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
                oauth_provider_arn=oauth_provider.provider_arn,
                cedar_policy=cedar_policy,
            )
            target.node.add_dependency(gateway)
            target.node.add_dependency(oauth_provider)

        # Guardrails
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


class DevOpsAgentNestedStack(NestedStack):
    """DevOps Agent Space, operator role, and log group."""

    def __init__(
        self, scope: Construct, id: str, *,
        account_id: str,
        failover_role_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        log_group = DevOpsAgentLogGroup(self, "AgentLogGroup")
        operator_role = DevOpsAgentOperatorRole(
            self, "AgentOperatorRole",
            account_id=account_id,
        )
        agent_space = DevOpsAgentSpace(
            self, "AgentSpace",
            account_id=account_id,
            operator_role=operator_role.role,
            failover_role_arn=failover_role_arn,
        )
        agent_space.node.add_dependency(operator_role)
        agent_space.node.add_dependency(log_group)


class MakitaStack(Stack):
    """
    Parent stack containing all MAKITA infrastructure as nested stacks.

    Deploy with: cdk deploy Makita
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_id = self.account
        failover_role_arn = f"arn:aws:iam::{account_id}:role/{FAILOVER_ROLE_NAME}"

        # Project root is two levels up from infra-cdk/stacks/
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # 1. PostgreSQL (primary region)
        postgresql = PostgresqlNestedStack(
            self, "PostgresqlStack",
            description="MAKITA PostgreSQL primary infrastructure",
        )

        # 2. AgentCore (depends on PostgreSQL for IAM role)
        agentcore = AgentCoreNestedStack(
            self, "AgentCoreStack",
            role_arn=failover_role_arn,
            project_root=project_root,
            description="MAKITA AgentCore runtimes, gateway, guardrails",
        )
        agentcore.add_dependency(postgresql)

        # 3. DevOps Agent (depends on AgentCore for gateway)
        devops_agent = DevOpsAgentNestedStack(
            self, "DevOpsAgentStack",
            account_id=account_id,
            failover_role_arn=failover_role_arn,
            description="MAKITA DevOps Agent infrastructure",
        )
        devops_agent.add_dependency(agentcore)

        # Outputs from parent stack
        CfnOutput(self, "PrimaryEndpoint",
                  value=postgresql.primary_instance.db_instance_endpoint_address,
                  export_name=f"{PROJECT}-primary-endpoint")

        CfnOutput(self, "FailoverRoleArn",
                  value=postgresql.failover_role.role_arn,
                  export_name=f"{PROJECT}-failover-role-arn")

        CfnOutput(self, "GatewayName",
                  value=GATEWAY_NAME,
                  description="AgentCore Gateway name")

        CfnOutput(self, "AgentSpaceName",
                  value=AGENT_SPACE_NAME,
                  description="DevOps Agent Space name")

        CfnOutput(self, "ConsoleUrl",
                  value=f"https://{PRIMARY_REGION}.console.aws.amazon.com/devops-agent/home?region={PRIMARY_REGION}",
                  description="DevOps Agent console URL")

        CfnOutput(self, "CognitoClientId",
                  value=agentcore.cognito_client_id,
                  export_name=f"{PROJECT}-CognitoClientId",
                  description="Cognito App Client ID for MCP gateway auth")

        CfnOutput(self, "CognitoTokenEndpoint",
                  value=agentcore.cognito_token_endpoint,
                  export_name=f"{PROJECT}-CognitoTokenEndpoint",
                  description="Cognito OAuth2 token endpoint")
