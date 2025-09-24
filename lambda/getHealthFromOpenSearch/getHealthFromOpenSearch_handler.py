import os
import sys
import json
import boto3
from datetime import datetime
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

sys.path.append('/opt')
from prompt_gen_input import gen_batch_record_health
from s3 import store_data
from validate_jsonl import dict_to_jsonl

def get_mode_from_ssm():
    """Get MODE value from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-mode")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting mode from SSM: {e}")
        return 'health'  # default fallback

def get_events_since_from_ssm():
    """Get EVENTS_SINCE value from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-events-since")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting events-since from SSM: {e}")
        return '2023-01-01T00:00:00Z'  # default fallback

def get_opensearch_endpoint_from_ssm():
    """Get OpenSearch endpoint from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-endpoint")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"Error getting opensearch-endpoint from SSM: {e}")
        return os.environ.get('OPENSEARCH_ENDPOINT', 'placeholder-endpoint')  # fallback to env var

def get_health_events_from_opensearch(opensearch_endpoint, opensearch_index, start_time, region):
    """Query health events from OpenSearch Serverless since start_time based on when event was received"""
    try:
        host = opensearch_endpoint.replace('https://', '')
        
        # Use AWSV4SignerAuth for OpenSearch Serverless
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, region, 'aoss')
        
        client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )

        # Query for health events after the specified time based on lastUpdatedTime
        query = {
            "query": {
                "range": {
                    "lastUpdatedTime": {
                        "gte": start_time
                    }
                }
            },
            "sort": [{"lastUpdatedTime": {"order": "desc"}}]
        }

        response = client.search(index=opensearch_index, body=query)
        return response['hits']['hits']
        
    except Exception as e:
        print(f"Error querying OpenSearch: {e}")
        return []

def handler(event, context):
    # Environment variables
    opensearch_skip = os.environ['OPENSEARCH_SKIP']
    opensearch_endpoint = get_opensearch_endpoint_from_ssm()  # Get from SSM instead of env var
    opensearch_index = os.environ['OPENSEARCH_INDEX']
    start_time = get_events_since_from_ssm()
    
    s3_health_agg = os.environ['S3_HEALTH_AGG']
    bedrock_categorize_temperature = float(os.environ['BEDROCK_CATEGORIZE_TEMPERATURE'])
    bedrock_max_tokens = int(os.environ['BEDROCK_MAX_TOKENS'])
    bedrock_categorize_top_p = float(os.environ['BEDROCK_CATEGORIZE_TOP_P'])

    if opensearch_skip == 'true':
        print("Skipping getting health events from OpenSearch")
        start_time = get_events_since_from_ssm()
        end_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            'eventsTotal': 0,
            'events': [],
            'ondemand_run_datetime': f"{start_time}-{end_time}",
            'mode': get_mode_from_ssm()
        }

    try:
        region = boto3.Session().region_name
        
        # Get health events from OpenSearch
        health_events = get_health_events_from_opensearch(opensearch_endpoint, opensearch_index, start_time, region)
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
            
            # no need for categorization templates for health - already in the data
            batch_record = gen_batch_record_health(
                health_event_jsonl,
                bedrock_categorize_temperature,
                bedrock_max_tokens,
                bedrock_categorize_top_p
            )

            # Store in S3
            store_data(batch_record, s3_health_agg, event_obj_key)
            processed_files.append(event_obj_key)

    except Exception as e:
        print(f"Could not get health events from OpenSearch: {e}")
        return {
            'error': f"Could not get health events from OpenSearch: {e}"
        }

    start_time = get_events_since_from_ssm()
    end_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    ondemand_run_datetime = f"{start_time}-{end_time}"
    
    return {
        'eventsTotal': len(processed_files),
        'events': processed_files,
        'ondemand_run_datetime': ondemand_run_datetime,
        'mode': 'health'
    }
