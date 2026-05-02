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
]


def _load_file(project_root: str, relative_path: str) -> str:
    """Load a file relative to the makita project root."""
    path = os.path.join(project_root, relative_path)
    with open(path) as f:
        return f.read()


class AgentCoreRuntime(Construct):
    """
    Custom resource that creates an AgentCore Runtime for a single
    MCP server. Uploads the server code as a zip to S3 via CDK Asset
    and deploys to AgentCore Runtime using direct code deploy.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        server_def: dict,
        role_arn: str,
        project_root: str,
        discovery_url: str = None,
        allowed_clients: list = None,
    ) -> None:
        super().__init__(scope, id)

        from aws_cdk import aws_s3_assets as s3_assets

        name = server_def["name"]
        module_path = os.path.join(project_root, server_def["module_path"])

        # Upload server code as a zip to S3
        self.code_asset = s3_assets.Asset(
            self, f"Code-{name}",
            path=module_path,
            exclude=["__pycache__", "*.pyc", ".bedrock_agentcore", ".bedrock_agentcore.yaml"],
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
                    "s3:GetObject",
                    "s3:GetBucketLocation",
                ],
                resources=[
                    self.code_asset.bucket.bucket_arn,
                    f"{self.code_asset.bucket.bucket_arn}/*",
                ],
            ),
        ])

        # Build runtime parameters using code zip instead of container
        runtime_params = {
            "agentRuntimeName": name,
            "description": server_def["description"],
            "roleArn": role_arn,
            "agentRuntimeArtifact": {
                "codeZipConfiguration": {
                    "s3Uri": self.code_asset.s3_object_url,
                    "entryPoint": server_def.get("entry_point", ["server.py"]),
                    "runtimeType": "PYTHON_3_11",
                }
            },
            "networkConfiguration": {"networkMode": "PUBLIC"},
            "protocolConfiguration": {"serverProtocol": "MCP"},
        }

        # Add JWT auth if Cognito is configured
        if discovery_url and allowed_clients:
            runtime_params["authorizerConfiguration"] = {
                "customJWTAuthorizer": {
                    "discoveryUrl": discovery_url,
                    "allowedClients": allowed_clients,
                }
            }

        # Create the runtime with code zip configuration
        self.runtime = cr.AwsCustomResource(
            self, f"Runtime-{name}",
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="createAgentRuntime",
                parameters=runtime_params,
                physical_resource_id=cr.PhysicalResourceId.from_response("agentRuntimeId"),
            ),
            on_update=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="getAgentRuntime",
                parameters={
                    "agentRuntimeId": name,
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
        self.runtime.node.add_dependency(self.code_asset)

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
        discovery_url: str,
        allowed_clients: list[str],
        allowed_scopes: list[str] = None,
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

        jwt_config = {
            "discoveryUrl": discovery_url,
            "allowedClients": allowed_clients,
        }
        if allowed_scopes:
            jwt_config["allowedScopes"] = allowed_scopes

        self.gateway = cr.AwsCustomResource(
            self, "Gateway",
            install_latest_aws_sdk=True,
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
                        "customJWTAuthorizer": jwt_config,
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("gatewayId"),
            ),
            on_update=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="getGateway",
                parameters={
                    "gatewayIdentifier": GATEWAY_NAME,
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
        oauth_provider_arn: str = None,
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
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=["*"],
            ),
        ])

        # Build credential provider config
        if oauth_provider_arn:
            cred_config = [{
                "credentialProviderType": "OAUTH",
                "credentialProvider": {
                    "oauthCredentialProvider": {
                        "providerArn": oauth_provider_arn,
                        "scopes": [f"{PROJECT}-mcp/invoke"],
                    }
                },
            }]
        else:
            cred_config = [{
                "credentialProviderType": "GATEWAY_IAM_ROLE",
                "credentialProvider": {
                    "iamCredentialProvider": {
                        "service": "bedrock-agentcore",
                        "region": PRIMARY_REGION,
                    }
                },
            }]

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
            "credentialProviderConfigurations": cred_config,
        }

        if cedar_policy:
            target_params["authorizationConfiguration"] = {
                "cedar": {"statement": cedar_policy}
            }

        self.target = cr.AwsCustomResource(
            self, "Target",
            install_latest_aws_sdk=True,
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
