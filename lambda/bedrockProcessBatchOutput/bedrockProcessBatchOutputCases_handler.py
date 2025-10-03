"""
MAKI Bedrock Batch Output Processing Handler for Support Cases

This Lambda function processes the outputs from Bedrock batch inference jobs for 
support cases, aggregating individual results into comprehensive summaries and 
organizing outputs for reporting and analysis.

Purpose:
- Process batch inference job outputs for support cases
- Aggregate individual case analyses into comprehensive summaries
- Organize processed results in S3 for reporting and analysis
- Generate executive summaries using advanced Bedrock models
- Clean up temporary batch processing files

Key Features:
- Batch output file discovery and processing across multiple jobs
- JSON validation and error handling for malformed outputs
- Aggregation of case summaries, sentiments, and insights
- Executive summary generation using sophisticated models
- S3 file organization with timestamped directory structure
- Cleanup of temporary batch processing files

Processing Flow:
1. Receive batch job details from Step Functions
2. Discover and collect all batch output files from S3
3. Process individual case analysis results
4. Extract and validate JSON outputs from batch inference
5. Aggregate case summaries and sentiment analysis
6. Generate executive summary using advanced Bedrock model
7. Store organized results in report bucket
8. Clean up temporary batch processing files

Environment Variables:
- S3_BATCH_OUTPUT: Bucket containing batch inference outputs
- S3_REPORT: Bucket for final processed reports
- S3_ARCHIVE: Bucket for long-term storage
- S3_BATCHES: Temporary batch processing bucket
- MODEL_ID: Advanced Bedrock model for summary generation
- BEDROCK_MAX_TOKENS: Maximum tokens for summary generation
- BEDROCK_SUMMARY_TEMPERATURE: Temperature for summary generation
- SUMMARY_OUTPUT_FORMAT: Format specification for summaries

Input Event Structure:
- batchInferenceResult: Contains batch job details and output locations
- batch_jobs: List of completed batch jobs with output URIs

Output Structure:
- summary: Generated executive summary of all processed cases

File Organization:
- Individual results: batch/{timestamp}/events/{case-id}-output.json
- Executive summary: batch/{timestamp}/summary.json
- Timestamped directories for historical tracking
"""

import os
import sys
import json
from datetime import datetime

sys.path.append('/opt')
from s3 import store_data, list_bucket_object_keys, get_s3_obj_body, move_s3_object, empty_s3_bucket
from prompt_agg_cases import aggregate_prompt as aggregate_prompt
from validate_jsonl import is_valid_json

def handler(event, context):

    bucket_name_batch_output = os.environ['S3_BATCH_OUTPUT']
    bucket_name_report = os.environ['S3_REPORT']
    bucket_name_archive = os.environ['S3_ARCHIVE']
    bucket_name_batches = os.environ['S3_BATCHES']
    model_id = os.environ['MODEL_ID']
    max_tokens = os.environ['BEDROCK_MAX_TOKENS']
    bedrock_temperature = os.environ['BEDROCK_SUMMARY_TEMPERATURE']
    summary_output_format = os.environ['SUMMARY_OUTPUT_FORMAT']

    # each report is set to this timekey
    timestamp = datetime.now().strftime("batch/%Y%m%d-%H%M%S")

    try:

        # Get the batch jobs from the batch inference result
        batch_inference_result = event.get('batchInferenceResult', {})
        batch_jobs = batch_inference_result.get('batch_jobs', [])
        print(f"Found {len(batch_jobs)} batch jobs to process")
        
        # Get all individual output files from all batch job output directories
        batch_output = []
        for job in batch_jobs:
            output_s3_uri = job.get('output_s3_uri', '')
            print(f"Processing batch job with output_s3_uri: {output_s3_uri}")
            if output_s3_uri:
                # Extract bucket and prefix from S3 URI
                if output_s3_uri.startswith('s3://'):
                    s3_parts = output_s3_uri[5:].split('/', 1)
                    if len(s3_parts) == 2:
                        output_bucket, output_prefix = s3_parts
                        print(f"Searching in bucket: {output_bucket}, prefix: {output_prefix}")
                        
                        # List all files recursively in the batch job output directory
                        batch_files = list_bucket_object_keys(output_bucket, prefix=output_prefix)
                        print(f"Found {len(batch_files)} files in {output_s3_uri}")
                        
                        # Filter for actual output files (not directories or manifest files)
                        for file_key in batch_files:
                            if file_key.endswith('.jsonl.out') or (file_key.endswith('.out') and not file_key.endswith('manifest.json.out')):
                                batch_output.append((output_bucket, file_key))
                                print(f"Added output file: s3://{output_bucket}/{file_key}")
        
        print(f"Found {len(batch_output)} total batch output files to process")

        aggregate = ''

        # extract llm output from the batch returns
        # also aggregate them
        eventsN = 0
        for bucket, event_key in batch_output: 
            if event_key.endswith('manifest.json.out'): # used for batch inf
                continue

            obj = get_s3_obj_body(bucket, event_key, True)
            if not obj or obj.strip() == '':
                print(f"Empty or invalid object for event: {event_key}")
                continue
            
            try:
                data = json.loads(obj)
            except json.JSONDecodeError as e:
                print(f"JSON decode error for event {event_key}: {e}")
                print(f"Object content: {repr(obj[:200])}")
                continue
            
            eventsN += 1

            try:
                val = data['modelOutput']['output']['message']['content'][0]['text']
                if is_valid_json(val):
                    json_val = json.loads(val)
                    # Handle case event file naming - extract filename from path
                    filename = event_key.split('/')[-1].split('.')[0] if '/' in event_key else event_key.split('.')[0]
                    key = timestamp + '/events/' + filename + '-output.json'
                    aggregate += 'event: '  + str(json_val['caseId']) + ':\n'
                    aggregate += 'sentiment: ' + str(json_val['sentiment']) + '\n'
                    aggregate += json_val['case_summary'] + '\n\n'
                    print("Store " + key + ' in ' + bucket_name_report) 
                    store_data(val, bucket_name_report, key)
                else:
                    print("Invalid JSON: " + val) # write code to handle these
            except KeyError:
                print("Invalid LLM OUTPUT: ", data) # write code to handle these

        out = aggregate_prompt(
            model_id_input=model_id,
            events=aggregate,
            temperature=bedrock_temperature,
            summary_output_format=summary_output_format,
            max_tokens=max_tokens
        )

        if (eventsN > 0):
            print("processed " + str(eventsN) + " events")
            store_data(out, bucket_name_report, f'{timestamp}/summary.json')
        else:
            print("No new batch outputs found...")
        
        empty_s3_bucket(bucket_name_batches)

        return {
            'summary': out
        }
        
    except Exception as e:
        print(f"Error processing output from batch inference job: {str(e)}")
        raise
