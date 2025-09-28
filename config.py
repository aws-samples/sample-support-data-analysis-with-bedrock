# builds unique key for build
import boto3

####
# Helper function to get SSM parameters
def get_ssm_parameter(parameter_name):
    """Get parameter value from SSM Parameter Store"""
    import boto3
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-{parameter_name}")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting {parameter_name} from SSM: {e}")
        return '2023-01-01T00:00:00Z'  # default fallback

###
# Support Case Categories
# need to add more categories
CATEGORIES = [
    'limit-reached', 
    'customer-release',
    'development-issue',
    'customer-networking',
    'throttling',
    'ice-error',
    'feature-request',
    'customer-dependency',
    'aws-release',
    'customer-question',
    'exceeding-capability',
    'lack-monitoring',
    'security-issue',
    'service-event',
    'transient-issues',
    'upgrade-management'
]
# where example category files are stored, relative to base
CATEGORY_DIR =  'categories'

###
# Default mode when not specified in input
DEFAULT_MODE = 'health'

###
# General
def get_region():
    try:
        ec2 = boto3.client('ec2')
        return ec2.meta.region_name
    except:
        return 'us-east-1'  # fallback

REGION = get_region()

#####
# Tags 
PROJ = 'maki'
AUTODELETE = 'no'

#####
# Unique Key

sts_client = boto3.client("sts")
account_id = sts_client.get_caller_identity()["Account"]
KEY = PROJ + '-' + account_id + '-' + REGION

###
# Bedrock
# must use cross region inference profiles
# must support prompt caching
BEDROCK_TEXT_MODEL = "us.amazon.nova-micro-v1:0"
BEDROCK_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
BEDROCK_THROTTLE_DELAY_SECONDS = 3
BEDROCK_MAX_TOKENS = 10240
BEDROCK_CATEGORIZE_TEMPERATURE = 0.5
BEDROCK_CATEGORIZE_TOP_P = 0.1
BEDROCK_SUMMARY_TEMPERATURE = 0.3
BEDROCK_SUMMARY_TOP_P = 0.5
BEDROCK_ONDEMAND_BATCH_INFLECTION = 100

BEDROCK_TEXT_MODEL_AGG = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
BEDROCK_MAX_TOKENS_AGG = 131072 

###
# Synthetic case generation
SYNTH_CASES_MAX_TOKENS = 10240
SYNTH_CASES_NUMBER_SEED = 2 
SYNTH_CASES_TEMPERATURE = 0.3
SYNTH_CASES_CATEGORIZE_TOP_P = 0.1

# Proper LLM output format in JSON
# this is in in str format as it needs to feed into the Bedrock prompt as a str
CASES_CATEGORY_OUTPUT_FORMAT = "{ \
 \"caseId\": caseId, \
 \"displayId\": DisplayId, \
 \"status\": status, \
 \"serviceCode\": serviceCode, \
 \"timeCreated\": timeCreated, \
 \"timeResolved\" timeResolved, \
 \"submittedBY\": submittedBy, \
 \"category\": Category, \
 \"category_explanation\": Category_Explanation, \
 \"case_summary\": Case_Summary, \
 \"sentiment\": Sentiment, \
 \"suggested_action\": Suggested_Action \
 \"suggestion_link\": Suggestion_Link\
}"

HEALTH_OUTPUT_FORMAT = "{ \
\"arn\": \"arn\", \
\"service\": \"service\", \
\"eventTypeCode\": \"eventTypeCode\", \
\"eventTypeCategory\": \"eventTypeCategory\", \
\"region\": \"region\", \
\"startTime\": \"startTime\", \
\"lastUpdatedTime\": \"lastUpdatedTime\", \
\"statusCode\": \"statusCode\", \
\"eventScopeCode\": \"eventScopeCode\", \
\"latestDescription\": \"latestDescription\", \
\"event_summary\": \"event_summary\", \
\"suggestion_action\": \"suggestion_action\", \
\"suggestion_link\": \"suggestion_link\" \
}"

SUMMARY_OUTPUT_FORMAT = "{ \
 \"summary\": Summary, \
 \"plan\": Plan \
}"

