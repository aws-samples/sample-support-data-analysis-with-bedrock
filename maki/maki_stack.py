import sys
import config
from constructs import Construct
sys.path.append('utils')    
import utils

from aws_cdk import (
    Stack,
    CfnOutput,
    Fn,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_s3 as s3,
    aws_logs as logs,
    aws_cloudwatch as cw,
    aws_ec2 as ec2,
)

from . import (
    BuildIAM,
    BuildS3,
    BuildLambda,
    BuildEC2,
    BuildCloudWatch,
    BuildStateMachine,
    BuildEventBridge,
    BuildSageMaker,
    BuildOpenSearch,
    BuildSSM
)

from constructs import Construct

# Build the foundational layers of Maki
class MakiFoundations(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # build IAM
        makiRole = BuildIAM.buildMakiRole(self)

        # build VPC
        vpc = BuildEC2.buildVPC(self, makiRole)
        sg = BuildEC2.buildSecurityGroup(self, vpc) # needed for SageMaker notebook
        log_group = BuildCloudWatch.buildCWLogGroup(self,vpc)

        categoryBucketName = utils.returnName(config.BUCKET_NAME_CATEGORY_BASE)
        BuildS3.buildS3Bucket(self, makiRole, categoryBucketName)

        casesAggBucketName = utils.returnName(config.BUCKET_NAME_CASES_AGG_BASE)
        BuildS3.buildS3Bucket(self,makiRole,casesAggBucketName)

        batchesBucketName = utils.returnName(config.BUCKET_NAME_BATCHES)
        BuildS3.buildS3Bucket(self, makiRole, batchesBucketName)

        llmOutputBucketName = utils.returnName(config.BUCKET_NAME_LLM_BASE)
        BuildS3.buildS3Bucket(self,makiRole,llmOutputBucketName)

        reportBucketName = utils.returnName(config.BUCKET_NAME_REPORT_BASE)
        reportBucket = BuildS3.buildS3Bucket(self,makiRole,reportBucketName)

        archiveBucketName = utils.returnName(config.BUCKET_NAME_ARCHIVE)
        BuildS3.buildS3Bucket(self,makiRole,archiveBucketName)

        # Build SSM Parameters
        ssm_parameters = BuildSSM.buildSSMParameters(self)

        s3_utils_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.S3_UTILS_LAYER_PATH, 
            config.S3_UTILS_LAYER_DESC, 
            config.S3_UTILS_LAYER_NAME_BASE)
        
        json_utils_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.JSON_UTILS_LAYER_PATH, 
            config.JSON_UTILS_LAYER_DESC, 
            config.JSON_UTILS_LAYER_NAME_BASE)      

        prompt_gen_cases_input_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.PROMPT_GEN_CASES_INPUT_LAYER_PATH, 
            config.PROMPT_GEN_CASES_INPUT_LAYER_DESC, 
            config.PROMPT_GEN_CASES_INPUT_LAYER_NAME_BASE) 

        prompt_agg_cases_layer = BuildLambda.buildLambdaLayer(
            self,
            makiRole,
            config.PROMPT_AGG_CASES_LAYER_PATH,
            config.PROMPT_AGG_CASES_LAYER_DESC,
            config.PROMPT_AGG_CASES_LAYER_NAME_BASE
        )

        opensearch_utils_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.OPENSEARCH_UTILS_LAYER_PATH, 
            config.OPENSEARCH_UTILS_LAYER_DESC, 
            config.OPENSEARCH_UTILS_LAYER_NAME_BASE) 

        # build Lambda functions
        functions = {} 
    
        # check for batch inference jobs
        functions[config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE] = BuildLambda.buildCheckBatchInferenceJobs(
            self,
            makiRole,
            log_group
        )

        # check step functions jobs
        functions[config.CHECK_RUNNING_JOBS_NAME_BASE] = BuildLambda.buildCheckRunningJobs(
            self,
            makiRole,
            log_group
        )

        # check enabled models
        functions[config.CHECK_ENABLED_MODELS_NAME_BASE] = BuildLambda.buildCheckEnabledModels(
            self,
            makiRole,
            log_group
        )

        # gets cases from CID
        functions[config.GET_CID_CASES_NAME_BASE] = BuildLambda.buildGetCasesFromCID(
            self, 
            makiRole, 
            log_group, 
            prompt_gen_cases_input_layer, 
            s3_utils_layer, 
            json_utils_layer
        ) 

        # creates the Bedrock ondemand inference job
        functions[config.BEDROCK_ONDEMAND_INF_NAME_BASE] = BuildLambda.buildOnDemandInference(
            self,
            makiRole,
            log_group,
            s3_utils_layer,
            json_utils_layer,
            prompt_gen_cases_input_layer, 
            casesAggBucketName,
            reportBucketName
        )
     
        # create the Bedrock batch inference job
        functions[config.BEDROCK_BATCH_INF_JOB_NAME_BASE] = BuildLambda.buildBedrockBatchInferenceJob(
            self, 
            makiRole, 
            log_group, 
            s3_utils_layer,
            casesAggBucketName,
            batchesBucketName,
            llmOutputBucketName
        )
        
        # processes outputs from the Bedrock batch inference
        functions[config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE] = BuildLambda.buildBedrockProcessBatchOutput(
            self,
            makiRole,
            log_group,
            s3_utils_layer,
            json_utils_layer,
            prompt_agg_cases_layer,
            llmOutputBucketName,
            reportBucketName,
            archiveBucketName,
            batchesBucketName
        )

        #processes output from Bedrock ondemand inference
        functions[config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_NAME_BASE] = BuildLambda.buildBedrockProcessOnDemandOputput(
            self,
            makiRole,
            log_group,
            s3_utils_layer,
            json_utils_layer,
            prompt_agg_cases_layer,
            reportBucketName
        )

        functions[config.CLEAN_OUTPUT_FILES_NAME_BASE] = BuildLambda.buildCleanOutputFiles(
            self,
            makiRole,
            log_group,
            s3_utils_layer,
            reportBucketName
        )

        # Build health lambda with placeholder endpoint
        functions[config.GET_HEALTH_FROM_OPENSEARCH_NAME_BASE] = BuildLambda.buildGetHealthFromOpenSearch(
            self, 
            makiRole, 
            log_group, 
            prompt_gen_cases_input_layer, 
            s3_utils_layer, 
            json_utils_layer,
            opensearch_utils_layer,
            "placeholder-endpoint"  # Will be updated by MakiEmbeddings
        )

        # build State Machine
        state_machine = BuildStateMachine.buildStateMachine(self, functions, log_group)

        # build EventBridge
        # this is the overall cron that runs the state machine daily
        BuildEventBridge.buildMainCronJob(
            self, 
            state_machine
        )

        # build SageMaker notebook
        notebook = BuildSageMaker.buildNotebookInstance(self, makiRole, vpc, sg)
        
        # Export security group for other stacks
        CfnOutput(self, "SecurityGroupId", 
                 value=sg.security_group_id,
                 export_name="MakiSecurityGroupId")        

