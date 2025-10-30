#!/usr/bin/env python3
"""
MAKI (Machine Augmented Key Insights) CDK Application

This is the main CDK application entry point for deploying the MAKI infrastructure,
which provides automated analysis of AWS Enterprise Support cases and Health events
using Amazon Bedrock for machine learning insights.

Purpose:
- Deploy comprehensive MAKI infrastructure across three logical stacks
- Configure AWS CDK environment and deployment parameters
- Implement security best practices with CDK NAG compliance checking
- Manage stack dependencies and deployment ordering
- Apply consistent tagging and resource management policies

Architecture Overview:
MAKI consists of three main CDK stacks deployed in sequence:

1. MakiFoundations Stack:
   - Core infrastructure (VPC, IAM, S3, Lambda, Step Functions)
   - CloudWatch logging and monitoring
   - SageMaker notebook for analysis
   - SSM parameters for configuration management

2. MakiData Stack:
   - Reference data deployment (category examples and descriptions)
   - Support case categorization templates
   - Example data for all 16 predefined categories

3. MakiEmbeddings Stack:
   - OpenSearch Serverless collection for health events
   - Vector embedding capabilities for semantic search
   - Health events processing infrastructure

Key Features:
- Dual processing modes: Support Cases and Health Events
- Scalable processing: On-demand and batch inference
- Comprehensive security: IAM least-privilege access
- Cost optimization: Lifecycle policies and resource sizing
- Monitoring: CloudWatch integration and X-Ray tracing
- Compliance: CDK NAG security checks and suppressions

Deployment Order:
1. MakiFoundations (required first - provides core infrastructure)
2. MakiData (depends on foundations - deploys reference data)
3. MakiEmbeddings (depends on foundations - adds health events support)

Environment Configuration:
- Account: Uses CDK_DEFAULT_ACCOUNT environment variable
- Region: Uses CDK_DEFAULT_REGION environment variable (defaults to us-east-1)
- Tags: Applied consistently across all resources

Security and Compliance:
- CDK NAG integration for AWS Solutions compliance checking
- Specific suppressions for acceptable sample code patterns
- IAM wildcard permissions justified for Bedrock batch inference limitations
- Lambda runtime versions managed appropriately for sample code

Usage:
- Deploy all stacks: cdk deploy --all
- Deploy specific stack: cdk deploy MakiFoundations
- Synthesize templates: cdk synth
- Destroy infrastructure: cdk destroy --all

Prerequisites:
- AWS CDK v2 installed and configured
- AWS CLI configured with appropriate permissions
- Python 3.9+ with required dependencies
- Bedrock model access enabled for required models

Resource Management:
- Auto-delete tag set to "no" for production safety
- Project tag "maki" applied to all resources
- Stack dependencies properly configured
- Environment-specific resource naming
"""

import os

import aws_cdk as cdk

from cdk_nag import AwsSolutionsChecks, NagSuppressions

from maki.maki_stack import MakiFoundations, MakiData, MakiEmbeddings, MakiAgents

app = cdk.App()

# Define environment
env = cdk.Environment(
    account=os.environ.get('CDK_DEFAULT_ACCOUNT'),
    region=os.environ.get('CDK_DEFAULT_REGION', 'us-east-1')
)

foundations_stack = MakiFoundations(app, "MakiFoundations", env=env, description='Machine Augmented Key Insights (MAKI) foundational layer')
data_stack = MakiData(app, "MakiData", env=env, description='Machine Augmented Key Insights (MAKI) data layer')
embeddings_stack = MakiEmbeddings(app, "MakiEmbeddings", env=env, description='Machine Augmented Key Insights (MAKI) embeddings layer')
agents_stack = MakiAgents(app, "MakiAgents", env=env, description='Machine Augmented Key Insights (MAKI) agents layer')

data_stack.add_dependency(foundations_stack)
embeddings_stack.add_dependency(foundations_stack)
agents_stack.add_dependency(foundations_stack)
agents_stack.add_dependency(data_stack)
agents_stack.add_dependency(embeddings_stack)
cdk.Tags.of(app).add("project", "maki")
cdk.Tags.of(app).add("auto-delete", "no")
cdk.Aspects.of(app).add(AwsSolutionsChecks())
NagSuppressions.add_stack_suppressions(foundations_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Wildcard permissions are acceptable for sample code.  Also Bedrock batch inference has no way to make this more granular."},
    {"id": "AwsSolutions-L1", "reason": "Lambda runtime version is acceptable for sample code."},
    {"id": "AwsSolutions-IAM4", "reason": "EventBridge health processor requires AWS managed policy for Lambda execution"},
])
NagSuppressions.add_stack_suppressions(data_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Wildcard permissions are acceptable for sample code."},
    {"id": "AwsSolutions-L1", "reason": "BucketDeployment creates internal Lambda function with CDK-managed runtime version"},
    {"id": "AwsSolutions-IAM4", "reason": "BucketDeployment creates internal Lambda function with CDK-managed runtime version"},
])
NagSuppressions.add_stack_suppressions(embeddings_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Wildcard permissions are acceptable for sample code."},
    {"id": "AwsSolutions-L1", "reason": "Lambda runtime version is acceptable for sample code."},
    {"id": "AwsSolutions-IAM4", "reason": "Custom resource requires AWS managed policy for Lambda execution"},
])
NagSuppressions.add_stack_suppressions(agents_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Wildcard permissions are acceptable for sample code and required for OpenSearch Serverless access."},
])
app.synth()