###
# State Machine
STATE_MACHINE_NAME_BASE = 'state-machine' 
STATE_MACHINE_TIMEOUT = 3600 #seconds
CRON_MAIN_JOB_NAME_BASE = 'cron-job-main'
CRON_MAIN_MINUTE = '0'
CRON_MAIN_HOUR = '6'
CRON_MAIN_DAY = '*'
CRON_MAIN_MONTH = '*'
CRON_MAIN_YEAR = '*'
BEDROCK_BATCH_INF_WAIT_BASE = 'batch-inference-wait'
BEDROCK_BATCH_RULE_BASE = 'bedrock-batch-completion-rule'
EVENT_ITERATOR_MAX_PARALLEL = 1

POST_BATCH_CHECK_INTERVAL_MIN = 1

# report cron
CRON_REPORT_JOB_NAME_BASE = 'cron-job-report'
CRON_REPORT_MINUTE = '*/5'
CRON_REPORT_HOUR = '*'
CRON_REPORT_DAY = '*'
CRON_REPORT_MONTH = '*'
CRON_REPORT_YEAR = '*'

# CloudWatch
LOG_GROUP_NAME_BASE = 'log-group'

# S3 bucket lifecycle to S3-int
LCDAYS = 90 
LCDAYS_POLICY = 'LC_TO_INT'
BUCKET_CASES = 'cases'

BUCKET_NAME_BATCHES = 'batches'
BUCKET_NAME_CATEGORY_BASE = 'examples'
BUCKET_NAME_LLM_BASE = 'llm-output'
BUCKET_NAME_ARCHIVE = 'archive'

BUCKET_NAME_REPORT_BASE = 'report'

# where CID retrieves the cases
BUCKET_NAME_CID = 'cid-data-' + account_id

# set this to true, to not look for files in CUR directories
CID_SKIP = 'true' 

BUCKET_NAME_CASES_AGG_BASE = 'cases-agg'
BUCKET_NAME_HEALTH_AGG_BASE = 'health-agg'

###
# OpenSearch Serverless Health Events
OPENSEARCH_COLLECTION_NAME = 'maki-health'
OPENSEARCH_INDEX = 'aws-health-events'

####
# IAM
EXEC_ROLE = 'maki-exec-role'

###
BEDROCK_INF_METHOD_ROUTER_NAME_BASE = 'inference-method-router'

####
# Lambda configs to check for batch inference jobs
CHECK_BATCH_INFERENCE_JOBS_NAME_BASE = 'check-batch-inference-jobs'
CHECK_BATCH_INFERENCE_JOBS_TIMEOUT = 900
CHECK_BATCH_INFERENCE_JOBS_MEMORY = 128
CHECK_BATCH_INFERENCE_JOBS_DESC = 'check batch inference jobs'
CHECK_BATCH_INFERENCE_JOBS_PATH = 'lambda/checkBatchInferenceJobs'
CHECK_BATCH_INFERENCE_JOBS_HANDLER_FILE = 'checkBatchInferenceJobs_handler'
CHECK_BATCH_INFERENCE_JOBS_HANDLER_FUNC = 'handler'
CHECK_BATCH_INFERENCE_JOBS_RETRIES = 0

# Lambda configs to check for running jobs
CHECK_ENABLED_MODELS_NAME_BASE = 'check-enabled_models'
CHECK_ENABLED_MODELS_TIMEOUT = 900
CHECK_ENABLED_MODELS_MEMORY = 128
CHECK_ENABLED_MODELS_DESC = 'check enabled models'
CHECK_ENABLED_MODELS_PATH = 'lambda/checkEnabledModels'
CHECK_ENABLED_MODELS_HANDLER_FILE = 'checkEnabledModels_handler'
CHECK_ENABLED_MODELS_HANDLER_FUNC = 'handler'
CHECK_ENABLED_MODELS_RETRIES = 0

# Lambda configs to check for running jobs
CHECK_RUNNING_JOBS_NAME_BASE = 'check-running-jobs'
CHECK_RUNNING_JOBS_TIMEOUT = 900
CHECK_RUNNING_JOBS_MEMORY = 128
CHECK_RUNNING_JOBS_DESC = 'check running jobs'
CHECK_RUNNING_JOBS_PATH = 'lambda/checkRunningJobs'
CHECK_RUNNING_JOBS_HANDLER_FILE = 'checkRunningJobs_handler'
CHECK_RUNNING_JOBS_HANDLER_FUNC = 'handler'
CHECK_RUNNING_JOBS_RETRIES = 0


