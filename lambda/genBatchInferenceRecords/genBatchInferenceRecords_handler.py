"""
MAKI Batch Inference Records Generator (Legacy/Unused)

This Lambda function was designed to generate batch inference records from 
CID (Cloud Intelligence Dashboard) data, but is currently not used in the 
active MAKI workflow. The functionality has been integrated into the main 
getCasesFromCID handler.

Purpose:
- Originally intended for separate batch record generation
- Would have processed CID support case data into Bedrock-compatible format
- Part of earlier MAKI architecture with separate processing stages

Legacy Functionality:
- CID data extraction and processing
- Support case communication and metadata merging
- Batch record generation for Bedrock inference
- JSONL format conversion for batch processing

Current Status:
- Not actively used in current MAKI workflow
- Functionality integrated into getCasesFromCID_handler
- Maintained for historical reference

Environment Variables:
- S3_AGG: Aggregation bucket for processed cases
- S3_CID: CID data bucket
- BEDROCK_CATEGORIZE_TEMPERATURE: Temperature for categorization
- BEDROCK_MAX_TOKENS: Maximum tokens for processing
- BEDROCK_CATEGORIZE_TOP_P: Top-p parameter for categorization
- CATEGORY_BUCKET_NAME: Bucket containing category examples
- CATEGORIES: List of supported categories
- CASES_CATEGORY_OUTPUT_FORMAT: Output format specification

Note:
This function is maintained for historical reference but is not part of 
the active MAKI processing pipeline. Current MAKI architecture handles 
batch record generation within the main data ingestion process.
"""

import os
import sys
sys.path.append('/opt')
from s3 import find_files_in_s3, get_s3_obj_body, store_data
from prompt_gen_input import gen_batch_record_cases
from validate_jsonl import jsonl_to_dict, json_to_dict, dict_to_jsonl

def handler(event, context):
    # need to use start_t 
   # start_t = os.environ['START_T'] 

    s3_agg = os.environ['S3_AGG']
    s3_cid = os.environ['S3_CID']   
    bedrock_categorize_temperature = float(os.environ['BEDROCK_CATEGORIZE_TEMPERATURE'])
    bedrock_max_tokens = int(os.environ['BEDROCK_MAX_TOKENS'])
    bedrock_categorize_top_p = float(os.environ['BEDROCK_CATEGORIZE_TOP_P'])
    categoryBucketName = os.environ['CATEGORY_BUCKET_NAME']
    categories = os.environ['CATEGORIES']
    categoryOutputFormat = os.environ['CASES_CATEGORY_OUTPUT_FORMAT']

    #print("getting CID cases from: ", start_t, ':', s3_cid) 

    prefix = 'support-cases/support-cases-communications'
    file_ext = '.json' # not really json data, but jsonl
    recursive = True

    files = find_files_in_s3(bucket_name=s3_cid, prefix=prefix, file_ext=file_ext, recursive=recursive)
    case_comms = {}

    try: 
        for event in files:
            event_data = get_s3_obj_body(bucket_name=s3_cid, object_key=event['Key'], decode=True)
            event_data = jsonl_to_dict(event_data)
            case_comms[event_data['CaseId']] = event_data['Body']

    # collect support meta
        prefix = 'support-cases/support-cases-data'
        file_ext = '.json' # really is json data, and not jsonl

        files = find_files_in_s3(bucket_name=s3_cid, prefix=prefix, file_ext=file_ext, recursive=recursive)
        for event in files:
            event_data = get_s3_obj_body(bucket_name=s3_cid, object_key=event['Key'], decode=True)
            event_data = json_to_dict(event_data)
            case_data = event_data  # Fix: assign event_data to case_data
            case = {
                'id': event_data['CaseId'],
                'meta': case_data,
                'communication': case_comms[case_data['CaseId']]
            }
            case = dict_to_jsonl(case)

        # final output must be in jsonl, for Bedrock Batch Inference
            case_obj_key = case_data['CaseId'] + '.jsonl'
            batch_record = gen_batch_record_cases(case, bedrock_categorize_temperature, bedrock_max_tokens, bedrock_categorize_top_p, categoryBucketName, categoryOutputFormat, categories)
            store_data(batch_record, s3_agg, case_obj_key)

    except Exception as e:
        return {
            # Handle any exceptions
            print(f"Error: {e}")
        }
