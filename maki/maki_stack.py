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

        healthAggBucketName = utils.returnName(config.BUCKET_NAME_HEALTH_AGG_BASE)

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

        prompt_gen_input_layer = BuildLambda.buildLambdaLayer(
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
            prompt_gen_input_layer, 
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
            prompt_gen_input_layer, 
            casesAggBucketName,
            reportBucketName
        )

        functions[config.BEDROCK_HEALTH_ONDEMAND_INF_NAME_BASE] = BuildLambda.buildHealthOnDemandInference(
            self,
            makiRole,
            log_group,
            s3_utils_layer,
            json_utils_layer,
            prompt_gen_input_layer, 
            healthAggBucketName,
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
        functions[config.BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_NAME_BASE] = BuildLambda.buildBedrockProcessOnDemandOputput(
            self,
            makiRole,
            log_group,
            s3_utils_layer,
            json_utils_layer,
            prompt_agg_cases_layer,
            reportBucketName
        )

        functions[config.BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_NAME_BASE] = BuildLambda.buildBedrockProcessHealthOnDemandOutput(
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
            prompt_gen_input_layer, 
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

        # Update SSM parameter with actual OpenSearch endpoint
        from aws_cdk import custom_resources as cr
        ssm_update = cr.AwsCustomResource(
            self, "UpdateOpenSearchEndpointSSM",
            on_create=cr.AwsSdkCall(
                service="SSM",
                action="putParameter",
                parameters={
                    "Name": utils.returnName("opensearch-endpoint"),
                    "Value": opensearch_endpoint,
                    "Type": "String",
                    "Overwrite": True
                },
                physical_resource_id=cr.PhysicalResourceId.of("opensearch-endpoint-update")
            ),
            on_update=cr.AwsSdkCall(
                service="SSM",
                action="putParameter",
                parameters={
                    "Name": utils.returnName("opensearch-endpoint"),
                    "Value": opensearch_endpoint,
                    "Type": "String",
                    "Overwrite": True
                },
                physical_resource_id=cr.PhysicalResourceId.of("opensearch-endpoint-update")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["ssm:PutParameter"],
                    resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/{utils.returnName('opensearch-endpoint')}"]
                )
            ])
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

        prompt_gen_input_layer = BuildLambda.buildLambdaLayer(
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

        # Create health aggregation S3 bucket
        healthAggBucketName = utils.returnName(config.BUCKET_NAME_HEALTH_AGG_BASE)