# Lambda configs for getting cases from CID
GET_CID_CASES_NAME_BASE = 'GetCasesFromCID'
GET_CID_CASES_TIMEOUT = 900
GET_CID_CASES_MEMORY = 10240
GET_CID_CASES_DESC = 'get cases from the CID'
GET_CID_CASES_PATH = 'lambda/getCasesFromCID'
GET_CID_CASES_HANDLER_FILE = 'getCasesFromCID_handler'
GET_CID_CASES_HANDLER_FUNC = 'handler'
GET_CID_CASES_RETRIES = 0

# Lambda configs for getting health events from OpenSearch
GET_HEALTH_FROM_OPENSEARCH_NAME_BASE = 'GetHealthFromOpenSearch'
GET_HEALTH_FROM_OPENSEARCH_TIMEOUT = 900
GET_HEALTH_FROM_OPENSEARCH_MEMORY = 10240
GET_HEALTH_FROM_OPENSEARCH_DESC = 'get health events from OpenSearch'
GET_HEALTH_FROM_OPENSEARCH_PATH = 'lambda/getHealthFromOpenSearch'
GET_HEALTH_FROM_OPENSEARCH_HANDLER_FILE = 'getHealthFromOpenSearch_handler'
GET_HEALTH_FROM_OPENSEARCH_HANDLER_FUNC = 'handler'
GET_HEALTH_FROM_OPENSEARCH_RETRIES = 0

# Lambda configs for using Bedrock ondemand inference
BEDROCK_ONDEMAND_INF_NAME_BASE = 'cases-ondemand-inference'
BEDROCK_ONDEMAND_INF_TIMEOUT = 900
BEDROCK_ONDEMAND_INF_MEMORY = 10240
BEDROCK_ONDEMAND_INF_DESC = 'ondemand inference'
BEDROCK_ONDEMAND_INF_PATH = 'lambda/bedrockOnDemandInference'
BEDROCK_ONDEMAND_INF_HANDLER_FILE = 'bedrockOnDemandInference_handler'
BEDROCK_ONDEMAND_INF_HANDLER_FUNC = 'handler'
BEDROCK_ONDEMAND_INF_RETRIES = 0

BEDROCK_HEALTH_ONDEMAND_INF_NAME_BASE = 'health-ondemand-inference'
BEDROCK_HEALTH_ONDEMAND_INF_TIMEOUT = 900
BEDROCK_HEALTH_ONDEMAND_INF_MEMORY = 10240
BEDROCK_HEALTH_ONDEMAND_INF_DESC = 'health ondemand inference'
BEDROCK_HEALTH_ONDEMAND_INF_PATH = 'lambda/bedrockOnDemandInference'
BEDROCK_HEALTH_ONDEMAND_INF_HANDLER_FILE = 'bedrockOnDemandInferenceHealth_handler'
BEDROCK_HEALTH_ONDEMAND_INF_HANDLER_FUNC = 'handler'
BEDROCK_HEALTH_ONDEMAND_INF_RETRIES = 0

# Lambda to create batch inf records
GEN_BATCH_INF_RECORDS_NAME_BASE = 'gen-batch-inference-records'
GEN_BATCH_INF_RECORDS_TIMEOUT = 900
GEN_BATCH_INF_RECORDS_MEMORY = 10240
GEN_BATCH_INF_RECORDS_DESC = 'generate batch inference records'
GEN_BATCH_INF_RECORDS_PATH = 'lambda/genBatchInferenceRecords'
GEN_BATCH_INF_RECORDS_HANDLER_FILE = 'genBatchInferenceRecords_handler'
GEN_BATCH_INF_RECORDS_HANDLER_FUNC = 'handler'
GEN_BATCH_INF_RECORDS_RETRIES = 0

# Lambda configs to clean output files
CLEAN_OUTPUT_FILES_NAME_BASE = 'clean-output-files'
CLEAN_OUTPUT_FILES_TIMEOUT = 900
CLEAN_OUTPUT_FILES_MEMORY = 128
CLEAN_OUTPUT_FILES_DESC = 'clean output files'
CLEAN_OUTPUT_FILES_PATH = 'lambda/cleanOutputFiles'
CLEAN_OUTPUT_FILES_HANDLER_FILE = 'cleanOutputFiles_handler'
CLEAN_OUTPUT_FILES_HANDLER_FUNC = 'handler'
CLEAN_OUTPUT_FILES_RETRIES = 0

