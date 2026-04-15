"""
MAKITA DevOps Agent CDK Stack

Deploys the infrastructure for the Amazon DevOps Agent integration:
- IAM operator role for the DevOps Agent web app
- CloudWatch log group for agent logs
- DevOps Agent Space (via custom resource)

Prerequisites:
- AgentCore Gateway must be deployed first (deploy_agentcore.py)
- PostgreSQL stacks must be deployed for the failover role

Usage:
    cdk deploy MakitaDevOpsAgent --app "python3 infra/app.py"
"""

from constructs import Construct
from aws_cdk import Stack, CfnOutput, Tags

from config import (
    PROJECT,
    TAGS,
    PRIMARY_REGION,
    FAILOVER_ROLE_NAME,
)
from resources.devops_agent import (
    DevOpsAgentLogGroup,
    DevOpsAgentOperatorRole,
    DevOpsAgentSpace,
    AGENT_SPACE_NAME,
    OPERATOR_ROLE_NAME,
    LOG_GROUP_NAME,
)


class MakitaDevOpsAgentStack(Stack):
    """Stack for MAKITA DevOps Agent resources."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_id = self.account
        failover_role_arn = f"arn:aws:iam::{account_id}:role/{FAILOVER_ROLE_NAME}"

        # CloudWatch log group
        log_group = DevOpsAgentLogGroup(self, "AgentLogGroup")

        # IAM operator role
        operator_role = DevOpsAgentOperatorRole(
            self, "AgentOperatorRole",
            account_id=account_id,
        )

        # DevOps Agent Space (custom resource)
        agent_space = DevOpsAgentSpace(
            self, "AgentSpace",
            account_id=account_id,
            operator_role=operator_role.role,
            failover_role_arn=failover_role_arn,
        )
        agent_space.node.add_dependency(operator_role)
        agent_space.node.add_dependency(log_group)

        # Outputs
        CfnOutput(self, "AgentSpaceName",
                  value=AGENT_SPACE_NAME,
                  description="DevOps Agent Space name")

        CfnOutput(self, "OperatorRoleName",
                  value=OPERATOR_ROLE_NAME,
                  description="DevOps Agent operator IAM role")

        CfnOutput(self, "LogGroupName",
                  value=LOG_GROUP_NAME,
                  description="DevOps Agent CloudWatch log group")

        CfnOutput(self, "ConsoleUrl",
                  value=f"https://{PRIMARY_REGION}.console.aws.amazon.com/devops-agent/home?region={PRIMARY_REGION}",
                  description="DevOps Agent console URL")
