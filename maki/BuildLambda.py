# Builds S3 components of MAKI
import aws_cdk as cdk
import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_iam as iam
import config
import sys
sys.path.append('utils')
import utils

# checks to see if required models are enabled in Bedrock
def buildCheckEnabledModels(self, execution_role, log_group):

    state_machine_arn = 'arn:aws:states:' + config.REGION + ':' + config.account_id + ':stateMachine:' + utils.returnName(config.STATE_MACHINE_NAME_BASE)
    print("check for: " + state_machine_arn)

    lambdaCheckEnabledModels = _lambda.Function(
        self, utils.returnName(config.CHECK_ENABLED_MODELS_NAME_BASE),
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.CHECK_ENABLED_MODELS_PATH),
        function_name=utils.returnName(config.CHECK_ENABLED_MODELS_NAME_BASE),
        role=execution_role,
        timeout=cdk.Duration.seconds(config.CHECK_ENABLED_MODELS_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.CHECK_ENABLED_MODELS_MEMORY,
        description=config.CHECK_ENABLED_MODELS_DESC,
        handler=config.CHECK_ENABLED_MODELS_HANDLER_FILE + '.' + config.CHECK_ENABLED_MODELS_HANDLER_FUNC,
        retry_attempts=config.CHECK_ENABLED_MODELS_RETRIES,
        log_group=log_group,
        environment={
            "STATE_MACHINE_ARN": state_machine_arn,
            "BEDROCK_TEXT_MODEL": str(config.BEDROCK_TEXT_MODEL),
            "BEDROCK_TEXT_MODEL_AGG": str(config.BEDROCK_TEXT_MODEL_AGG)
        }
    )

    lambdaCheckEnabledModels.node.add_dependency(log_group) # add dependency
    lambdaCheckEnabledModels.node.add_dependency(execution_role) # add dependency

    return lambdaCheckEnabledModels

# checks for other batch inference jobs
def buildCheckBatchInferenceJobs(self, execution_role, log_group):

    lambdaCheckBatchInferenceJobs = _lambda.Function(
        self, utils.returnName(config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE),
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.CHECK_BATCH_INFERENCE_JOBS_PATH),
        function_name=utils.returnName(config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE),
        role=execution_role,
        timeout=cdk.Duration.seconds(config.CHECK_BATCH_INFERENCE_JOBS_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.CHECK_BATCH_INFERENCE_JOBS_MEMORY,
        description=config.CHECK_BATCH_INFERENCE_JOBS_DESC,
        handler=config.CHECK_BATCH_INFERENCE_JOBS_HANDLER_FILE + '.' + config.CHECK_BATCH_INFERENCE_JOBS_HANDLER_FUNC,
        retry_attempts=config.CHECK_BATCH_INFERENCE_JOBS_RETRIES,
        log_group=log_group,
    )

    lambdaCheckBatchInferenceJobs.node.add_dependency(log_group) # add dependency
    lambdaCheckBatchInferenceJobs.node.add_dependency(execution_role) # add dependency

    return lambdaCheckBatchInferenceJobs

# checks to see if any other maki state functions are already running
def buildCheckRunningJobs(self, execution_role, log_group):

    state_machine_arn = 'arn:aws:states:' + config.REGION + ':' + config.account_id + ':stateMachine:' + utils.returnName(config.STATE_MACHINE_NAME_BASE)
    print("check for: " + state_machine_arn)

    lambdaCheckRunningJobs = _lambda.Function(
        self, utils.returnName(config.CHECK_RUNNING_JOBS_NAME_BASE),
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.CHECK_RUNNING_JOBS_PATH),
        function_name=utils.returnName(config.CHECK_RUNNING_JOBS_NAME_BASE),
        role=execution_role,
        timeout=cdk.Duration.seconds(config.CHECK_RUNNING_JOBS_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.CHECK_RUNNING_JOBS_MEMORY,
        description=config.CHECK_RUNNING_JOBS_DESC,
        handler=config.CHECK_RUNNING_JOBS_HANDLER_FILE + '.' + config.CHECK_RUNNING_JOBS_HANDLER_FUNC,
        retry_attempts=config.CHECK_RUNNING_JOBS_RETRIES,
        log_group=log_group,
        environment={
            "STATE_MACHINE_ARN": state_machine_arn 
        }
    )

    lambdaCheckRunningJobs.node.add_dependency(log_group) # add dependency
    lambdaCheckRunningJobs.node.add_dependency(execution_role) # add dependency

    return lambdaCheckRunningJobs