# Lambda configs for creating Bedrock batch inference job
BEDROCK_BATCH_INF_JOB_NAME_BASE = 'batch-inference'
BEDROCK_BATCH_INF_JOB_TIMEOUT = 900
BEDROCK_BATCH_INF_JOB_MEMORY = 10240
BEDROCK_BATCH_INF_JOB_DESC = 'create Bedrock batch inference job'
BEDROCK_BATCH_INF_JOB_PATH = 'lambda/bedrockBatchInferenceJob'
BEDROCK_BATCH_INF_JOB_HANDLER_FILE = 'bedrockBatchInferenceJob_handler'
BEDROCK_BATCH_INF_JOB_HANDLER_FUNC = 'handler'
BEDROCK_BATCH_INF_JOB_RETRIES = 0

# Lambda configs for creating Bedrock process output job 
BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE = 'process-batch-output'
BEDROCK_PROCESS_BATCH_OUTPUT_TIMEOUT = 900
BEDROCK_PROCESS_BATCH_OUTPUT_MEMORY = 10240
BEDROCK_PROCESS_BATCH_OUTPUT_DESC = 'process Bedrock batch inference output'
BEDROCK_PROCESS_BATCH_OUTPUT_PATH = 'lambda/bedrockProcessBatchOutput'
BEDROCK_PROCESS_BATCH_OUTPUT_HANDLER_FILE = 'bedrockProcessBatchOutput_handler'
BEDROCK_PROCESS_BATCH_OUTPUT_HANDLER_FUNC = 'handler'
BEDROCK_PROCESS_BATCH_OUTPUT_RETRIES = 0

# Lambda to process ondemand inference output
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_NAME_BASE = 'cases-process-ondemand'
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_TIMEOUT = 900
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_MEMORY = 10240
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_DESC = 'process ondemand inference output'
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_PATH = 'lambda/bedrockProcessOnDemandOutput'
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_HANDLER_FILE = 'bedrockProcessOnDemandOutput_handler'
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_HANDLER_FUNC = 'handler'
BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_RETRIES = 0

BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_NAME_BASE = 'health-process-ondemand'
BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_TIMEOUT = 900
BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_MEMORY = 10240
BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_DESC = 'process health ondemand inference output'
BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_PATH = 'lambda/bedrockProcessOnDemandOutput'
BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_HANDLER_FILE = 'bedrockProcessOnDemandOutput_handler'
BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_HANDLER_FUNC = 'handler'
BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_RETRIES = 0

# this Lambda layer is used to store prompts that generate Bedrock batch inference records from CID and synthetic records
PROMPT_GEN_CASES_INPUT_LAYER_PATH = 'lambda/layers/prompt_gen_input'
PROMPT_GEN_CASES_INPUT_LAYER_NAME_BASE = 'MakiPromptGenCasesInput'
PROMPT_GEN_CASES_INPUT_LAYER_DESC = 'MAKI Prompt Cases Input Layer'

# this lambda layer is used to process and aggregate the output from Bedrock batch inference
PROMPT_AGG_CASES_LAYER_PATH = 'lambda/layers/prompt_agg_cases'
PROMPT_AGG_CASES_LAYER_NAME_BASE = 'MakiPromptAggCases'
PROMPT_AGG_CASES_LAYER_DESC = 'MAKI Prompt Aggregate Cases Layer'

PROMPT_AGG_HEALTH_LAYER_PATH = 'lambda/layers/prompt_agg_health'
PROMPT_AGG_HEALTH_LAYER_NAME_BASE = 'MakiPromptAggHealth'
PROMPT_AGG_HEALTH_LAYER_DESC = 'MAKI Prompt Aggregate Health Layer'

# this Lambda layer is used for various S3 functions
S3_UTILS_LAYER_PATH = 'lambda/layers/s3_utils'
S3_UTILS_LAYER_NAME_BASE = 'MakiS3Utils'
S3_UTILS_LAYER_DESC = 'MAKI S3 Utils Layer'

# this Lambda layer is used for various json methods
JSON_UTILS_LAYER_PATH = 'lambda/layers/json_utils'
JSON_UTILS_LAYER_NAME_BASE = 'MakiJsonUtils'
JSON_UTILS_LAYER_DESC = 'MAKI JSON Utils Layer'

OPENSEARCH_UTILS_LAYER_PATH = 'lambda/layers/opensearch_utils'
OPENSEARCH_UTILS_LAYER_NAME_BASE = 'MakiOpenSearchUtils'
OPENSEARCH_UTILS_LAYER_DESC = 'MAKI OpenSearch Utils Layer'

#Sagemaker
SAGEMAKER_INSTANCE_TYPE = "ml.t3.medium"
SAGEMAKER_NOTEBOOK_NAME = "maki-notebook"
