# Builds S3 components of MAKI
import aws_cdk as cdk
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3deploy
import aws_cdk.aws_lambda as _lambda
import config
import random
import datetime

# Builds S3 components of MAKI
import aws_cdk as cdk
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3deploy
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
