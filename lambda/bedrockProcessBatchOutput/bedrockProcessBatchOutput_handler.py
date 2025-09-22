import os
import json
import sys
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
    key = os.environ['KEY']

    # each report is set to this timekey
    timestamp = datetime.now().strftime("batch/%Y%m%d-%H%M%S")

    try:

        #batch_output = list_bucket_object_keys(bucket_name_batch_output)[:s3_max]
        batch_output = list_bucket_object_keys(bucket_name_batch_output, prefix="maki-")

        aggregate = ''

        # extract llm output from the batch returns
        # also aggregate them
        eventsN = 0
        for event in batch_output: 
            if event.endswith('manifest.json.out'): # used for batch inf
                move_s3_object(bucket_name_batch_output, event, bucket_name_archive, event)
                continue

            obj = get_s3_obj_body(bucket_name_batch_output, event, True)
            data = json.loads(obj)
            eventsN += 1

            try:
                val = data['modelOutput']['output']['message']['content'][0]['text']
                if is_valid_json(val):
                    json_val = json.loads(val)
                    key = timestamp + '/events/' + event.split('/')[2].split('.')[0] + '-output.json'
                    aggregate += 'event: '  + str(json_val['caseId']) + ':\n'
                    aggregate += 'sentiment: ' + str(json_val['sentiment']) + '\n'
                    aggregate += json_val['event_summary'] + '\n\n'
                    print("Store " + key + ' in ' + bucket_name_report) 
                    store_data(val, bucket_name_report, key)
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
            print("processed " + str(eventsN) + " events")
            store_data(out, bucket_name_report, f'{timestamp}/summary.json')
        else:
            print("No new batch outputs found...")
        
        empty_s3_bucket(bucket_name_batches)
        
    except Exception as e:
        print(f"Error creating report from batch inference jobs: {str(e)}")
        raise
