"""
MAKITA PostgreSQL Replica Stack (us-west-2)

Deploys the cross-region read replica infrastructure:
- VPC with private subnets in DR region
- KMS key for replica encryption
- RDS PostgreSQL read replica from primary in us-east-1

Prerequisites:
- MakitaPostgresql stack must be deployed first in us-east-1

Usage:
    cdk deploy MakitaPostgresqlReplica --app "python3 infra/app.py"
"""

from constructs import Construct
from aws_cdk import Stack, CfnOutput

from config import PROJECT
from resources.postgresql import DrNetworking, ReplicaDatabase


class MakitaPostgresqlReplicaStack(Stack):
    """DR region PostgreSQL replica stack."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        primary_instance_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Networking
        networking = DrNetworking(self, "DrNetworking")

        # Replica database
        database = ReplicaDatabase(
            self, "ReplicaDatabase",
            vpc=networking.vpc,
            security_group=networking.security_group,
            source_instance_arn=primary_instance_arn,
        )

        # Outputs
        CfnOutput(self, "ReplicaEndpoint",
                  value=database.instance.db_instance_endpoint_address,
                  export_name=f"{PROJECT}-replica-endpoint")

        CfnOutput(self, "ReplicaInstanceArn",
                  value=database.instance.instance_arn,
                  export_name=f"{PROJECT}-replica-instance-arn")