# Lambda function to retrieve support cases from CID
def buildGetCasesFromCID(self, execution_role, log_group, prompt_gen_cases_input_layer, s3_utils_layer, json_utils_layer):

    categoryBucketName = config.KEY + '-' + config.BUCKET_NAME_CATEGORY_BASE
   

    environment={
        "CID_SKIP": config.CID_SKIP,
        "START_T": config.CASES_AFTER_TIME,
        "S3_CID": config.BUCKET_NAME_CID,
        "S3_AGG": config.KEY + '-' + config.BUCKET_NAME_CASES_AGG_BASE,
        "BEDROCK_CATEGORIZE_TEMPERATURE": str(config.BEDROCK_CATEGORIZE_TEMPERATURE),
        "BEDROCK_MAX_TOKENS": str(config.BEDROCK_MAX_TOKENS),
        "BEDROCK_CATEGORIZE_TOP_P": str(config.BEDROCK_CATEGORIZE_TOP_P),
        "CATEGORY_BUCKET_NAME": categoryBucketName,
        "CATEGORIES": str(config.CATEGORIES),
        "CATEGORY_OUTPUT_FORMAT": str(config.CATEGORY_OUTPUT_FORMAT)
    }

    func_name = utils.returnName(config.GET_CID_CASES_NAME_BASE) 

    lambdaGetCasesFromCID = _lambda.Function(
        self, func_name, 
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.GET_CID_CASES_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.GET_CID_CASES_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.GET_CID_CASES_MEMORY,
        description=config.GET_CID_CASES_DESC,
        handler=config.GET_CID_CASES_HANDLER_FILE + '.' + config.GET_CID_CASES_HANDLER_FUNC,
        retry_attempts=config.GET_CID_CASES_RETRIES,
        layers=[prompt_gen_cases_input_layer,s3_utils_layer,json_utils_layer],
        log_group=log_group,
        environment=environment
    )

    lambdaGetCasesFromCID.node.add_dependency(log_group) # add dependency

    return lambdaGetCasesFromCID

# builds a lambda layer
def buildLambdaLayer(self, execution_role, layer_path, layer_desc, layer_name):

    layer = _lambda.LayerVersion(
        self, layer_name,
        code=_lambda.Code.from_asset(layer_path),
        compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        compatible_architectures=[_lambda.Architecture.X86_64],
        description=layer_desc,
        layer_version_name=utils.returnName(layer_name)
    )

    layer.node.add_dependency(execution_role) # add dependency

    return layer

# use the above general layer function
# the layer functions should be generalized
def buildOpenSearchLayer(self, execution_role):

    layerOpenSearch = _lambda.LayerVersion(
        self, "layerOpenSearch",
        code=_lambda.Code.from_asset(config.OPENSEARCH_LAYER_PATH),
        compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        compatible_architectures=[_lambda.Architecture.X86_64],
        description=config.OPENSEARCH_LAYER_DESC,
        layer_version_name=utils.returnName(config.OPENSEARCH_LAYER_NAME_BASE)
    )

    layerOpenSearch.node.add_dependency(execution_role) # add dependency

    return layerOpenSearch

def buildRequestsLayer(self, execution_role):

    layerRequests = _lambda.LayerVersion(
        self, "layerRequests",
        code=_lambda.Code.from_asset(config.REQUESTS_LAYER_PATH),
        compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        compatible_architectures=[_lambda.Architecture.X86_64],
        description=config.REQUESTS_LAYER_DESC,
        layer_version_name=utils.returnName(config.REQUESTS_LAYER_NAME_BASE)
    )

    layerRequests.node.add_dependency(execution_role) # add dependency

    return layerRequests

