"""
MAKI Support Cases Data Ingestion Handler

This Lambda function serves as the primary data ingestion point for AWS 
Enterprise Support cases, retrieving data from Cloud Intelligence Dashboard 
(CID) or processing synthetic data for testing purposes.

Purpose:
- Ingest support cases from CID or synthetic data sources
- Process and merge case communications with metadata
- Generate Bedrock-compatible batch inference records
- Provide event counts for processing mode decisions (on-demand vs batch)
- Support both real CID data and synthetic test data

Key Features:
- CID integration with configurable skip option for testing
- Support case communication and metadata merging
- Batch record generation for Bedrock inference
- SSM Parameter Store integration for configuration
- Flexible data source handling (CID or synthetic)
- Event counting for processing mode determination

Processing Flow:
1. Retrieve configuration from SSM Parameter Store
2. Check CID_SKIP flag to determine data source
3. Extract case communications from CID (if enabled)
4. Extract case metadata from CID (if enabled)
5. Merge communications with metadata
6. Generate Bedrock batch inference records
7. Store processed records in aggregation bucket
8. Count available files and return processing information

Environment Variables:
- CID_SKIP: Flag to skip CID and use synthetic data ('true'/'false')
- S3_AGG: Aggregation bucket for processed cases
- S3_CID: CID data bucket
- BEDROCK_CATEGORIZE_TEMPERATURE: Temperature for categorization
- BEDROCK_MAX_TOKENS: Maximum tokens for processing
- BEDROCK_CATEGORIZE_TOP_P: Top-p parameter for categorization
- CATEGORY_BUCKET_NAME: Bucket containing category examples
- CATEGORIES: List of supported categories
- CASES_CATEGORY_OUTPUT_FORMAT: Output format specification

SSM Parameters Used:
- maki-{account}-{region}-events-since: Start time for event retrieval
- maki-{account}-{region}-mode: Processing mode (retrieved for consistency)

Input Event Structure:
- No specific input required (uses environment variables and SSM)

Output Structure:
- eventsTotal: Total number of cases available for processing
- events: List of case file keys for processing
- ondemand_run_datetime: Timestamp range for output organization
- mode: Current processing mode from SSM

Data Processing:
- Merges case communications with metadata
- Converts to JSONL format for Bedrock compatibility
- Generates batch inference records with prompts
- Organizes files for both on-demand and batch processing

Integration Points:
- CID: Primary data source for real support cases
- SSM Parameter Store: Configuration and timing parameters
- S3: Data storage and file organization
- Step Functions: Provides event counts for processing decisions
"""

import os
import sys
import boto3
sys.path.append('/opt')
from prompt_gen_input import gen_batch_record_cases
from s3 import find_files_in_s3, get_s3_obj_body, store_data
from validate_jsonl import jsonl_to_dict, json_to_dict, dict_to_jsonl
from datetime import datetime

def get_mode_from_ssm():
    """Get MODE value from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-mode")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting mode from SSM: {e}")
        return 'cases'  # default fallback

def get_events_since_from_ssm():
    """Get EVENTS_SINCE value from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-events-since")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting events-since from SSM: {e}")
        return '2023-01-01T00:00:00Z'  # default fallback

def handler(event, context):
    # Get start time from SSM Parameter Store
    start_t = get_events_since_from_ssm() 

    # if this is true, it will not get any files from CID
    cid_skip = os.environ['CID_SKIP']

    s3_agg = os.environ['S3_AGG']
    s3_cid = os.environ['S3_CID']   
    bedrock_categorize_temperature = float(os.environ['BEDROCK_CATEGORIZE_TEMPERATURE'])
    bedrock_max_tokens = int(os.environ['BEDROCK_MAX_TOKENS'])
    bedrock_categorize_top_p = float(os.environ['BEDROCK_CATEGORIZE_TOP_P'])
    categoryBucketName = os.environ['CATEGORY_BUCKET_NAME']
    categories = os.environ['CATEGORIES']
    categoryOutputFormat = os.environ['CASES_CATEGORY_OUTPUT_FORMAT']

    prefix = 'support-cases/support-cases-communications'
    file_ext = '.json' # not really json data, but jsonl
    recursive = True

    if cid_skip == 'true':
        print("skipping getting cases from CID")
        files = []
    else: 
        files = find_files_in_s3(bucket_name=s3_cid, prefix=prefix, file_ext=file_ext, recursive=recursive)
    
    # get case communications
    case_comms = {}
    try: 
        for case in files:
            case_data = get_s3_obj_body(bucket_name=s3_cid, object_key=case['Key'], decode=True) 
            case_data = jsonl_to_dict(case_data)
            case_comms[case_data['CaseId']] = case_data['Body']
    except Exception as e:
        print(f"Could not get case communications: {e}")
        return {
            'error': f"Could not get case communications: {e}"
        }

    # get case meta
    # and merge them with the case comms, and create the batch record
    try:
        prefix = 'support-cases/support-cases-data'
        file_ext = '.json' # really is json data, and not jsonl

        if cid_skip == 'true':
            print("skipping getting case meta from CID")
            files = []
        else:
            files = find_files_in_s3(bucket_name=s3_cid, prefix=prefix, file_ext=file_ext, recursive=recursive)

        for case in files:
            case_data = get_s3_obj_body(bucket_name=s3_cid, object_key=case['Key'], decode=True)
            case_data = json_to_dict(case_data)
            case = {
                'id': case_data['CaseId'],
                'meta': case_data,
                'communication': case_comms[case_data['CaseId']]
            }
            case = dict_to_jsonl(case)

        # final output must be in jsonl, for Bedrock Batch Inference
        # for ondemand, we will adapt to use the same files
            case_obj_key = case_data['CaseId'] + '.jsonl'
            batch_record = gen_batch_record_cases(case, 
                                            bedrock_categorize_temperature, 
                                            bedrock_max_tokens, 
                                            bedrock_categorize_top_p, 
                                            categoryBucketName, 
                                            categories,
                                            categoryOutputFormat) 

            store_data(batch_record, s3_agg, case_obj_key)

    except Exception as e:
        print(f"Could not create the prompt record: {e}")
        return {
            'error': f"Could not create the prompt record: {e}"
        }

    # count the jsonl records.  If count meets Bedrock Batch Inference job threshold, create a batch inference job.
    # otherwise, use ondemand.
    prefix = 'case-'
    file_ext = '.jsonl'
    recursive = False 
    
    # even if CID_SKIP='true', we check for files in the aggregated s3, for files that came from outside CID
    prompt_files = find_files_in_s3(bucket_name=s3_agg, prefix=prefix, file_ext=file_ext, recursive=recursive) 
    files = []

    for file in prompt_files:
        out = file['Key']
        files.append(out)
    
    start_time = get_events_since_from_ssm()
    end_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    ondemand_run_datetime = f"{start_time}-{end_time}"
    # this is used to create the bucket prefix for ondemand runs.  Not used for batch
         
    return {
        'eventsTotal': len(files),
        'events': files,
        'ondemand_run_datetime': ondemand_run_datetime,
        'mode': get_mode_from_ssm()
    }