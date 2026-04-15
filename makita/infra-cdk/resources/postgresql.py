"""
MAKITA PostgreSQL CDK Constructs

Creates the primary and DR PostgreSQL infrastructure including
VPC networking, RDS instances, IAM roles, SSM parameters,
Secrets Manager, and Bedrock Guardrails.
"""

from constructs import Construct
from aws_cdk import (
    Duration,
    RemovalPolicy,
    SecretValue,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_secretsmanager as secretsmanager,
    aws_kms as kms,
    aws_bedrock as bedrock,
)
from config import (
    PROJECT,
    PRIMARY_REGION,
    DR_REGION,
    PRIMARY_VPC_CIDR,
    PRIMARY_SUBNET_A_CIDR,
    PRIMARY_SUBNET_B_CIDR,
    DR_VPC_CIDR,
    DB_ENGINE_VERSION,
    DB_INSTANCE_CLASS,
    DB_ALLOCATED_STORAGE,
    DB_MAX_ALLOCATED_STORAGE,
    DB_PORT,
    DB_NAME,
    DB_MASTER_USERNAME,
    DB_BACKUP_RETENTION,
    PRIMARY_INSTANCE_ID,
    REPLICA_INSTANCE_ID,
    CLUSTER_NAME,
    FAILOVER_ROLE_NAME,
    PRECHECK_ROLE_NAME,
    POSTCHECK_ROLE_NAME,
    SSM_PREFIX,
)


class PrimaryNetworking(Construct):
    """VPC, subnets, and security group for the primary region."""

    def __init__(self, scope: Construct, id: str) -> None:
        super().__init__(scope, id)

        self.vpc = ec2.Vpc(
            self, "Vpc",
            vpc_name=f"{PROJECT}-vpc",
            ip_addresses=ec2.IpAddresses.cidr(PRIMARY_VPC_CIDR),
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"{PROJECT}-private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        self.security_group = ec2.SecurityGroup(
            self, "DbSg",
            vpc=self.vpc,
            security_group_name=f"{PROJECT}-db-sg",
            description="Security group for MAKITA PostgreSQL instances",
        )
        self.security_group.add_ingress_rule(
            ec2.Peer.ipv4(PRIMARY_VPC_CIDR),
            ec2.Port.tcp(DB_PORT),
            "Allow PostgreSQL access from within the VPC",
        )


class DrNetworking(Construct):
    """VPC, subnets, and security group for the DR region."""

    def __init__(self, scope: Construct, id: str) -> None:
        super().__init__(scope, id)

        self.vpc = ec2.Vpc(
            self, "DrVpc",
            vpc_name=f"{PROJECT}-dr-vpc",
            ip_addresses=ec2.IpAddresses.cidr(DR_VPC_CIDR),
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"{PROJECT}-dr-private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        self.security_group = ec2.SecurityGroup(
            self, "DrDbSg",
            vpc=self.vpc,
            security_group_name=f"{PROJECT}-dr-db-sg",
            description="Security group for MAKITA PostgreSQL replica in DR region",
        )
        self.security_group.add_ingress_rule(
            ec2.Peer.ipv4(DR_VPC_CIDR),
            ec2.Port.tcp(DB_PORT),
            "Allow PostgreSQL access from within the DR VPC",
        )


class PrimaryDatabase(Construct):
    """PostgreSQL primary instance with Secrets Manager credentials."""

    def __init__(
        self, scope: Construct, id: str, *,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
    ) -> None:
        super().__init__(scope, id)

        # Secrets Manager for master credentials
        self.secret = secretsmanager.Secret(
            self, "MasterSecret",
            secret_name=f"{PROJECT}-db-master-secret",
            description="Auto-generated master credentials for MAKITA PostgreSQL",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=f'{{"username": "{DB_MASTER_USERNAME}"}}',
                generate_string_key="password",
                password_length=32,
                exclude_characters='"@/\\',
            ),
        )

        # Primary RDS instance
        self.instance = rds.DatabaseInstance(
            self, "Primary",
            instance_identifier=PRIMARY_INSTANCE_ID,
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_6,
            ),
            instance_type=ec2.InstanceType(DB_INSTANCE_CLASS.replace("db.", "")),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[security_group],
            credentials=rds.Credentials.from_secret(self.secret),
            database_name=DB_NAME,
            port=DB_PORT,
            allocated_storage=DB_ALLOCATED_STORAGE,
            max_allocated_storage=DB_MAX_ALLOCATED_STORAGE,
            storage_type=rds.StorageType.GP3,
            storage_encrypted=True,
            multi_az=False,
            publicly_accessible=False,
            backup_retention=Duration.days(DB_BACKUP_RETENTION),
            copy_tags_to_snapshot=True,
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
        )


