#!/usr/bin/env python3
"""Generate IAM policy JSON for AgentCore runtime roles.

Outputs a JSON policy document to policies/iam/agentcore-runtime-policy.json
that grants the permissions needed by the 3 PostgreSQL MCP server runtimes.
"""

import json
import os
import sys

import boto3

PROJECT = "makita"
SSM_PREFIX = "/makita"


def get_account_id() -> str:
    return boto3.client("sts").get_caller_identity()["Account"]


def generate_policy(account_id: str) -> dict:
    """Build the IAM policy document for AgentCore runtimes."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "RDSFailover",
                "Effect": "Allow",
                "Action": [
                    "rds:PromoteReadReplica",
                    "rds:DescribeDBInstances",
                    "rds:DescribeDBClusters",
                    "rds:RebootDBInstance",
                ],
                "Resource": [
                    f"arn:aws:rds:*:{account_id}:db:{PROJECT}-*",
                    f"arn:aws:rds:*:{account_id}:cluster:{PROJECT}-*",
                ],
            },
            {
                "Sid": "SSMParameters",
                "Effect": "Allow",
                "Action": [
                    "ssm:GetParameter",
                    "ssm:PutParameter",
                ],
                "Resource": f"arn:aws:ssm:*:{account_id}:parameter{SSM_PREFIX}/*",
            },
            {
                "Sid": "ECRAuth",
                "Effect": "Allow",
                "Action": "ecr:GetAuthorizationToken",
                "Resource": "*",
            },
            {
                "Sid": "ECRPull",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchCheckLayerAvailability",
                ],
                "Resource": f"arn:aws:ecr:*:{account_id}:repository/cdk-*",
            },
            {
                "Sid": "AgentCoreRuntime",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntimeEndpoint",
                ],
                "Resource": f"arn:aws:bedrock-agentcore:*:{account_id}:runtime/*",
            },
            {
                "Sid": "LambdaInvoke",
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": f"arn:aws:lambda:*:{account_id}:function:{PROJECT}-*",
            },
        ],
    }


def main():
    account_id = get_account_id()
    policy = generate_policy(account_id)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "policies", "iam")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "agentcore-runtime-policy.json")

    with open(out_path, "w") as f:
        json.dump(policy, f, indent=2)
        f.write("\n")

    print(f"Generated {out_path} for account {account_id}")


if __name__ == "__main__":
    main()
