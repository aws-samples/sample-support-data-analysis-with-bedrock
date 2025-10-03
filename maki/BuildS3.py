"""
MAKI S3 Storage Components Builder

This module creates the comprehensive S3 storage infrastructure for MAKI, including
data buckets, access logging, lifecycle policies, and initial data deployment.

Purpose:
- Create secure S3 buckets for all MAKI data storage needs
- Configure lifecycle policies for cost optimization
- Enable access logging for security and compliance
- Deploy initial reference data and examples

S3 Buckets Created:
- Cases aggregation: Support case data and processing results
- Health aggregation: Health events data and processing results
- Report: Final analysis outputs and summaries
- Archive: Long-term storage of processed data
- Batches: Bedrock batch inference job data
- LLM output: Direct model outputs and intermediate results

Key Features:
- Server-side encryption with S3-managed keys
- Versioning enabled for data protection
- Block public access for security
- SSL enforcement for data in transit
- Lifecycle rules for automatic cost optimization
- Access logging for audit and compliance
- Auto-delete on stack removal for development environments

Security Configuration:
- All buckets block public access by default
- SSL/TLS enforcement for all requests
- Server-side encryption enabled
- Access logging to dedicated logging buckets
- IAM-based access control integration

Data Deployment:
- Automatic deployment of category examples and reference data
- Support for both support cases and health events categories
- Configurable deployment paths and prefixes
"""

import aws_cdk as cdk
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3deploy
import aws_cdk.aws_lambda as _lambda
import config
import random
import datetime

def deployS3(self, bucketName, sourceDir, category_prefix):
    # deploy S3 files
    key = 'DeployCaseExamples-' + str(random.random()) + str(datetime.datetime.now())
    key2 = 'DeployBucket' + str(random.random()) + str(datetime.datetime.now())
    s3deploy.BucketDeployment(self, key,
        sources=[s3deploy.Source.asset(sourceDir)],
        destination_key_prefix=category_prefix,
        destination_bucket=s3.Bucket.from_bucket_name(self, key2, bucketName)
    )

def buildS3Bucket(self,role,bucketName):
    # S3 bucket for MAKI
    #bucketName = utils.returnName(config.BUCKET_NAME_BASE) 

    lifecycleRaw = s3.LifecycleRule(
        enabled=True,
        id=config.KEY + '-' + config.LCDAYS_POLICY,
        transitions=[
            s3.Transition(storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                transition_after=cdk.Duration.days(config.LCDAYS)
            )
        ]
    )

    # Create access logs bucket
    access_logs_bucket = s3.Bucket(self, f"{bucketName}-access-logs",
        bucket_name=f"{bucketName}-access-logs",
        public_read_access=False,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        encryption=s3.BucketEncryption.S3_MANAGED,
        enforce_ssl=True,
        auto_delete_objects=True,
        removal_policy=cdk.RemovalPolicy.DESTROY
    )

    bucket = s3.Bucket(self, bucketName, 
        bucket_name=bucketName,
        public_read_access=False,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        encryption=s3.BucketEncryption.S3_MANAGED,
        enforce_ssl=True,
        versioned=True,
        auto_delete_objects=True,
        removal_policy=cdk.RemovalPolicy.DESTROY,
        lifecycle_rules=[lifecycleRaw],
        # Enable server access logging
        server_access_logs_bucket=access_logs_bucket,
        server_access_logs_prefix=f"{bucketName}-access-logs/"
    )

    bucket.node.add_dependency(role) # add dependency
    access_logs_bucket.node.add_dependency(role) # add dependency for access logs bucket

    return bucket
