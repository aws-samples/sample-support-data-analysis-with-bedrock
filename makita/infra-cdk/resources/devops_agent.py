"""
MAKITA DevOps Agent CDK Constructs

Creates the IAM operator role and CloudWatch log group required
by the Amazon DevOps Agent Space. The agent space itself and its
gateway association are managed via custom resources since there
are no native CloudFormation resources for the DevOps Agent API.
"""

import json
from constructs import Construct
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_iam as iam,
    aws_logs as logs,
    aws_devopsagent as devopsagent,
    custom_resources as cr,
)
from config import (
    PROJECT,
    TAGS,
    PRIMARY_REGION,
    FAILOVER_ROLE_NAME,
    PRECHECK_ROLE_NAME,
    POSTCHECK_ROLE_NAME,
    SSM_PREFIX,
)

AGENT_SPACE_NAME = f"{PROJECT}-agentspace"
OPERATOR_ROLE_NAME = f"{PROJECT}-devops-agent-operator-role"
LOG_GROUP_NAME = f"/{PROJECT}/devops-agent"
GATEWAY_NAME = f"{PROJECT}-mcp-gateway"


class DevOpsAgentLogGroup(Construct):
    """CloudWatch log group for DevOps Agent logs."""

    def __init__(self, scope: Construct, id: str) -> None:
        super().__init__(scope, id)

        self.log_group = logs.LogGroup(
            self, "LogGroup",
            log_group_name=LOG_GROUP_NAME,
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )


class DevOpsAgentOperatorRole(Construct):
    """IAM role assumed by the DevOps Agent web app operator."""

    def __init__(self, scope: Construct, id: str, *, account_id: str) -> None:
        super().__init__(scope, id)

        self.role = iam.Role(
            self, "OperatorRole",
            role_name=OPERATOR_ROLE_NAME,
            description="MAKITA DevOps Agent web app operator role",
            assumed_by=iam.ServicePrincipal(
                "aidevops.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:aidevops:{PRIMARY_REGION}:{account_id}:agentspace/*"
                    },
                },
            ),
        )

        # Managed policy for DevOps Agent operator access
        self.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AIDevOpsOperatorAppAccessPolicy"
            )
        )

        # Inline policy for additional permissions
        self.role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "devops-agent:GetAgentSpace",
                "devops-agent:ListAgentSpaces",
                "devops-agent:InvokeAgent",
            ],
            resources=[f"arn:aws:aidevops:{PRIMARY_REGION}:{account_id}:agentspace/*"],
        ))
        self.role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock-agentcore:InvokeAgentRuntime",
                "bedrock-agentcore:GetAgentRuntime",
                "bedrock-agentcore:GetGateway",
                "bedrock-agentcore:InvokeGateway",
            ],
            resources=[
                f"arn:aws:bedrock-agentcore:{PRIMARY_REGION}:{account_id}:runtime/*",
                f"arn:aws:bedrock-agentcore:{PRIMARY_REGION}:{account_id}:gateway/*",
            ],
        ))
        self.role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "rds:DescribeDBInstances",
                "rds:DescribeDBClusters",
            ],
            resources=[
                f"arn:aws:rds:*:{account_id}:db:{PROJECT}-*",
                f"arn:aws:rds:*:{account_id}:cluster:{PROJECT}-*",
            ],
        ))
        self.role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:*:{account_id}:parameter{SSM_PREFIX}/*"],
        ))
        self.role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudwatch:GetMetricData",
                "cloudwatch:DescribeAlarms",
                "logs:GetLogEvents",
                "logs:DescribeLogGroups",
            ],
            resources=[
                f"arn:aws:cloudwatch:{PRIMARY_REGION}:{account_id}:alarm:{PROJECT}-*",
                f"arn:aws:logs:{PRIMARY_REGION}:{account_id}:log-group:/{PROJECT}/*",
            ],
        ))


class DevOpsAgentSpace(Construct):
    """
    Custom resource that creates the DevOps Agent Space, associates
    the AWS account, finds the AgentCore Gateway, and enables the
    web app operator.

    Uses AwsCustomResource to call the DevOps Agent SDK APIs since
    there are no native CloudFormation resources for this service.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        account_id: str,
        operator_role: iam.IRole,
        failover_role_arn: str,
    ) -> None:
        super().__init__(scope, id)

        # Policy for the custom resource Lambda to call DevOps Agent APIs
        custom_resource_policy = cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=[
                    "aidevops:CreateAgentSpace",
                    "aidevops:DeleteAgentSpace",
                    "aidevops:GetAgentSpace",
                    "devops-agent:CreateAgentSpace",
                    "devops-agent:DeleteAgentSpace",
                    "devops-agent:GetAgentSpace",
                ],
                resources=[f"arn:aws:aidevops:{PRIMARY_REGION}:{account_id}:agentspace/*"],
            ),
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore-control:GetGateway",
                    "bedrock-agentcore-control:ListGateways",
                ],
                resources=[f"arn:aws:bedrock-agentcore:{PRIMARY_REGION}:{account_id}:gateway/*"],
            ),
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[
                    operator_role.role_arn,
                    failover_role_arn,
                ],
            ),
            iam.PolicyStatement(
                actions=["iam:CreateServiceLinkedRole"],
                resources=[f"arn:aws:iam::{account_id}:role/aws-service-role/*"],
            ),
        ])

        # Create Agent Space (without tags to avoid serialization issues)
        self.create_space = cr.AwsCustomResource(
            self, "CreateAgentSpace",
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="devops-agent",
                action="createAgentSpace",
                parameters={
                    "name": AGENT_SPACE_NAME,
                    "description": "MAKITA DevOps Agent Space for PostgreSQL DR operations",
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("agentSpace.agentSpaceId"),
            ),
            on_delete=cr.AwsSdkCall(
                service="devops-agent",
                action="deleteAgentSpace",
                parameters={
                    "agentSpaceId": cr.PhysicalResourceId.of("agentSpaceId"),
                },
            ),
            policy=custom_resource_policy,
        )

        # Store the agent space ID
        self.agent_space_id = self.create_space.get_response_field("agentSpace.agentSpaceId")

        # Associate the current AWS account as the primary (monitor) account
        self.source_association = devopsagent.CfnAssociation(
            self, "SourceAwsAssociation",
            agent_space_id=self.agent_space_id,
            service_id="aws",
            configuration=devopsagent.CfnAssociation.ServiceConfigurationProperty(
                aws=devopsagent.CfnAssociation.AWSConfigurationProperty(
                    account_id=account_id,
                    account_type="monitor",
                    assumable_role_arn=operator_role.role_arn,
                ),
            ),
        )
        self.source_association.node.add_dependency(self.create_space)
