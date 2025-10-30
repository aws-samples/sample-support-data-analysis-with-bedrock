"""
MAKI OpenSearch Serverless Components Builder

This module creates OpenSearch Serverless infrastructure for MAKI's health events 
processing mode, providing vector search capabilities and scalable event storage.

Purpose:
- Create OpenSearch Serverless collection for health events storage
- Configure security policies for encryption, network access, and data access
- Enable vector search capabilities for semantic analysis
- Provide dashboard access for data exploration and monitoring

Components Created:
- OpenSearch Serverless collection with search optimization
- Encryption policy using AWS-owned keys
- Network policy allowing public access (secured by data access policy)
- Data access policy with least-privilege permissions
- IAM policies for dashboard access and collection management

Key Features:
- Serverless architecture with automatic scaling
- Vector search support for semantic similarity
- Comprehensive security policy configuration
- Integration with MAKI execution role and current user
- Dashboard access for data visualization and debugging

Security Configuration:
- Encryption at rest using AWS-owned keys
- Network access controlled through security policies
- Data access restricted to MAKI execution role and deploying user
- Separate permissions for collection operations and index management

Usage:
- Deployed by MakiEmbeddings stack for health events mode
- Stores health events with vector embeddings for semantic search
- Provides scalable storage for large volumes of health data
- Enables advanced querying and similarity search capabilities
"""

import aws_cdk as cdk
import aws_cdk.aws_opensearchserverless as opensearch
import aws_cdk.aws_iam as iam
import aws_cdk.custom_resources as cr
import config
import sys
sys.path.append('utils')
import utils

def buildOpenSearchCollection(self, execution_role):
    """Build OpenSearch Serverless collection for health events"""
    
    collection_name = config.OPENSEARCH_COLLECTION_NAME
    
    # Get current caller identity to add to access policy
    import boto3
    sts_client = boto3.client("sts")
    caller_arn = sts_client.get_caller_identity()["Arn"]
    
    # Create encryption policy first
    encryption_policy = opensearch.CfnSecurityPolicy(
        self, utils.returnName("opensearch-encryption-policy"),
        name=f"{collection_name}-encryption-policy",
        type="encryption",
        policy=f"""{{
            "Rules": [{{
                "ResourceType": "collection",
                "Resource": ["collection/{collection_name}"]
            }}],
            "AWSOwnedKey": true
        }}"""
    )
    
    # Create network policy for public access with dashboard access enabled
    network_policy = opensearch.CfnSecurityPolicy(
        self, utils.returnName("opensearch-network-policy"),
        name=f"{collection_name}-network-policy",
        type="network",
        policy=f"""[{{
            "Rules": [{{
                "ResourceType": "collection",
                "Resource": ["collection/{collection_name}"]
            }}, {{
                "ResourceType": "dashboard",
                "Resource": ["collection/{collection_name}"]
            }}],
            "AllowFromPublic": true
        }}]"""
    )
    
    # Create access policy with execution role and current caller
    principals = [execution_role.role_arn, caller_arn]
    
    import json
    
    access_policy = opensearch.CfnAccessPolicy(
        self, utils.returnName("opensearch-access-policy"),
        name=f"{collection_name}-access-policy",
        type="data",
        policy=json.dumps([{
            "Rules": [{
                "ResourceType": "index",
                "Resource": [f"index/{collection_name}/*", f"index/{collection_name}/amazon-health-events"],
                "Permission": ["aoss:CreateIndex", "aoss:DeleteIndex", "aoss:UpdateIndex", "aoss:DescribeIndex", "aoss:ReadDocument", "aoss:WriteDocument"]
            }, {
                "ResourceType": "collection",
                "Resource": [f"collection/{collection_name}"],
                "Permission": ["aoss:CreateCollectionItems", "aoss:DeleteCollectionItems", "aoss:UpdateCollectionItems", "aoss:DescribeCollectionItems"]
            }],
            "Principal": principals
        }])
    )
    
    # Create OpenSearch Serverless collection
    collection = opensearch.CfnCollection(
        self, utils.returnName("opensearch-collection"),
        name=collection_name,
        type="SEARCH"
    )
    
    # Add dependencies
    collection.add_dependency(encryption_policy)
    collection.add_dependency(network_policy)
    collection.add_dependency(access_policy)
    
    # Create IAM policy for dashboard access
    dashboard_iam_policy = iam.Policy(
        self, utils.returnName("maki-aoss-dashboard"),
        policy_name="maki-aoss-dashboard",
        document=iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["aoss:APIAccessAll"],
                    resources=[f"arn:aws:aoss:{config.REGION}:{config.account_id}:collection/{collection_name}"]
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["aoss:DashboardsAccessAll"],
                    resources=[f"arn:aws:aoss:{config.REGION}:{config.account_id}:dashboards/default"]
                )
            ]
        )
    )
    
    # Attach policy to execution role
    execution_role.attach_inline_policy(dashboard_iam_policy)
    
    # Output the endpoint for reference
    endpoint = collection.attr_collection_endpoint
    
    cdk.CfnOutput(
        self, "OpenSearchEndpoint",
        value=endpoint,
        description="OpenSearch Serverless collection endpoint"
    )
    
    return collection, endpoint
