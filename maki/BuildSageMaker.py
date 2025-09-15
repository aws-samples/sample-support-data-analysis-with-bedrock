import aws_cdk as cdk
import aws_cdk.aws_sagemaker as sagemaker
import aws_cdk.aws_iam as iam
import aws_cdk.aws_kms as kms
import sys
sys.path.append('..')
import config
sys.path.append('utils')
import utils


def buildNotebookInstance(self, execution_role, vpc, security_group):
    # Create KMS key for SageMaker notebook encryption
    kms_key = kms.Key(
        self, f"{utils.returnName(config.SAGEMAKER_NOTEBOOK_NAME)}-kms-key",
        description="KMS key for SageMaker notebook instance encryption",
        enable_key_rotation=True,
        removal_policy=cdk.RemovalPolicy.DESTROY
    )
    
    # Get private subnets from VPC
    private_subnets = vpc.private_subnets
    if not private_subnets:
        raise ValueError("No private subnets found in VPC for SageMaker notebook")
    
    notebook = sagemaker.CfnNotebookInstance(
        self, utils.returnName(config.SAGEMAKER_NOTEBOOK_NAME),
        instance_type=config.SAGEMAKER_INSTANCE_TYPE,
        role_arn=execution_role.role_arn,
        # notebook_instance_name=utils.returnName(config.SAGEMAKER_NOTEBOOK_NAME),  # Removed to allow CloudFormation auto-naming
        # Place in VPC (AwsSolutions-SM1)
        subnet_id=private_subnets[0].subnet_id,
        security_group_ids=[security_group.security_group_id],
        # Disable direct internet access (AwsSolutions-SM3)
        direct_internet_access="Disabled",
        # Enable storage encryption (AwsSolutions-SM2)
        kms_key_id=kms_key.key_arn
    )
    
    notebook.node.add_dependency(execution_role)
    notebook.node.add_dependency(vpc)
    notebook.node.add_dependency(security_group)
    notebook.node.add_dependency(kms_key)
    
    return notebook
