"""
MAKI Bedrock On-Demand Inference Handler for Support Cases

This Lambda function processes individual support cases through Amazon Bedrock 
on-demand inference, providing immediate analysis and categorization for small 
volumes of cases (< 100 cases).

Purpose:
- Process individual support cases through Bedrock models
- Generate case analysis, categorization, and sentiment analysis
- Handle real-time inference for immediate results
- Manage S3 file operations for input and output processing

Key Features:
- Exponential backoff retry logic for robust API handling
- Individual case processing with detailed analysis
- S3 file management with organized output structure
- Error handling and recovery mechanisms
- Integration with MAKI prompt generation system

Processing Flow:
1. Receive individual case data from Step Functions Map state
2. Retrieve case file from S3 input bucket
3. Parse JSONL format and extract Bedrock prompt components
4. Execute Bedrock inference with exponential backoff retry
5. Process and store analysis results in organized S3 structure
6. Clean up input files after successful processing

Environment Variables:
- S3_INPUT: Input bucket containing case files
- S3_OUTPUT: Output bucket for processed results
- BEDROCK_TEXT_MODEL: Bedrock model ID for inference

Input Event Structure:
- case: S3 key for the case file to process
- ondemand_run_datetime: Timestamp for output organization

Output Structure:
- event_file: Processed case file identifier

Retry Logic:
- Implements exponential backoff (1, 2, 4 seconds)
- Maximum 5 retry attempts for transient failures
- Handles Bedrock throttling and temporary service issues
"""

import sys
sys.path.append('/opt')

import boto3
from botocore.exceptions import ClientError
import os
import time

from s3 import get_s3_obj_body, store_data, delete_s3_object
from prompt_gen_input import generate_conversation
from validate_jsonl import string_to_dict

def exponential_backoff_retry(func, max_retries=5, initial_delay=1):
    """
    Implements exponential backoff retry logic
    """
    for attempt in range(max_retries):
        try:
            return func()
        except ClientError as e:
            if attempt == max_retries - 1:  # Last attempt
                raise  # Re-raise the last exception
            
            # Calculate delay with exponential backoff
            delay = initial_delay * (2 ** attempt)  # 1, 2, 4 seconds
            print(f"Retry attempt {attempt + 1} after {delay} seconds")
            time.sleep(delay)

def handler(event, context):


    print(f"boto3 version: {boto3.__version__}")
    event_data = event.get('case', 0) 
    ondemand_run_datetime = event['ondemand_run_datetime']

    input_s3 = os.environ['S3_INPUT']  # agg folder 
    output_s3 = os.environ['S3_OUTPUT'] # llm output folder
    model_id = os.environ['BEDROCK_TEXT_MODEL']

    bedrock_runtime = boto3.client('bedrock-runtime')

    # construct bedrock prompt for individual records
    print(f"Processing event: {event_data}")
    event_file = event_data
    event_file_data = get_s3_obj_body(input_s3, event_file, False)
    event_dict = string_to_dict(event_file_data)

    system_prompt = event_dict['modelInput']['system']

    messages = event_dict['modelInput']['messages']
    temperature = event_dict['modelInput']['inferenceConfig']['temperature']

    generate_conversation_with_params = lambda: generate_conversation(
        bedrock_runtime,
        model_id,
        system_prompt,
        messages,
        temperature
    )

    try:
        response = exponential_backoff_retry(
            generate_conversation_with_params,
            max_retries=5,
            initial_delay=1
        )
    except ClientError as e:
        print(f"Failed after retry attempts : {event_data}: {str(e)}")
        raise
        
    output_message = response['output']['message']
    # add output to the conversation, in case we have longer conversations
    messages.append(output_message)

    # Show the complete conversation.
    # for now return assistant output
    for message in messages:
        if message['role'] == 'assistant':
            out = message['content'][0]['text']
    
    # store output 
    old_event_file = event_file
    new_event_file = event_file.replace('.jsonl', '.json')
    new_event_file = f"ondemand/{ondemand_run_datetime}/{new_event_file}"
    store_data(out, output_s3, new_event_file)
    delete_s3_object(input_s3, old_event_file)
    print(f"processed {old_event_file} into {new_event_file}")

    return {
        'event_file': event_file
    }