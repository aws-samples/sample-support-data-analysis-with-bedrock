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