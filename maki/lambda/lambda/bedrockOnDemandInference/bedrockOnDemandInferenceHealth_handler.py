"""
MAKI Bedrock On-Demand Inference Handler for Health Events

This Lambda function processes individual AWS Health events through Amazon Bedrock 
on-demand inference, providing immediate analysis and categorization for small 
volumes of health events (< 100 events).

Purpose:
- Process individual health events through Bedrock models
- Generate health event analysis, categorization, and impact assessment
- Handle real-time inference for immediate operational insights
- Manage S3 file operations for health event processing

Key Features:
- Exponential backoff retry logic for robust API handling
- Individual health event processing with detailed analysis
- S3 file management with organized output structure
- Error handling and recovery mechanisms
- Integration with MAKI prompt generation system for health events

Processing Flow:
1. Receive individual health event data from Step Functions Map state
2. Retrieve health event file from S3 input bucket
3. Parse JSONL format and extract Bedrock prompt components
4. Execute Bedrock inference with exponential backoff retry
5. Process and store analysis results in organized S3 structure
6. Maintain input files (no deletion for health events)

Environment Variables:
- S3_INPUT: Input bucket containing health event files
- S3_OUTPUT: Output bucket for processed results
- BEDROCK_TEXT_MODEL: Bedrock model ID for inference

Input Event Structure:
- case: S3 key for the health event file to process
- ondemand_run_datetime: Timestamp for output organization

Output Structure:
- event_file: Processed health event file identifier

Retry Logic:
- Implements exponential backoff (1, 2, 4 seconds)
- Maximum 5 retry attempts for transient failures
- Handles Bedrock throttling and temporary service issues

Health Event Specific Features:
- Preserves original health event files (no deletion)
- Handles health event specific data structures
- Supports vector embedding context from OpenSearch
"""

import sys
sys.path.append('/opt')

import boto3
from botocore.exceptions import ClientError
import os
import time

from s3 import get_s3_obj_body, store_data
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
    print(f"Processing health event: {event_data}")
    event_file = event_data
    event_file_data = get_s3_obj_body(input_s3, event_file, False)
    event_dict = string_to_dict(event_file_data)
    
    if event_dict is None:
        raise ValueError(f"Failed to parse event data from S3 object: {event_file}")

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
    event_file = event_data  # Use the S3 key as filename base
    new_event_file = f"{event_file}.json"
    new_event_file = f"ondemand/{ondemand_run_datetime}/{new_event_file}"
    store_data(out, output_s3, new_event_file)
    print(f"processed health event into {new_event_file}")

    return {
        'event_file': event_file
    }