# not used
def buildLangChainLayer(self, execution_role):

    # Lambda layer for LangChain
    layerLangChain = _lambda.LayerVersion(
        self, "layerLangChain",
        code=_lambda.Code.from_asset(config.LANGCHAIN_LAYER_PATH),
        compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        compatible_architectures=[_lambda.Architecture.X86_64],
        description=config.LANGCHAIN_LAYER_DESC,
        layer_version_name=utils.returnName(config.LANGCHAIN_LAYER_NAME_BASE)
    )

    layerLangChain.node.add_dependency(execution_role) # add dependency

    return layerLangChain

# not used
def buildChunkCases(self, execution_role, s3raw, log_group, langChainLayer, dopmainId):

    # Lambda function to chunk cases into s3
    func_name = utils.returnName(config.CHUNK_CASES_NAME_BASE)

    lambdaChunkCases = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.CHUNK_CASES_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.CHUNK_CASES_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.CHUNK_CASES_MEMORY,
        description=config.CHUNK_CASES_DESC,
        handler=config.CHUNK_CASES_HANDLER_FILE + '.' + config.CHUNK_CASES_HANDLER_FUNC,
        retry_attempts=config.CHUNK_CASES_RETRIES,
        log_group=log_group,
        layers=[langChainLayer], # add layer
        environment={
            "RAW_CASES": s3raw.bucket_name,
            "DOMAIN_ID": dopmainId
        }
    )

    lambdaChunkCases.node.add_dependency(s3raw) # add dependency
    lambdaChunkCases.node.add_dependency(log_group) # add dependency
    lambdaChunkCases.node.add_dependency(langChainLayer) # add dependency

    return lambdaChunkCases

# not used
def buildIndex(self, execution_role, log_group, requestsLayer, opensearchLayer, domain_endpoint):
    # cdk isn't mature to create an index for opensearch, so do in lambda

    func_name = utils.returnName(config.INDEX_NAME_BASE)

    lambdaIndex = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.INDEX_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.INDEX_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.INDEX_MEMORY,
        description=config.INDEX_DESC,
        handler=config.INDEX_HANDLER_FILE + '.' + config.INDEX_HANDLER_FUNC,
        retry_attempts=config.INDEX_RETRIES,
        log_group=log_group,
        layers=[requestsLayer,opensearchLayer],
        environment={
            "REGION": config.REGION,
            "BEDROCK_EMBEDDING_MODEL": config.BEDROCK_EMBEDDING_MODEL,
            "DOMAIN_ENDPOINT": domain_endpoint,
            "INDEX_NAME": config.OPENSEARCH_CASE_INDEX_NAME
        }
    )

    lambdaIndex.node.add_dependency(log_group) # add dependency
    lambdaIndex.node.add_dependency(requestsLayer) # add dependency
    lambdaIndex.node.add_dependency(execution_role) # add dependency
    
    return lambdaIndex 

# not used
def buildStoreCases(self, execution_role, s3raw, log_group, openSearchLayer, domain_id, domain_endpoint):

    # Lambda function to chunk cases into s3
    func_name = utils.returnName(config.STORE_CASES_NAME_BASE)

    lambdaChunkCases = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.STORE_CASES_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.STORE_CASES_TIMEOUT),
        memory_size=config.STORE_CASES_MEMORY,
        description=config.STORE_CASES_DESC,
        handler=config.STORE_CASES_HANDLER_FILE + '.' + config.STORE_CASES_HANDLER_FUNC,
        retry_attempts=config.STORE_CASES_RETRIES,
        log_group=log_group,
        layers=[openSearchLayer],   
        environment={
            "RAW_CASES": s3raw.bucket_name,
            "REGION": config.REGION,
            "BEDROCK_EMBEDDING_MODEL": config.BEDROCK_EMBEDDING_MODEL,
            "DOMAIN_ID": domain_id,
            "DOMAIN_ENDPOINT": domain_endpoint
        }
    )

    lambdaChunkCases.node.add_dependency(s3raw) # add dependency
    lambdaChunkCases.node.add_dependency(log_group) # add dependency
    lambdaChunkCases.node.add_dependency(openSearchLayer) # add dependency

    return lambdaChunkCases

