# Builds IAM components of MAKI
import aws_cdk.aws_iam as iam
import sys
sys.path.append('..')
import config
sys.path.append('utils')
import utils

# this role is used to retrieve cases across the organization
def buildMakiRole(self):

    # trust principal
    trust_principal = iam.CompositePrincipal(
        iam.ServicePrincipal("lambda.amazonaws.com"),
        iam.ServicePrincipal("states.amazonaws.com"),
        iam.ServicePrincipal("bedrock.amazonaws.com"),
        iam.ServicePrincipal("glue.amazonaws.com"),
        iam.ServicePrincipal("sagemaker.amazonaws.com") 
    )

    # Create the IAM role
    role = iam.Role(
        self, utils.returnName(config.EXEC_ROLE), 
        assumed_by = trust_principal,
        role_name = utils.returnName(config.EXEC_ROLE),
        description = utils.returnName(config.EXEC_ROLE)
    )

    # Resources policies
    role.add_to_policy(iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            "bedrock:ListModelInvocationJobs",
        ],
        resources=[
            "*" #This is currently the least privilege for this bedrock action
            #https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrock.html
        ]
        )       
    )

    # Add SageMaker permissions
    role.add_to_policy(iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            "sagemaker:CreateNotebookInstance",
            "sagemaker:DeleteNotebookInstance",
            "sagemaker:DescribeNotebookInstance",
            "sagemaker:StartNotebookInstance",
            "sagemaker:StopNotebookInstance"
        ],
        resources=["*"]
    ))
    role.add_to_policy(iam.PolicyStatement(
        effect=iam.Effect.ALLOW,
        actions=[
            "bedrock:InvokeModel",
            "bedrock:CreateModelInvocationJob",
            "bedrock:GetModelInvocationJob",
            "bedrock:ListFoundationModels",
            "bedrock:ListInferenceProfiles",
            "bedrock:ListInvocations",
            "bedrock:ListSessions",
            "s3:CreateBucket",
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:ListBucket",
            "s3:GetBucketLocation",
            "lambda:InvokeFunction",
            "lambda:UntagResource",
            "lambda:GetFunction",
            "lambda:ListFunctions",
            "events:PutRule",
            "events:DeleteRule",
            "events:PutTargets",
            "events:RemoveTargets",
            "events:ListRules",
            "events:EnableRule",
            "events:DisableRule",
            "states:StartExecution",
            "states:DescribeExecution",
            "states:ListExecutions",
            "states:StopExecution",
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:PutLogEvents",
            "iam:PassRole",
            "glue:GetDatabase",
            "glue:GetDatabases",
            "glue:CreateDatabase",
            "glue:UpdateDatabase",
            "glue:GetTable",
            "glue:GetTables",
            "glue:CreateTable",
            "glue:UpdateTable",
            "glue:DeleteTable",
            "glue:BatchGetPartition",
            "glue:BatchCreatePartition",
            "glue:GetPartition",
            "glue:GetPartitions",
            "glue:CreatePartition",
            "glue:UpdatePartition",
            "glue:DeletePartition",
            "glue:StartCrawler",
            "glue:StopCrawler",
            "glue:GetCrawler",
            "glue:GetCrawlers"
        ],
        resources=[
            "arn:aws:bedrock:*:" + config.account_id + ":inference-profile/*",
            "arn:aws:bedrock:*:" + config.account_id + ":model-invocation-job/*",
            "arn:aws:bedrock:*:" + config.account_id + ":model-invocation/*",
            "arn:aws:bedrock:" + "*::foundation-model/*",
            "arn:aws:s3:::" + config.KEY + "*",
            "arn:aws:s3:::" + 'cid-data-' + config.account_id + "*",
            "arn:aws:s3:::maki-fid-sample-support-case-data",
            "arn:aws:s3:::maki-fid-sample-support-case-data/*",
            "arn:aws:lambda:" + config.REGION + ":" + config.account_id + ":function:maki-*",
            "arn:aws:states:" + config.REGION + ":" + config.account_id + ":stateMachine:" + utils.returnName(config.STATE_MACHINE_NAME_BASE),
            "arn:aws:events:" + config.REGION + ":" + config.account_id + ":rule/maki-*",
            "arn:aws:logs:" + config.REGION + ":" + config.account_id + ":log-group:maki-*",
            "arn:aws:iam::" + config.account_id + ":role/" + utils.returnName(config.EXEC_ROLE),
            "arn:aws:logs:"  + config.REGION + ":" + config.account_id + ":log-group:/aws-glue/crawlers:*",
            "arn:aws:glue:" + config.REGION + ":" + config.account_id +  ":catalog",
            "arn:aws:glue:" + config.REGION + ":" + config.account_id +  ":database/*",
            "arn:aws:glue:" + config.REGION + ":" + config.account_id +  ":table/*",
            "arn:aws:glue:" + config.REGION + ":" + config.account_id +  ":crawler/*",
        ]
        )       
    )

    return role