"""
MAKITA AgentCore CDK Constructs

Creates the AgentCore infrastructure for MCP server runtimes, gateway,
gateway targets, and Bedrock guardrails. All resources use custom
resources since there are no native CloudFormation types for the
bedrock-agentcore-control APIs.

Resources created:
- S3 bucket for runtime deployment artifacts
- AgentCore Runtimes (one per MCP server)
- AgentCore Runtime Endpoints
- AgentCore Gateway with JWT auth
- Gateway Targets with Cedar policies
- Bedrock Guardrails from JSON config files
"""

import json
import os
from constructs import Construct
from aws_cdk import (
    Fn,
    RemovalPolicy,
    aws_iam as iam,
    custom_resources as cr,
)
from config import (
    PROJECT,
    TAGS,
    PRIMARY_REGION,
    FAILOVER_ROLE_NAME,
)

GATEWAY_NAME = f"{PROJECT}-mcp-gateway"

# MCP server definitions — mirrors deploy_agentcore.py
MCP_SERVERS = [
    {
        "name": "makita_postgresql_failover_mcp",
        "description": "Failover MCP Server - promotes DR replica to primary",
        "module_path": "mcp-servers/workloads/postgresql/failover",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/postgresql-failover.cedar",
        "guardrail_file": "policies/guardrails/postgresql-failover-guardrail.json",
    },
    {
        "name": "makita_postgresql_precheck_mcp",
        "description": "Pre-Check MCP Server - verifies cluster health before failover",
        "module_path": "mcp-servers/workloads/postgresql/precheck",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/postgresql-precheck.cedar",
        "guardrail_file": "policies/guardrails/postgresql-precheck-guardrail.json",
    },
    {
        "name": "makita_postgresql_postcheck_mcp",
        "description": "Post-Check MCP Server - verifies cluster state after failover",
        "module_path": "mcp-servers/workloads/postgresql/postcheck",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/postgresql-postcheck.cedar",
        "guardrail_file": "policies/guardrails/postgresql-postcheck-guardrail.json",
    },
    {
        "name": "makita_aws_support_stub",
        "description": "AWS Support Stub Server - simulates AWS Support API",
        "module_path": "mcp-servers/aws-support-stub",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/aws-support-stub.cedar",
        "guardrail_file": "policies/guardrails/aws-support-stub-guardrail.json",
    },
    {
        "name": "makita_servicenow_stub",
        "description": "ServiceNow Stub Server - simulates ServiceNow API",
        "module_path": "mcp-servers/servicenow-stub",
        "entry_point": ["server.py"],
        "policy_file": "policies/agentcore/servicenow-stub.cedar",
        "guardrail_file": "policies/guardrails/servicenow-stub-guardrail.json",
    },
]


def _load_file(project_root: str, relative_path: str) -> str:
    """Load a file relative to the makita project root."""
    path = os.path.join(project_root, relative_path)
    with open(path) as f:
        return f.read()


class AgentCoreRuntime(Construct):
    """
    Custom resource that creates an AgentCore Runtime for a single
    MCP server. Builds an ARM64 Docker image via CDK DockerImageAsset,
    pushes to ECR, and deploys to AgentCore Runtime.

    Requires a Dockerfile in the server's module_path directory.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        server_def: dict,
        role_arn: str,
        project_root: str,
    ) -> None:
        super().__init__(scope, id)

        from aws_cdk import aws_ecr_assets as ecr_assets

        name = server_def["name"]
        module_path = os.path.join(project_root, server_def["module_path"])

        # Build ARM64 Docker image and push to ECR
        self.image_asset = ecr_assets.DockerImageAsset(
            self, f"Image-{name}",
            directory=module_path,
            platform=ecr_assets.Platform.LINUX_ARM64,
        )

        # Policy for custom resource to manage runtimes
        agentcore_policy = cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:*",
                    "bedrock-agentcore-control:*",
                ],
                resources=["*"],
            ),
            iam.PolicyStatement(
                actions=[
                    "iam:PassRole",
                    "iam:CreateServiceLinkedRole",
                ],
                resources=["*"],
            ),
            iam.PolicyStatement(
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "ecr:BatchCheckLayerAvailability",
                ],
                resources=["*"],
            ),
        ])

        # Create the runtime with container configuration
        self.runtime = cr.AwsCustomResource(
            self, f"Runtime-{name}",
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="createAgentRuntime",
                parameters={
                    "agentRuntimeName": name,
                    "description": server_def["description"],
                    "roleArn": role_arn,
                    "agentRuntimeArtifact": {
                        "containerConfiguration": {
                            "containerUri": self.image_asset.image_uri,
                        }
                    },
                    "networkConfiguration": {"networkMode": "PUBLIC"},
                    "protocolConfiguration": {"serverProtocol": "MCP"},
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("agentRuntimeId"),
            ),
            on_delete=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="deleteAgentRuntime",
                parameters={
                    "agentRuntimeId": cr.PhysicalResourceId.of("agentRuntimeId"),
                },
            ),
            policy=agentcore_policy,
        )
        self.runtime.node.add_dependency(self.image_asset)

        # Store runtime ID and name for gateway target creation
        self.runtime_id = self.runtime.get_response_field("agentRuntimeId")
        self.runtime_arn = self.runtime.get_response_field("agentRuntimeArn")
        self.name = name
        # Construct the endpoint URL for gateway targets
        # The ARN must be URL-encoded in the path
        from aws_cdk import Stack as CdkStack
        account_id = CdkStack.of(self).account
        encoded_arn = Fn.join("", [
            f"arn%3Aaws%3Abedrock-agentcore%3A{PRIMARY_REGION}%3A",
            account_id,
            "%3Aruntime%2F",
            self.runtime_id,
        ])
        self.endpoint_url = Fn.join("", [
            f"https://bedrock-agentcore.{PRIMARY_REGION}.amazonaws.com/runtimes/",
            encoded_arn,
            "/invocations",
        ])


class AgentCoreGateway(Construct):
    """
    Custom resource that creates the AgentCore Gateway with
    JWT authorization for MCP protocol.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        role_arn: str,
    ) -> None:
        super().__init__(scope, id)

        gateway_policy = cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:*",
                    "bedrock-agentcore-control:*",
                ],
                resources=["*"],
            ),
            iam.PolicyStatement(
                actions=[
                    "iam:PassRole",
                    "iam:CreateServiceLinkedRole",
                ],
                resources=["*"],
            ),
        ])

        self.gateway = cr.AwsCustomResource(
            self, "Gateway",
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="createGateway",
                parameters={
                    "name": GATEWAY_NAME,
                    "description": "MAKITA MCP Gateway for DR operations",
                    "roleArn": role_arn,
                    "protocolType": "MCP",
                    "authorizerType": "CUSTOM_JWT",
                    "authorizerConfiguration": {
                        "customJWTAuthorizer": {
                            "discoveryUrl": "https://token.actions.githubusercontent.com/.well-known/openid-configuration",
                            "allowedAudience": ["makita-gateway"],
                        }
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("gatewayId"),
            ),
            on_delete=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="deleteGateway",
                parameters={
                    "gatewayIdentifier": cr.PhysicalResourceId.of("gatewayId"),
                },
            ),
            policy=gateway_policy,
        )

        # Store gateway ID for target creation
        self.gateway_id = self.gateway.get_response_field("gatewayId")


