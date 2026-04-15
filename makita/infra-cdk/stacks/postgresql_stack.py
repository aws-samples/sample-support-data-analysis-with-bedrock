"""
MAKITA PostgreSQL Primary Stack (us-east-1)

Deploys the primary PostgreSQL infrastructure:
- VPC with private subnets across 2 AZs
- RDS PostgreSQL primary instance with Secrets Manager credentials
- IAM roles for failover, precheck, and postcheck MCP servers
- SSM parameters for cluster configuration
- Bedrock Guardrails for each MCP server

Usage:
    cdk deploy MakitaPostgresql --app "python3 infra/app.py"
"""

from constructs import Construct
from aws_cdk import Stack, CfnOutput

from config import PROJECT
from resources.postgresql import (
    PrimaryNetworking,
    PrimaryDatabase,
    McpServerRoles,
    MakitaSsmParameters,
)


class MakitaPostgresqlStack(Stack):
    """Primary region PostgreSQL stack."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_id = self.account

        # Networking
        networking = PrimaryNetworking(self, "Networking")

        # Database
        database = PrimaryDatabase(
            self, "Database",
            vpc=networking.vpc,
            security_group=networking.security_group,
        )

        # Expose for cross-stack reference
        self.primary_instance = database.instance

        # IAM roles
        roles = McpServerRoles(self, "Roles", account_id=account_id)

        # SSM parameters
        MakitaSsmParameters(
            self, "SsmParams",
            primary_endpoint=database.instance.db_instance_endpoint_address,
            replica_endpoint="pending-replica-deployment",
            account_id=account_id,
        )

        # Outputs
        CfnOutput(self, "PrimaryEndpoint",
                  value=database.instance.db_instance_endpoint_address,
                  export_name=f"{PROJECT}-primary-endpoint")

        CfnOutput(self, "PrimaryInstanceArn",
                  value=database.instance.instance_arn,
                  export_name=f"{PROJECT}-primary-instance-arn")

        CfnOutput(self, "DbMasterSecretArn",
                  value=database.secret.secret_arn,
                  export_name=f"{PROJECT}-db-master-secret-arn")

        CfnOutput(self, "FailoverRoleArn",
                  value=roles.failover_role.role_arn,
                  export_name=f"{PROJECT}-failover-role-arn")

        CfnOutput(self, "PrecheckRoleArn",
                  value=roles.precheck_role.role_arn,
                  export_name=f"{PROJECT}-precheck-role-arn")

        CfnOutput(self, "PostcheckRoleArn",
                  value=roles.postcheck_role.role_arn,
                  export_name=f"{PROJECT}-postcheck-role-arn")
