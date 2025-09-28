import os
import sys
import json
import boto3
from datetime import datetime

sys.path.append('/opt')
from s3 import store_data, list_bucket_object_keys, get_s3_obj_body, move_s3_object, empty_s3_bucket
from prompt_agg_health import aggregate_prompt as aggregate_prompt
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

        # Get all batch job directories
        all_objects = list_bucket_object_keys(bucket_name_batch_output, prefix="")
        
        # Find batch job directories (they contain subdirectories with actual output files)
        batch_dirs = set()
        for obj_key in all_objects:
            if '/' in obj_key:
                # Extract the batch job directory (first part of the path)
                batch_dir = obj_key.split('/')[0]
                if batch_dir.startswith('maki-'):
                    batch_dirs.add(batch_dir)
        
        print(f"Found batch directories: {list(batch_dirs)}")
        
        # Get all individual output files from all batch directories
        batch_output = []
        for batch_dir in batch_dirs:
            batch_files = list_bucket_object_keys(bucket_name_batch_output, prefix=f"{batch_dir}/")
            batch_output.extend(batch_files)
        
        print(f"Found {len(batch_output)} total batch output files")

        aggregate = ''

        # extract llm output from the batch returns
        # also aggregate them
        eventsN = 0
        print(f"Processing {len(batch_output)} files from batch output")
        for event in batch_output: 
            print(f"Processing file: {event}")
            if event.endswith('manifest.json.out'): # used for batch inf
                move_s3_object(bucket_name_batch_output, event, bucket_name_archive, event)
                continue

            obj = get_s3_obj_body(bucket_name_batch_output, event, True)
            if not obj or obj.strip() == '':
                print(f"Empty or invalid object for event: {event}")
                continue
            
            try:
                data = json.loads(obj)
            except json.JSONDecodeError as e:
                print(f"JSON decode error for event {event}: {e}")
                print(f"Object content: {repr(obj[:200])}")
                continue
            
            eventsN += 1

            try:
                val = data['modelOutput']['output']['message']['content'][0]['text']
                print(f"Processing event {eventsN}: {event}")
                if is_valid_json(val):
                    json_val = json.loads(val)
                    # Handle health event file naming - extract filename from path
                    filename = event.split('/')[-1].split('.')[0] if '/' in event else event.split('.')[0]
                    key = timestamp + '/events/' + filename + '-output.json'
                    print(f"Storing individual event file: {key}")
                    aggregate += 'health_event: '  + str(json_val.get('arn', json_val.get('eventId', 'unknown'))) + ':\n'
                    aggregate += 'status: ' + str(json_val.get('statusCode', json_val.get('status', 'unknown'))) + '\n'
                    aggregate += json_val.get('event_summary', json_val.get('health_summary', '')) + '\n\n'
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
                        print(f"Successfully stored individual event file: {key}")
                    except Exception as e:
                        print(f"Error storing individual event file {key}: {str(e)}")
                    
                    move_s3_object(bucket_name_batch_output, event, bucket_name_archive, event)
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
            print("processed " + str(eventsN) + " health events")
            store_data(out, bucket_name_report, f'{timestamp}/health_summary.json')
        else:
            print("No new batch outputs found...")
        
        empty_s3_bucket(bucket_name_batches)

        return {
            'summary': out
        }
        
    except Exception as e:
        print(f"Error processing output from batch inference job: {str(e)}")
        raise