def genBatchInferenceRecords(self, execution_role, s3_utils_layer, json_utils_layer, prompt_agg_layer):
    func_name = utils.returnName(config.GEN_BATCH_INF_RECORDS_NAME_BASE)
    lambdaGenBatchInferenceRecords = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.GEN_BATCH_INF_RECORDS_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.GEN_BATCH_INF_RECORDS_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.GEN_BATCH_INF_RECORDS_MEMORY,
        description=config.GEN_BATCH_INF_RECORDS_DESC,
        handler=config.GEN_BATCH_INF_RECORDS_HANDLER_FILE + '.' + config.GEN_BATCH_INF_RECORDS_HANDLER_FUNC,
        retry_attempts=config.GEN_BATCH_INF_RECORDS_RETRIES,
        layers=[s3_utils_layer, json_utils_layer, prompt_agg_layer],
        environment={
            "BEDROCK_TEXT_MODEL": config.BEDROCK_TEXT_MODEL,
            "BEDROCK_SUMMARY_TEMPERATURE": str(config.BEDROCK_SUMMARY_TEMPERATURE),
            "BEDROCK_MAX_TOKENS": str(config.BEDROCK_MAX_TOKENS),
            "BEDROCK_CATEGORIZE_TEMPERATURE": str(config.BEDROCK_CATEGORIZE_TEMPERATURE),
            "BEDROCK_CATEGORIZE_TOP_P": str(config.BEDROCK_CATEGORIZE_TOP_P),
        }
    )

    return lambdaGenBatchInferenceRecords

def buildOnDemandInference(self, execution_role, log_group, s3_utils_layer, json_utils_layer, prompt_agg_layer, s3_in, s3_out):
    func_name = utils.returnName(config.BEDROCK_ONDEMAND_INF_NAME_BASE)
    categoryBucketName = config.KEY + '-' + config.BUCKET_NAME_CATEGORY_BASE
    

    lambdaBedrockOnDemandInference = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.BEDROCK_ONDEMAND_INF_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.BEDROCK_ONDEMAND_INF_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.BEDROCK_ONDEMAND_INF_MEMORY,
        description=config.BEDROCK_ONDEMAND_INF_DESC,
        handler=config.BEDROCK_ONDEMAND_INF_HANDLER_FILE + '.' + config.BEDROCK_ONDEMAND_INF_HANDLER_FUNC,
        retry_attempts=config.BEDROCK_ONDEMAND_INF_RETRIES,
        log_group=log_group,
        layers=[s3_utils_layer, json_utils_layer, prompt_agg_layer],
        environment={
            "S3_INPUT" : s3_in,
            "S3_OUTPUT" : s3_out,
            "BEDROCK_TEXT_MODEL": config.BEDROCK_TEXT_MODEL,
            "BEDROCK_SUMMARY_TEMPERATURE": str(config.BEDROCK_SUMMARY_TEMPERATURE),
            "BEDROCK_CATEGORIZE_TEMPERATURE": str(config.BEDROCK_CATEGORIZE_TEMPERATURE),
            "CATEGORY_BUCKET_NAME": categoryBucketName,
            "CATEGORIES": str(config.CATEGORIES),
            "CATEGORY_OUTPUT_FORMAT": str(config.CATEGORY_OUTPUT_FORMAT),
            "THROTTLE": str(config.BEDROCK_THROTTLE_DELAY_SECONDS),
            
        }
    )

    return lambdaBedrockOnDemandInference    

# create a bedrock batch inference job
def buildBedrockBatchInferenceJob(self, execution_role, log_group, s3_utils_layer, s3_input, s3_batches, s3_output):
    func_name = utils.returnName(config.BEDROCK_BATCH_INF_JOB_NAME_BASE)

    s3_input = f"s3://{s3_input}/"
    s3_batches = f"s3://{s3_batches}/"
    s3_output = f"s3://{s3_output}/"

    name = utils.returnName(config.BEDROCK_BATCH_INF_JOB_NAME_BASE)

    lambdaBatchInfJob = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.BEDROCK_BATCH_INF_JOB_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.BEDROCK_BATCH_INF_JOB_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.BEDROCK_BATCH_INF_JOB_MEMORY,
        description=config.BEDROCK_BATCH_INF_JOB_DESC,
        handler=config.BEDROCK_BATCH_INF_JOB_HANDLER_FILE + '.' + config.BEDROCK_BATCH_INF_JOB_HANDLER_FUNC,
        retry_attempts=config.BEDROCK_BATCH_INF_JOB_RETRIES,
        log_group=log_group,
        layers=[s3_utils_layer],
        environment={
            "S3_INPUT" : s3_input,
            "S3_BATCHES" : s3_batches,
            "S3_OUTPUT" : s3_output,
            "MODEL_ID" : config.BEDROCK_TEXT_MODEL,
            "NAME" : name,
            "ROLE": execution_role.role_arn,
            "BEDROCK_ONDEMAND_BATCH_INFLECTION": str(config.BEDROCK_ONDEMAND_BATCH_INFLECTION),
        }
    )

    lambdaBatchInfJob.node.add_dependency(log_group) # add dependency
    lambdaBatchInfJob.node.add_dependency(execution_role) # add dependency
    
    return lambdaBatchInfJob 

