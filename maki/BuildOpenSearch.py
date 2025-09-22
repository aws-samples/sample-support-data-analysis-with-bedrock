# Builds OpenSearch components of MAKI
import aws_cdk as cdk
import aws_cdk.aws_opensearchserverless as opensearch
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_iam as iam
import config
import sys
sys.path.append('utils')
import utils

def buildOpenSearchDomain(self, vpc, security_group, execution_role):
    """Build OpenSearch domain for health events"""
    
    domain_name = config.OPENSEARCH_DOMAIN_NAME
    
    # Create OpenSearch domain
    domain = opensearch.CfnCollection(
        self, utils.returnName("opensearch-domain"),
        name=domain_name,
        type="SEARCH"
    )
    
    # Create access policy
    access_policy = opensearch.CfnAccessPolicy(
        self, utils.returnName("opensearch-access-policy"),
        name=f"{domain_name}-access-policy",
        type="data",
        policy=f"""[{{
            "Rules": [{{
                "ResourceType": "index",
                "Resource": ["index/{domain_name}/*"],
                "Permission": ["aoss:*"]
            }}, {{
                "ResourceType": "collection",
                "Resource": ["collection/{domain_name}"],
                "Permission": ["aoss:*"]
            }}],
            "Principal": ["{execution_role.role_arn}"]
        }}]"""
    )
    
    # Create network policy for VPC access
    network_policy = opensearch.CfnSecurityPolicy(
        self, utils.returnName("opensearch-network-policy"),
        name=f"{domain_name}-network-policy",
        type="network",
        policy=f"""[{{
            "Rules": [{{
                "ResourceType": "collection",
                "Resource": ["collection/{domain_name}"],
                "AllowFromPublic": false
            }}],
            "AllowFromPublic": false
        }}]"""
    )
    
    # Create encryption policy
    encryption_policy = opensearch.CfnSecurityPolicy(
        self, utils.returnName("opensearch-encryption-policy"),
        name=f"{domain_name}-encryption-policy",
        type="encryption",
        policy=f"""{{
            "Rules": [{{
                "ResourceType": "collection",
                "Resource": ["collection/{domain_name}"]
            }}],
            "AWSOwnedKey": true
        }}"""
    )
    
    # Add dependencies
    domain.add_dependency(access_policy)
    domain.add_dependency(network_policy)
    domain.add_dependency(encryption_policy)
    
    # Output the endpoint for reference
    endpoint = f"https://{domain.attr_collection_endpoint}"
    
    cdk.CfnOutput(
        self, "OpenSearchEndpoint",
        value=endpoint,
        description="OpenSearch collection endpoint"
    )
    
    return domain, endpoint
