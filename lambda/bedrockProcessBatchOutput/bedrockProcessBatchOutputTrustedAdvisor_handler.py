"""
MAKI Bedrock Batch Output Processing Handler for Trusted Advisor

This Lambda function processes the outputs from Bedrock batch inference jobs for 
AWS Trusted Advisor recommendations, aggregating individual results into comprehensive 
operational summaries and organizing outputs for reporting and analysis.

Purpose:
- Process batch inference job outputs for AWS Trusted Advisor recommendations
- Aggregate individual recommendation analyses into operational summaries
- Organize processed results in S3 for reporting and analysis
- Generate executive summaries using advanced Bedrock models
- Clean up temporary batch processing files

Key Features:
- Batch output file discovery and processing across multiple jobs
- JSON validation and error handling for malformed outputs
- Aggregation of recommendation summaries, priorities, and operational insights
- Executive summary generation using sophisticated models
- S3 file organization with timestamped directory structure
- Cleanup of temporary batch processing files

Processing Flow:
1. Receive batch job details from Step Functions
2. Discover and collect all batch output files from S3
3. Process individual Trusted Advisor recommendation analysis results
4. Extract and validate JSON outputs from batch inference
5. Aggregate recommendation summaries and priority information
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
- summary: Generated executive summary of all processed Trusted Advisor recommendations

File Organization:
- Individual results: batch/{timestamp}/events/{recommendation-id}-output.json
- Executive summary: batch/{timestamp}/trusted_advisor_summary.json
- Timestamped directories for historical tracking

Trusted Advisor Specific Features:
- Handles recommendation IDs and status codes
- Processes cost optimization and security assessments
- Aggregates service-specific optimization insights
- Supports vector embedding context from processing
"""

import os
import sys
import json
import boto3
from datetime import datetime

sys.path.append('/opt')
from s3 import store_data, list_bucket_object_keys, get_s3_obj_body, move_s3_object, empty_s3_bucket
from prompt_agg_trusted_advisor import aggregate_prompt as aggregate_prompt
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
        print(f"Processing {len(batch_output)} files from batch output")
        for bucket, event_key in batch_output: 
            print(f"Processing file: s3://{bucket}/{event_key}")
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
                print(f"Processing recommendation {eventsN}: {event_key}")
                if is_valid_json(val):
                    json_val = json.loads(val)
                    # Handle Trusted Advisor recommendation file naming - extract filename from path
                    filename = event_key.split('/')[-1].split('.')[0] if '/' in event_key else event_key.split('.')[0]
                    key = timestamp + '/events/' + filename + '-output.json'
                    print(f"Storing individual recommendation file: {key}")
                    aggregate += 'trusted_advisor_recommendation: '  + str(json_val.get('checkId', json_val.get('recommendationId', 'unknown'))) + ':\n'
                    aggregate += 'status: ' + str(json_val.get('status', json_val.get('priority', 'unknown'))) + '\n'
                    aggregate += json_val.get('recommendation_summary', json_val.get('trusted_advisor_summary', '')) + '\n\n'
                    print("Store " + key + ' in ' + bucket_name_report) 
                    
                    # Store JSON directly without reformatting
                    try:
                        s3_client = boto3.client('s3')
                        s3_client.put_object(
                            Bucket=bucket_name_report,
                            Key=key,
                            Body=val,
                            ContentType='application/json'
                        )
                        print(f"Successfully stored individual recommendation file: {key}")
                    except Exception as e:
                        print(f"Error storing individual recommendation file {key}: {str(e)}")
                    
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
            print("processed " + str(eventsN) + " Trusted Advisor recommendations")
            store_data(out, bucket_name_report, f'{timestamp}/trusted_advisor_summary.json')
        else:
            print("No new batch outputs found...")
        
        empty_s3_bucket(bucket_name_batches)

        return {
            'summary': out
        }
        
    except Exception as e:
        print(f"Error processing output from batch inference job: {str(e)}")
        raise