class MakiData(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # deploys example S3 files
        categoryBucketName = utils.returnName(config.BUCKET_NAME_CATEGORY_BASE)


        for category in config.CATEGORIES:
            sourceCategoryDir = config.CATEGORY_DIR + '/' + category
            BuildS3.deployS3(self, categoryBucketName, sourceCategoryDir, category) 

class MakiEmbeddings(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get existing resources from foundations stack
        makiRole = iam.Role.from_role_arn(
            self, "ImportedMakiRole",
            role_arn=f"arn:aws:iam::{config.account_id}:role/{utils.returnName(config.EXEC_ROLE)}"
        )

        log_group = logs.LogGroup.from_log_group_name(
            self, "ImportedLogGroup",
            log_group_name=utils.returnName(config.LOG_GROUP_NAME_BASE)
        )

        # OpenSearch Serverless doesn't require VPC configuration

        # Create OpenSearch Serverless collection first
        opensearch_collection, opensearch_endpoint = BuildOpenSearch.buildOpenSearchCollection(
            self, makiRole
        )

        # Create health aggregation S3 bucket
        healthAggBucketName = utils.returnName(config.BUCKET_NAME_HEALTH_AGG_BASE)
        BuildS3.buildS3Bucket(self, makiRole, healthAggBucketName)

        # Create layers in this stack since they may not exist yet
        s3_utils_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.S3_UTILS_LAYER_PATH, 
            config.S3_UTILS_LAYER_DESC, 
            config.S3_UTILS_LAYER_NAME_BASE + "-embeddings")
        
        json_utils_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.JSON_UTILS_LAYER_PATH, 
            config.JSON_UTILS_LAYER_DESC, 
            config.JSON_UTILS_LAYER_NAME_BASE + "-embeddings")      

        prompt_gen_cases_input_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.PROMPT_GEN_CASES_INPUT_LAYER_PATH, 
            config.PROMPT_GEN_CASES_INPUT_LAYER_DESC, 
            config.PROMPT_GEN_CASES_INPUT_LAYER_NAME_BASE + "-embeddings") 

        opensearch_utils_layer = BuildLambda.buildLambdaLayer(
            self, 
            makiRole, 
            config.OPENSEARCH_UTILS_LAYER_PATH, 
            config.OPENSEARCH_UTILS_LAYER_DESC, 
            config.OPENSEARCH_UTILS_LAYER_NAME_BASE + "-embeddings") 

        # Build the getHealthFromOpenSearch Lambda function (depends on OpenSearch)
        # Update the existing health lambda's environment variable with the actual endpoint
        from aws_cdk import custom_resources as cr
        
        # Create a specific role for updating Lambda configuration
        lambda_update_role = iam.Role(
            self, "MakiLambdaUpdateRole",
            role_name=utils.returnName("maki-lambda-update-role"),
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "MakiLambdaUpdatePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:UpdateFunctionConfiguration"],
                            resources=[f"arn:aws:lambda:{config.REGION}:{config.account_id}:function:{utils.returnName(config.GET_HEALTH_FROM_OPENSEARCH_NAME_BASE)}"]
                        ),
                        iam.PolicyStatement(
                            actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                            resources=[f"arn:aws:logs:{config.REGION}:{config.account_id}:log-group:/aws/lambda/*"]
                        )
                    ]
                )
            }
        )

        # Use a custom resource to update the Lambda function's environment variables
        lambda_update = cr.AwsCustomResource(
            self, "UpdateHealthLambdaEnvironment",
            on_update=cr.AwsSdkCall(
                service="Lambda",
                action="updateFunctionConfiguration",
                parameters={
                    "FunctionName": utils.returnName(config.GET_HEALTH_FROM_OPENSEARCH_NAME_BASE),
                    "Environment": {
                        "Variables": {
                            "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                            "OPENSEARCH_SKIP": config.OPENSEARCH_SKIP,
                            "OPENSEARCH_INDEX": config.OPENSEARCH_INDEX,
                            "HEALTH_EVENTS_SINCE": "FROM_SSM",  # Will be retrieved from SSM Parameter Store
                            "S3_HEALTH_AGG": utils.returnName(config.BUCKET_NAME_HEALTH_AGG_BASE),
                            "BEDROCK_CATEGORIZE_TEMPERATURE": str(config.BEDROCK_CATEGORIZE_TEMPERATURE),
                            "BEDROCK_MAX_TOKENS": str(config.BEDROCK_MAX_TOKENS),
                            "BEDROCK_CATEGORIZE_TOP_P": str(config.BEDROCK_CATEGORIZE_TOP_P),
                            "CATEGORY_BUCKET_NAME": utils.returnName(config.BUCKET_NAME_CATEGORY_BASE),
                            "CATEGORIES": str(config.CATEGORIES),
                            "CATEGORY_OUTPUT_FORMAT": str(config.CATEGORY_OUTPUT_FORMAT),
                            "BEDROCK_EMBEDDING_MODEL": config.BEDROCK_EMBEDDING_MODEL
                        }
                    }
                },
                physical_resource_id=cr.PhysicalResourceId.of("health-lambda-env-update")
            ),
            role=lambda_update_role
        )

        # Add dependency to ensure OpenSearch Serverless collection is created before Lambda update
        lambda_update.node.add_dependency(opensearch_collection)
