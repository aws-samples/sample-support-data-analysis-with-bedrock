#!/usr/bin/env python3
"""
MAKITA CDK Application Entry Point

Stacks:
- Makita                   — Nested stack (PostgreSQL + AgentCore + DevOps Agent) in us-east-1
- MakitaPostgresqlReplica  — Cross-region read replica in us-west-2

Usage:
    cdk deploy Makita                                    # Deploy primary region
    cdk deploy MakitaPostgresqlReplica                   # Deploy replica (after primary)
    cdk deploy Makita MakitaPostgresqlReplica            # Deploy both
"""

import os
import aws_cdk as cdk

from stacks.makita_stack import MakitaStack
from stacks.postgresql_replica_stack import MakitaPostgresqlReplicaStack
from config import PRIMARY_INSTANCE_ID, DB_PORT

app = cdk.App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")

primary_env = cdk.Environment(
    account=account,
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

dr_env = cdk.Environment(
    account=account,
    region="us-west-2",
)

# Primary region: nested stack with PostgreSQL + AgentCore + DevOps Agent
makita_stack = MakitaStack(
    app, "Makita",
    env=primary_env,
    description="MAKITA - all infrastructure as nested stacks",
)

# DR region: cross-region replica
# Uses the primary instance ARN constructed from known identifiers
primary_region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
primary_instance_arn = f"arn:aws:rds:{primary_region}:{account}:db:{PRIMARY_INSTANCE_ID}"

replica_stack = MakitaPostgresqlReplicaStack(
    app, "MakitaPostgresqlReplica",
    env=dr_env,
    description="MAKITA PostgreSQL cross-region replica (us-west-2)",
    primary_instance_arn=primary_instance_arn,
)
replica_stack.add_dependency(makita_stack)

cdk.Tags.of(app).add("proj", "makita")
cdk.Tags.of(app).add("auto-delete", "no")
cdk.Tags.of(app).add("Env", "prod1")

app.synth()