# create a bedrock process batch output job
def buildBedrockProcessBatchOutput(
        self, 
        execution_role, 
        log_group, 
        s3_utils_layer, 
        json_utils_layer, 
        prompt_agg_layer, 
        s3_batch_output,
        s3_report,
        s3_archive,
        s3_batches):
    
    s3_batches = f"s3://{s3_batches}/"

    func_name = utils.returnName(config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE) 

    environment={
        "S3_BATCH_OUTPUT" : s3_batch_output,
        "S3_REPORT" : s3_report,
        "S3_ARCHIVE": s3_archive,
        "S3_BATCHES" : s3_batches,
        "MODEL_ID" : config.BEDROCK_TEXT_MODEL_AGG,
        "BEDROCK_SUMMARY_TEMPERATURE" : str(config.BEDROCK_SUMMARY_TEMPERATURE),
        "BEDROCK_MAX_TOKENS" : str(config.BEDROCK_MAX_TOKENS_AGG),
        "KEY" : config.KEY,
        "SUMMARY_OUTPUT_FORMAT": str(config.SUMMARY_OUTPUT_FORMAT), 
    }

    lambdaProcessBatchOutput = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.BEDROCK_PROCESS_BATCH_OUTPUT_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.BEDROCK_PROCESS_BATCH_OUTPUT_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.BEDROCK_PROCESS_BATCH_OUTPUT_MEMORY,
        description=config.BEDROCK_PROCESS_BATCH_OUTPUT_DESC,
        handler=config.BEDROCK_PROCESS_BATCH_OUTPUT_HANDLER_FILE + '.' + config.BEDROCK_PROCESS_BATCH_OUTPUT_HANDLER_FUNC,
        retry_attempts=config.BEDROCK_PROCESS_BATCH_OUTPUT_RETRIES,
        log_group=log_group,
        layers=[s3_utils_layer, json_utils_layer, prompt_agg_layer],
        environment=environment
    )       

    lambdaProcessBatchOutput.node.add_dependency(log_group) # add dependency
    lambdaProcessBatchOutput.node.add_dependency(execution_role) # add dependency

    return lambdaProcessBatchOutput

def buildBedrockProcessOnDemandOputput(
        self,
        execution_role,
        log_group,
        s3_utils_layer,
        json_utils_layer,
        prompt_agg_layer,
        s3_report):

    func_name = utils.returnName(config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_NAME_BASE)

    lambdaProcessOnDemandOutput = _lambda.Function(
        self, func_name,
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_MEMORY,
        description=config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_DESC,
        handler=config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_HANDLER_FILE + '.' + config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_HANDLER_FUNC,
        retry_attempts=config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_RETRIES,
        log_group=log_group,
        layers=[s3_utils_layer, json_utils_layer, prompt_agg_layer],
        environment={
            "S3_AGG_OUTPUT": s3_report,
            "MODEL_ID" : str(config.BEDROCK_TEXT_MODEL_AGG),
            "BEDROCK_SUMMARY_TEMPERATURE" : str(config.BEDROCK_SUMMARY_TEMPERATURE),
            "BEDROCK_MAX_TOKENS" : str(config.BEDROCK_MAX_TOKENS_AGG),
            "KEY" : config.KEY,
            "SUMMARY_OUTPUT_FORMAT": str(config.SUMMARY_OUTPUT_FORMAT),
        }
    )

    lambdaProcessOnDemandOutput.node.add_dependency(log_group) # add dependency
    lambdaProcessOnDemandOutput.node.add_dependency(execution_role) # add dependency

    return lambdaProcessOnDemandOutput

