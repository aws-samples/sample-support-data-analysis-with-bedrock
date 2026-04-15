"""MAKITA Infrastructure Configuration Constants."""

import boto3

# General
PROJECT = "makita"
AUTO_DELETE = "no"
ENV = "prod1"

TAGS = {
    "auto-delete": AUTO_DELETE,
    "Env": ENV,
    "proj": PROJECT,
}

# Regions
PRIMARY_REGION = "us-east-1"
DR_REGION = "us-west-2"

# Networking
PRIMARY_VPC_CIDR = "10.0.0.0/16"
PRIMARY_SUBNET_A_CIDR = "10.0.1.0/24"
PRIMARY_SUBNET_B_CIDR = "10.0.2.0/24"
DR_VPC_CIDR = "10.1.0.0/16"

# RDS PostgreSQL
DB_ENGINE_VERSION = "16.6"
DB_INSTANCE_CLASS = "db.t3.medium"
DB_ALLOCATED_STORAGE = 20
DB_MAX_ALLOCATED_STORAGE = 100
DB_PORT = 5432
DB_NAME = "makitadb"
DB_MASTER_USERNAME = "makitaadmin"
DB_BACKUP_RETENTION = 7
PRIMARY_INSTANCE_ID = "makita-pg-primary"
REPLICA_INSTANCE_ID = "makita-pg-replica"
CLUSTER_NAME = "makita-pg-cluster"

# IAM Roles
FAILOVER_ROLE_NAME = "makita-failover-role"
PRECHECK_ROLE_NAME = "makita-precheck-role"
POSTCHECK_ROLE_NAME = "makita-postcheck-role"

# SSM Parameter Paths
SSM_PREFIX = "/makita"

# MCP Server Names
MCP_FAILOVER = "makita-postgresql-failover-mcp"
MCP_PRECHECK = "makita-postgresql-precheck-mcp"
MCP_POSTCHECK = "makita-postgresql-postcheck-mcp"