class AgentCoreGatewayTarget(Construct):
    """
    Creates a Gateway Target that connects a runtime's DEFAULT endpoint
    to the gateway, optionally with a Cedar policy.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        gateway_id: str,
        runtime: 'AgentCoreRuntime',
        cedar_policy: str = None,
    ) -> None:
        super().__init__(scope, id)

        target_name = f"{runtime.name.replace('_', '-')}-target"

        target_policy = cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:*",
                    "bedrock-agentcore-control:*",
                ],
                resources=["*"],
            ),
        ])

        # Use the runtime ARN as the endpoint — AgentCore resolves
        # to the DEFAULT endpoint automatically
        # Use mcpServer with endpoint URL
        # Runtime ID may contain underscores from the name, which are
        # invalid in DNS hostnames. The endpoint URL uses the runtime ID
        # directly in the hostname.
        target_params = {
            "gatewayIdentifier": gateway_id,
            "name": target_name,
            "description": f"Gateway target for {runtime.name}",
            "targetConfiguration": {
                "mcp": {
                    "mcpServer": {
                        "endpoint": runtime.endpoint_url,
                    }
                }
            },
            "credentialProviderConfigurations": [{
                "credentialProviderType": "GATEWAY_IAM_ROLE",
                "credentialProvider": {
                    "iamCredentialProvider": {
                        "service": "bedrock-agentcore",
                        "region": PRIMARY_REGION,
                    }
                },
            }],
        }

        if cedar_policy:
            target_params["authorizationConfiguration"] = {
                "cedar": {"statement": cedar_policy}
            }

        self.target = cr.AwsCustomResource(
            self, "Target",
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="createGatewayTarget",
                parameters=target_params,
                physical_resource_id=cr.PhysicalResourceId.from_response("targetId"),
            ),
            on_delete=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="deleteGatewayTarget",
                parameters={
                    "gatewayIdentifier": gateway_id,
                    "targetId": cr.PhysicalResourceId.of(target_name),
                },
            ),
            policy=target_policy,
        )


class BedrockGuardrail(Construct):
    """
    Creates a Bedrock Guardrail using the native CloudFormation resource
    AWS::Bedrock::Guardrail.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        guardrail_config: dict,
    ) -> None:
        super().__init__(scope, id)

        from aws_cdk import aws_bedrock as bedrock

        # Build content policy filters
        filters_config = []
        for f in guardrail_config.get("contentPolicyConfig", {}).get("filtersConfig", []):
            filters_config.append(bedrock.CfnGuardrail.ContentFilterConfigProperty(
                type=f["type"],
                input_strength=f["inputStrength"],
                output_strength=f["outputStrength"],
            ))

        # Build topic policy
        topics_config = []
        for t in guardrail_config.get("topicPolicyConfig", {}).get("topicsConfig", []):
            topics_config.append(bedrock.CfnGuardrail.TopicConfigProperty(
                name=t["name"],
                definition=t["definition"],
                type=t["type"],
                examples=t.get("examples", []),
            ))

        # Build tags
        tags = []
        for t in guardrail_config.get("tags", []):
            tags.append({"key": t["key"], "value": t["value"]})

        self.guardrail = bedrock.CfnGuardrail(
            self, "Guardrail",
            name=guardrail_config["name"],
            description=guardrail_config.get("description", ""),
            blocked_input_messaging=guardrail_config["blockedInputMessaging"],
            blocked_outputs_messaging=guardrail_config["blockedOutputsMessaging"],
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=filters_config,
            ) if filters_config else None,
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=topics_config,
            ) if topics_config else None,
            tags=tags if tags else None,
        )
