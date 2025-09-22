import os
import sys
from datetime import datetime

sys.path.append('/opt')
from s3 import store_data, list_bucket_object_keys, get_s3_obj_body
from prompt_agg_cases import aggregate_prompt as aggregate_prompt
from validate_jsonl import is_valid_json

def handler(event, context):

    bucket_name_report = os.environ['S3_AGG_OUTPUT']
    model_id = os.environ['MODEL_ID']
    max_tokens = os.environ['BEDROCK_MAX_TOKENS']
    bedrock_temperature = os.environ['BEDROCK_SUMMARY_TEMPERATURE']
    summary_output_format = os.environ['SUMMARY_OUTPUT_FORMAT']

    ondemand_run_datetime = event['ondemand_run_datetime']
    summary_file = datetime.now().strftime(f"ondemand/{ondemand_run_datetime}/summary.json")

    try:

        # S3 Max allows to put limits on QuickSight
        # get rid of this with Athena/Glue tables
        ondemand_output = list_bucket_object_keys(bucket_name_report)

        aggregate = ''

        # extract llm output from the batch returns
        # also aggregate them
        for event in ondemand_output: 
            if event.endswith('manifest.json.out'): # write a better way to skip this
                continue

            aggregate += get_s3_obj_body(bucket_name_report, event, True)

        out = aggregate_prompt(
            model_id_input=model_id,
            events=aggregate,
            temperature=bedrock_temperature,
            summary_output_format=summary_output_format,
            max_tokens=max_tokens
        )

        store_data(out, bucket_name_report, summary_file)

        return {
            'summary': out
        }
        
    except Exception as e:
        print(f"Error processing output from ondemand inference job: {str(e)}")
        raise
