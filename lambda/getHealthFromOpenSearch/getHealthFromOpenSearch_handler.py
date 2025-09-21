import os
import sys
import json
import boto3
from datetime import datetime
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

sys.path.append('/opt')
from prompt_gen_cases_input import gen_batch_record
from s3 import store_data
from validate_jsonl import dict_to_jsonl

def handler(event, context):
    # Environment variables
    opensearch_skip = os.environ['OPENSEARCH_SKIP']
    opensearch_endpoint = os.environ['OPENSEARCH_ENDPOINT']
    opensearch_index = os.environ['OPENSEARCH_INDEX']
    health_events_after_time = os.environ['HEALTH_EVENTS_AFTER_TIME']
    
    s3_health_agg = os.environ['S3_HEALTH_AGG']
    bedrock_categorize_temperature = float(os.environ['BEDROCK_CATEGORIZE_TEMPERATURE'])
    bedrock_max_tokens = int(os.environ['BEDROCK_MAX_TOKENS'])
    bedrock_categorize_top_p = float(os.environ['BEDROCK_CATEGORIZE_TOP_P'])
    categoryBucketName = os.environ['CATEGORY_BUCKET_NAME']
    categories = os.environ['CATEGORIES']
    categoryOutputFormat = os.environ['CATEGORY_OUTPUT_FORMAT']

    if opensearch_skip == 'true':
        print("Skipping getting health events from OpenSearch")
        return {
            'healthEventsTotal': 0,
            'healthEvents': [],
            'ondemand_run_datetime': datetime.now().strftime("%Y%m%d-%H%M%S")
        }

    try:
        # Set up OpenSearch client with AWS authentication
        region = boto3.Session().region_name
        service = 'es'
        credentials = boto3.Session().get_credentials()
        awsauth = AWSRequestsAuth(credentials, region, service)
        
        client = OpenSearch(
            hosts=[{'host': opensearch_endpoint.replace('https://', ''), 'port': 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )

        # Query for health events after the specified time
        query = {
            "query": {
                "range": {
                    "startTime": {
                        "gte": health_events_after_time
                    }
                }
            },
            "size": 10000,  # Adjust as needed
            "sort": [
                {
                    "startTime": {
                        "order": "desc"
                    }
                }
            ]
        }

        response = client.search(
            index=opensearch_index,
            body=query
        )

        health_events = response['hits']['hits']
        processed_files = []

        for event_hit in health_events:
            event_data = event_hit['_source']
            
            # Create a structured health event record
            health_event = {
                'id': event_data.get('eventArn', event_hit['_id']),
                'meta': {
                    'eventArn': event_data.get('eventArn'),
                    'service': event_data.get('service'),
                    'eventTypeCode': event_data.get('eventTypeCode'),
                    'eventTypeCategory': event_data.get('eventTypeCategory'),
                    'region': event_data.get('region'),
                    'startTime': event_data.get('startTime'),
                    'endTime': event_data.get('endTime'),
                    'lastUpdatedTime': event_data.get('lastUpdatedTime'),
                    'statusCode': event_data.get('statusCode')
                },
                'description': event_data.get('eventDescription', {}).get('latestDescription', ''),
                'affectedEntities': event_data.get('affectedEntities', [])
            }
            
            # Convert to JSONL format for Bedrock Batch Inference
            health_event_jsonl = dict_to_jsonl(health_event)
            
            # Generate batch record using the same prompt generation logic
            event_obj_key = f"health-{event_data.get('eventArn', event_hit['_id']).replace(':', '-').replace('/', '-')}.jsonl"
            batch_record = gen_batch_record(
                health_event_jsonl,
                bedrock_categorize_temperature,
                bedrock_max_tokens,
                bedrock_categorize_top_p,
                categoryBucketName,
                categories,
                categoryOutputFormat
            )
            
            # Store in S3
            store_data(batch_record, s3_health_agg, event_obj_key)
            processed_files.append(event_obj_key)

    except Exception as e:
        print(f"Could not get health events from OpenSearch: {e}")
        return {
            'error': f"Could not get health events from OpenSearch: {e}"
        }

    ondemand_run_datetime = datetime.now().strftime("%Y%m%d-%H%M%S")
    
    return {
        'healthEventsTotal': len(processed_files),
        'healthEvents': processed_files,
        'ondemand_run_datetime': ondemand_run_datetime
    }
