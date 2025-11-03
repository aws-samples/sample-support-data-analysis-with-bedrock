"""
MAKI CDK Stack Definitions

This module defines the three main CDK stacks that comprise the MAKI (Machine Augmented 
Key Insights) infrastructure. Each stack has a specific purpose and deployment order 
to ensure proper dependency management and resource organization.

Stack Architecture:
1. MakiFoundations: Core infrastructure and Lambda functions
2. MakiData: Reference data and category examples deployment
3. MakiEmbeddings: OpenSearch Serverless and health events infrastructure

Purpose:
- Organize MAKI infrastructure into logical deployment units
- Manage dependencies between different infrastructure components
- Enable selective deployment and updates of specific functionality
- Support both support cases and health events processing modes

Key Features:
- Modular stack design for flexible deployment
- Proper dependency management between stacks
- Resource sharing through CloudFormation exports
- Support for both development and production environments
- Comprehensive error handling and validation

Deployment Order:
1. Deploy MakiFoundations first (core infrastructure)
2. Deploy MakiData second (reference data)
3. Deploy MakiEmbeddings third (health events support)
"""

import sys
import json
import config
from constructs import Construct
sys.path.append('utils')    
import utils

from aws_cdk import (
    Stack,
    CfnOutput,
    Fn,
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_s3 as s3,
    aws_logs as logs,
    aws_cloudwatch as cw,
    aws_ec2 as ec2,
    custom_resources as cr,
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
    BuildS3Vector,
    BuildSSM
)

from constructs import Construct

class MakiFoundations(Stack):
    """
    MakiFoundations Stack - Core Infrastructure and Processing Components
    
    This is the primary MAKI stack that creates all foundational infrastructure
    required for MAKI operations, including networking, storage, compute, and
    orchestration components.
    
    Components Created:
    - IAM roles and policies for comprehensive service access
    - VPC with multi-AZ subnets and security groups
    - CloudWatch log groups for centralized logging
    - S3 buckets for all data storage needs
    - Lambda functions for all processing stages
    - Lambda layers for shared dependencies
    - Step Functions state machine for workflow orchestration
    - EventBridge rules for automated scheduling
    - SageMaker notebook for data analysis
    - SSM parameters for configuration management
    
    Key Features:
    - Support for both support cases and health events processing
    - Scalable architecture with on-demand and batch processing
    - Comprehensive security with least-privilege access
    - Cost optimization through lifecycle policies and resource sizing
    - Monitoring and logging for operational visibility
    
    Dependencies:
    - Must be deployed first before other MAKI stacks
    - Requires Bedrock model access to be enabled
    - Exports security group ID for use by other stacks
    
    Usage:
    - Deploy with: cdk deploy MakiFoundations
    - Provides core functionality for both processing modes
    - Creates all necessary infrastructure for MAKI operations
    """
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Build core infrastructure components
        # IAM role with comprehensive permissions for all MAKI operations
        makiRole = BuildIAM.buildMakiRole(self)

        # VPC with multi-AZ deployment for high availability and OpenSearch requirements
        vpc = BuildEC2.buildVPC(self, makiRole)
        sg = BuildEC2.buildSecurityGroup(self, vpc)  # Security group for SageMaker notebook
        log_group = BuildCloudWatch.buildCWLogGroup(self, vpc)  # Centralized logging

        # Create S3 buckets for all MAKI data storage needs
        # Category examples and reference data
        categoryBucketName = utils.returnName(config.BUCKET_NAME_CATEGORY_BASE)
        BuildS3.buildS3Bucket(self, makiRole, categoryBucketName)

        # Support cases aggregation and processing
        casesAggBucketName = utils.returnName(config.BUCKET_NAME_CASES_AGG_BASE)
        BuildS3.buildS3Bucket(self, makiRole, casesAggBucketName)

        # Health events aggregation (bucket name defined for consistency)
        healthAggBucketName = utils.returnName(config.BUCKET_NAME_HEALTH_AGG_BASE)

        # Bedrock batch inference job data
        batchesBucketName = utils.returnName(config.BUCKET_NAME_BATCHES)
        BuildS3.buildS3Bucket(self, makiRole, batchesBucketName)

        # Direct LLM outputs and intermediate results
        llmOutputBucketName = utils.returnName(config.BUCKET_NAME_LLM_BASE)
        BuildS3.buildS3Bucket(self, makiRole, llmOutputBucketName)

        # Final analysis reports and summaries
        reportBucketName = utils.returnName(config.BUCKET_NAME_REPORT_BASE)
        reportBucket = BuildS3.buildS3Bucket(self, makiRole, reportBucketName)

        # Long-term archive storage
        archiveBucketName = utils.returnName(config.BUCKET_NAME_ARCHIVE)
        BuildS3.buildS3Bucket(self, makiRole, archiveBucketName)

        # Build SSM Parameters for runtime configuration management
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

        prompt_agg_health_layer = BuildLambda.buildLambdaLayer(
            self,
            makiRole,
            config.PROMPT_AGG_HEALTH_LAYER_PATH,
            config.PROMPT_AGG_HEALTH_LAYER_DESC,
            config.PROMPT_AGG_HEALTH_LAYER_NAME_BASE
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
        
        # create the Bedrock batch inference job for health
        functions["health-" + config.BEDROCK_BATCH_INF_JOB_NAME_BASE] = BuildLambda.buildBedrockBatchInferenceJobHealth(
            self, 
            makiRole, 
            log_group, 
            s3_utils_layer,
            healthAggBucketName,
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
            prompt_agg_health_layer,
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
        
        # Export MAKI role for other stacks
        CfnOutput(self, "MakiRoleArn",
                 value=makiRole.role_arn,
                 export_name="MakiRoleArn")        

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

        # Create S3 Vector Bucket and Index
        vector_index = config.S3_VECTOR_INDEX_NAME
        s3vector_bucket, s3vector_index = BuildS3Vector.buildS3Vector(self, makiRole)

        # Update SSM parameter with actual OpenSearch endpoint
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

        # Create Lambda function to initialize health events data
        init_health_events_function = lambda_.Function(
            self, "InitHealthEventsFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="init_health_events.handler",
            code=lambda_.Code.from_asset("lambda/initHealthEvents"),
            timeout=Duration.minutes(15),
            memory_size=1024,
            role=makiRole,
            layers=[s3_utils_layer, json_utils_layer, opensearch_utils_layer],
            environment={
                "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                "INDEX_NAME": config.OPENSEARCH_INDEX,
                "REGION": config.REGION
            }
        )

        # Create custom resource to trigger the initialization
        init_health_events = cr.AwsCustomResource(
            self, "InitHealthEventsData",
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": init_health_events_function.function_name,
                    "Payload": json.dumps({
                        "RequestType": "Create"
                    })
                },
                physical_resource_id=cr.PhysicalResourceId.of("init-health-events")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[init_health_events_function.function_arn]
                )
            ])
        )

        # Add dependency to ensure collection is created first
        init_health_events.node.add_dependency(opensearch_collection)
        init_health_events.node.add_dependency(s3vector_bucket)