def buildCleanOutputFiles(
        self,
        makiRole,
        log_group,
        s3_utils_layer,
        reportBucketName):

    func_name = utils.returnName(config.CLEAN_OUTPUT_FILES_NAME_BASE)
    lambdaCleanOutputFile = _lambda.Function(
            self, func_name,
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset(config.CLEAN_OUTPUT_FILES_PATH),
            function_name=func_name,
            role=makiRole,
            timeout=cdk.Duration.seconds(config.CLEAN_OUTPUT_FILES_TIMEOUT),
            architecture=_lambda.Architecture.X86_64,
            memory_size=config.CLEAN_OUTPUT_FILES_MEMORY,
            description=config.CLEAN_OUTPUT_FILES_DESC,
            handler=config.CLEAN_OUTPUT_FILES_HANDLER_FILE + '.' + config.CLEAN_OUTPUT_FILES_HANDLER_FUNC,
            retry_attempts=config.CLEAN_OUTPUT_FILES_RETRIES,
            layers=[s3_utils_layer],
            log_group=log_group,
            environment={
                "S3_OUTPUT" : reportBucketName,
            }
        )

    return lambdaCleanOutputFile

# Lambda function to retrieve health events from OpenSearch
def buildGetHealthFromOpenSearch(self, execution_role, log_group, prompt_gen_cases_input_layer, s3_utils_layer, json_utils_layer, opensearch_utils_layer, opensearch_endpoint):

    categoryBucketName = config.KEY + '-' + config.BUCKET_NAME_CATEGORY_BASE
    healthAggBucketName = config.KEY + '-' + config.BUCKET_NAME_HEALTH_AGG_BASE

    environment={
        "OPENSEARCH_SKIP": config.OPENSEARCH_SKIP,
        "OPENSEARCH_ENDPOINT": opensearch_endpoint,
        "OPENSEARCH_INDEX": config.OPENSEARCH_INDEX,
        "HEALTH_EVENTS_SINCE": config.HEALTH_EVENTS_SINCE,
        "S3_HEALTH_AGG": healthAggBucketName,
        "BEDROCK_CATEGORIZE_TEMPERATURE": str(config.BEDROCK_CATEGORIZE_TEMPERATURE),
        "BEDROCK_MAX_TOKENS": str(config.BEDROCK_MAX_TOKENS),
        "BEDROCK_CATEGORIZE_TOP_P": str(config.BEDROCK_CATEGORIZE_TOP_P),
        "CATEGORY_BUCKET_NAME": categoryBucketName,
        "CATEGORIES": str(config.CATEGORIES),
        "CATEGORY_OUTPUT_FORMAT": str(config.CATEGORY_OUTPUT_FORMAT),
        "BEDROCK_EMBEDDING_MODEL": config.BEDROCK_EMBEDDING_MODEL
    }

    func_name = utils.returnName(config.GET_HEALTH_FROM_OPENSEARCH_NAME_BASE) 

    lambdaGetHealthFromOpenSearch = _lambda.Function(
        self, func_name, 
        runtime=_lambda.Runtime.PYTHON_3_12,
        code=_lambda.Code.from_asset(config.GET_HEALTH_FROM_OPENSEARCH_PATH),
        function_name=func_name,
        role=execution_role,
        timeout=cdk.Duration.seconds(config.GET_HEALTH_FROM_OPENSEARCH_TIMEOUT),
        architecture=_lambda.Architecture.X86_64,
        memory_size=config.GET_HEALTH_FROM_OPENSEARCH_MEMORY,
        description=config.GET_HEALTH_FROM_OPENSEARCH_DESC,
        handler=config.GET_HEALTH_FROM_OPENSEARCH_HANDLER_FILE + '.' + config.GET_HEALTH_FROM_OPENSEARCH_HANDLER_FUNC,
        retry_attempts=config.GET_HEALTH_FROM_OPENSEARCH_RETRIES,
        layers=[prompt_gen_cases_input_layer,s3_utils_layer,json_utils_layer,opensearch_utils_layer],
        log_group=log_group,
        environment=environment
    )

    lambdaGetHealthFromOpenSearch.node.add_dependency(log_group)

    return lambdaGetHealthFromOpenSearch