class ReplicaDatabase(Construct):
    """Cross-region PostgreSQL read replica using CfnDBInstance for cross-region support."""

    def __init__(
        self, scope: Construct, id: str, *,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
        source_instance_arn: str,
    ) -> None:
        super().__init__(scope, id)

        self.kms_key = kms.Key(
            self, "DrKmsKey",
            description="KMS key for MAKITA PostgreSQL replica encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Get private subnet IDs for the DB subnet group
        private_subnets = vpc.isolated_subnets

        subnet_group = rds.CfnDBSubnetGroup(
            self, "DrSubnetGroup",
            db_subnet_group_name=f"{PROJECT}-dr-db-subnet-group",
            db_subnet_group_description="Subnet group for MAKITA PostgreSQL replica",
            subnet_ids=[s.subnet_id for s in private_subnets],
        )

        # Use CfnDBInstance for cross-region replica — the L2 construct
        # doesn't support cross-region SourceDBInstanceIdentifier
        self.cfn_instance = rds.CfnDBInstance(
            self, "Replica",
            db_instance_identifier=REPLICA_INSTANCE_ID,
            source_db_instance_identifier=source_instance_arn,
            db_instance_class=DB_INSTANCE_CLASS,
            storage_type="gp3",
            kms_key_id=self.kms_key.key_arn,
            publicly_accessible=False,
            copy_tags_to_snapshot=True,
            deletion_protection=False,
            auto_minor_version_upgrade=True,
            db_subnet_group_name=subnet_group.db_subnet_group_name,
            vpc_security_groups=[security_group.security_group_id],
        )
        self.cfn_instance.add_dependency(subnet_group)

        # Expose as an IDatabase-like interface for outputs
        self.instance = rds.DatabaseInstance.from_database_instance_attributes(
            self, "ImportedReplica",
            instance_identifier=REPLICA_INSTANCE_ID,
            instance_endpoint_address=self.cfn_instance.attr_endpoint_address,
            instance_resource_id=self.cfn_instance.ref,
            port=DB_PORT,
            security_groups=[security_group],
        )


class McpServerRoles(Construct):
    """IAM roles for the three MCP servers (failover, precheck, postcheck)."""

    def __init__(self, scope: Construct, id: str, *, account_id: str) -> None:
        super().__init__(scope, id)

        agentcore_principal = iam.CompositePrincipal(
            iam.ServicePrincipal("lambda.amazonaws.com"),
            iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        )
        lambda_principal = iam.ServicePrincipal("lambda.amazonaws.com")

        # Failover role — RDS promote/reboot + SSM read/write
        self.failover_role = iam.Role(
            self, "FailoverRole",
            role_name=FAILOVER_ROLE_NAME,
            assumed_by=agentcore_principal,
        )
        self.failover_role.add_to_policy(iam.PolicyStatement(
            actions=["rds:PromoteReadReplica", "rds:DescribeDBInstances", "rds:RebootDBInstance"],
            resources=[f"arn:aws:rds:*:{account_id}:db:{PROJECT}-*"],
        ))
        self.failover_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:PutParameter", "ssm:GetParameter"],
            resources=[f"arn:aws:ssm:*:{account_id}:parameter{SSM_PREFIX}/*"],
        ))
        self.failover_role.add_to_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[f"arn:aws:lambda:*:{account_id}:function:{PROJECT}-*"],
        ))

        # ECR permissions — AgentCore needs these to pull container images
        self.failover_role.add_to_policy(iam.PolicyStatement(
            actions=["ecr:GetAuthorizationToken"],
            resources=["*"],
        ))
        self.failover_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ecr:BatchGetImage",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchCheckLayerAvailability",
            ],
            resources=[f"arn:aws:ecr:*:{account_id}:repository/cdk-*"],
        ))

        # AgentCore permissions — gateway needs to invoke runtimes
        self.failover_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock-agentcore:InvokeAgentRuntime",
                "bedrock-agentcore:GetAgentRuntime",
                "bedrock-agentcore:GetAgentRuntimeEndpoint",
            ],
            resources=[f"arn:aws:bedrock-agentcore:*:{account_id}:runtime/*"],
        ))

        # Precheck role — read-only RDS + SSM
        self.precheck_role = iam.Role(
            self, "PrecheckRole",
            role_name=PRECHECK_ROLE_NAME,
            assumed_by=lambda_principal,
        )
        self._add_readonly_policy(self.precheck_role, account_id)

        # Postcheck role — read-only RDS + SSM
        self.postcheck_role = iam.Role(
            self, "PostcheckRole",
            role_name=POSTCHECK_ROLE_NAME,
            assumed_by=lambda_principal,
        )
        self._add_readonly_policy(self.postcheck_role, account_id)

    def _add_readonly_policy(self, role: iam.Role, account_id: str):
        role.add_to_policy(iam.PolicyStatement(
            actions=["rds:DescribeDBInstances", "rds:DescribeDBClusters"],
            resources=[
                f"arn:aws:rds:*:{account_id}:db:{PROJECT}-*",
                f"arn:aws:rds:*:{account_id}:cluster:{PROJECT}-*",
            ],
        ))
        role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:*:{account_id}:parameter{SSM_PREFIX}/*"],
        ))


class MakitaSsmParameters(Construct):
    """SSM Parameter Store entries for cluster configuration."""

    def __init__(
        self, scope: Construct, id: str, *,
        primary_endpoint: str,
        replica_endpoint: str,
        account_id: str,
    ) -> None:
        super().__init__(scope, id)

        params = {
            "db/primary-endpoint": primary_endpoint,
            "db/replica-endpoint": replica_endpoint,
            "db/primary-region": PRIMARY_REGION,
            "db/dr-region": DR_REGION,
            "db/cluster-name": CLUSTER_NAME,
            "db/replication-status": "active",
            "db/port": str(DB_PORT),
            "mcp/failover-server-arn": f"arn:aws:agentcore:{PRIMARY_REGION}:{account_id}:mcp-server/{PROJECT}-postgresql-failover-mcp",
            "mcp/precheck-server-arn": f"arn:aws:agentcore:{PRIMARY_REGION}:{account_id}:mcp-server/{PROJECT}-postgresql-precheck-mcp",
            "mcp/postcheck-server-arn": f"arn:aws:agentcore:{PRIMARY_REGION}:{account_id}:mcp-server/{PROJECT}-postgresql-postcheck-mcp",
        }

        for key, value in params.items():
            ssm.StringParameter(
                self, key.replace("/", "-"),
                parameter_name=f"{SSM_PREFIX}/{key}",
                string_value=value,
                description=f"MAKITA {key}",
            )