class MakiAgents(Stack):
    """
    MakiAgents Stack - FastMCP Agent Infrastructure
    
    This stack creates the infrastructure needed to run MAKI FastMCP agents
    that can query the OpenSearch instance created by MakiEmbeddings.
    
    Components Created:
    - FastMCP agent configuration
    - IAM roles for agent access to OpenSearch
    - Integration with existing MAKI infrastructure
    
    Key Features:
    - Semantic search using vector embeddings
    - Lexical search for exact term matching
    - Integration with Amazon Q CLI
    - Access to OpenSearch Serverless collection
    
    Dependencies:
    - Requires MakiFoundations stack (core infrastructure)
    - Requires MakiData stack (reference data)
    - Requires MakiEmbeddings stack (OpenSearch collection)
    
    Usage:
    - Deploy with: cdk deploy MakiAgents
    - Run agent with: python maki/BuildAgents.py
    """
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Import the MAKI role from MakiFoundations stack
        maki_role_arn = Fn.import_value("MakiRoleArn")
        maki_role = iam.Role.from_role_arn(
            self, "ImportedMakiRole",
            role_arn=maki_role_arn
        )

        # Add additional permissions for agent operations
        agent_policy = iam.Policy(
            self, utils.returnName("maki-agent-policy"),
            policy_name="maki-agent-policy",
            document=iam.PolicyDocument(
                statements=[
                    # OpenSearch Serverless permissions
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "aoss:APIAccessAll",
                            "aoss:DashboardsAccessAll"
                        ],
                        resources=[f"arn:aws:aoss:{self.region}:{self.account}:collection/{config.OPENSEARCH_COLLECTION_NAME}"]
                    ),
                    # Bedrock permissions for embeddings
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "bedrock:InvokeModel"
                        ],
                        resources=[
                            f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v1"
                        ]
                    ),
                    # SSM permissions for configuration
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "ssm:GetParameter",
                            "ssm:GetParameters"
                        ],
                        resources=[
                            f"arn:aws:ssm:{self.region}:{self.account}:parameter/maki-*"
                        ]
                    )
                ]
            )
        )

        # Attach the policy to the MAKI role
        maki_role.attach_inline_policy(agent_policy)

        # Output agent configuration
        CfnOutput(
            self, "AgentCommand",
            value="Configure mcp.json in Amazon Q CLI",
            description="MAKI agent is configured via mcp.json for Q CLI integration"
        )

        CfnOutput(
            self, "AgentDescription",
            value="MAKI FastMCP agent for semantic and lexical search of OpenSearch data",
            description="Description of the MAKI agent capabilities"
        )

