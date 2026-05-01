"""
MAKITA Cognito CDK Constructs

Creates the Cognito User Pool and App Client for OAuth M2M
authentication between the AgentCore Gateway and Runtimes.
"""

from constructs import Construct
from aws_cdk import (
    Aws,
    RemovalPolicy,
    aws_cognito as cognito,
    custom_resources as cr,
    aws_iam as iam,
)
from config import PROJECT, PRIMARY_REGION


class McpOAuthPool(Construct):
    """Cognito User Pool + Resource Server + App Client for M2M auth."""

    def __init__(self, scope: Construct, id: str) -> None:
        super().__init__(scope, id)

        # User Pool
        self.pool = cognito.UserPool(
            self, "M2MPool",
            user_pool_name=f"{PROJECT}-m2m-pool",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Domain (required for token endpoint)
        # Cognito domain prefixes are globally unique — append account ID
        self.domain = self.pool.add_domain(
            "Domain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"{PROJECT}-m2m-{Aws.ACCOUNT_ID}",
            ),
        )

        # Resource Server with invoke scope
        resource_server = self.pool.add_resource_server(
            "McpResourceServer",
            identifier=f"{PROJECT}-mcp",
            scopes=[
                cognito.ResourceServerScope(
                    scope_name="invoke",
                    scope_description="Invoke MCP tools",
                ),
            ],
        )

        # App Client with client_credentials grant
        self.client = self.pool.add_client(
            "GatewayClient",
            user_pool_client_name=f"{PROJECT}-gateway-client",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(client_credentials=True),
                scopes=[
                    cognito.OAuthScope.custom(f"{PROJECT}-mcp/invoke"),
                ],
            ),
        )
        self.client.node.add_dependency(resource_server)

        # Store values for other constructs
        self.discovery_url = f"https://cognito-idp.{PRIMARY_REGION}.amazonaws.com/{self.pool.user_pool_id}/.well-known/openid-configuration"
        self.client_id = self.client.user_pool_client_id


class AgentCoreOAuthProvider(Construct):
    """Creates an OAuth2 Credential Provider in AgentCore Identity."""

    def __init__(
        self, scope: Construct, id: str, *,
        cognito_pool: McpOAuthPool,
    ) -> None:
        super().__init__(scope, id)

        provider_policy = cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:*",
                    "bedrock-agentcore-control:*",
                ],
                resources=["*"],
            ),
            iam.PolicyStatement(
                actions=["secretsmanager:*"],
                resources=["*"],
            ),
        ])

        # Get client secret - use the CDK token directly
        client_secret = cognito_pool.client.user_pool_client_secret

        # Create the OAuth2 credential provider
        self.provider = cr.AwsCustomResource(
            self, "OAuthProvider",
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="createOauth2CredentialProvider",
                parameters={
                    "name": f"{PROJECT}-m2m-oauth2-provider",
                    "credentialProviderVendor": "CustomOauth2",
                    "oauth2ProviderConfigInput": {
                        "customOauth2ProviderConfig": {
                            "clientId": cognito_pool.client_id,
                            "clientSecret": client_secret.unsafe_unwrap(),
                            "oauthDiscovery": {
                                "discoveryUrl": cognito_pool.discovery_url,
                            },
                        },
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("credentialProviderArn"),
            ),
            on_delete=cr.AwsSdkCall(
                service="bedrock-agentcore-control",
                action="deleteOauth2CredentialProvider",
                parameters={
                    "name": f"{PROJECT}-m2m-oauth2-provider",
                },
            ),
            policy=provider_policy,
        )

        self.provider_arn = self.provider.get_response_field("credentialProviderArn")
