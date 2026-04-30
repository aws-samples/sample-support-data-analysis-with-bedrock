"""
MAKI Health Events Data Ingestion Handler

This Lambda function serves as the primary data ingestion point for AWS Health 
events, retrieving data from OpenSearch Serverless and processing it for 
MAKI analysis workflows.

Purpose:
- Ingest AWS Health events from OpenSearch Serverless
- Process health events into Bedrock-compatible batch inference records
- Support vector embedding context from OpenSearch storage
- Provide event counts for processing mode decisions (on-demand vs batch)
- Enable operational health insights and impact analysis

Key Features:
- OpenSearch Serverless integration with AWS authentication
- Health event querying with time-based filtering
- Vector embedding support for semantic analysis
- Batch record generation for Bedrock inference
- SSM Parameter Store integration for configuration
- Configurable query size limits for performance optimization

Processing Flow:
1. Retrieve configuration from SSM Parameter Store
2. Connect to OpenSearch Serverless with AWS authentication
3. Query health events based on lastUpdatedTime filter
4. Process each health event into structured format
5. Generate Bedrock batch inference records with prompts
6. Store processed records in health aggregation bucket
7. Count available files and return processing information

Environment Variables:
- OPENSEARCH_INDEX: OpenSearch index containing health events
- S3_HEALTH_AGG: Aggregation bucket for processed health events
- HEALTH_OUTPUT_FORMAT: Output format specification for health events
- BEDROCK_CATEGORIZE_TEMPERATURE: Temperature for categorization
- BEDROCK_MAX_TOKENS: Maximum tokens for processing
- BEDROCK_CATEGORIZE_TOP_P: Top-p parameter for categorization

SSM Parameters Used:
- maki-{account}-{region}-opensearch-endpoint: OpenSearch collection endpoint
- maki-{account}-{region}-opensearch-query-size: Maximum events per query
- maki-{account}-{region}-events-since: Start time for event retrieval
- maki-{account}-{region}-mode: Processing mode (retrieved for consistency)

Input Event Structure:
- No specific input required (uses environment variables and SSM)

Output Structure:
- eventsTotal: Total number of health events available for processing
- events: List of health event file keys for processing
- ondemand_run_datetime: Timestamp range for output organization
- mode: Always returns 'health' for this handler

Health Event Processing:
- Extracts comprehensive health event metadata
- Preserves event descriptions and affected entities
- Maintains event ARNs and service information
- Converts to JSONL format for Bedrock compatibility
- Generates batch inference records with health-specific prompts

OpenSearch Integration:
- Uses AWSV4SignerAuth for OpenSearch Serverless authentication
- Queries based on lastUpdatedTime for recent events
- Supports configurable result size limits
- Handles vector embedding context when available
- Provides error handling for connection issues

Integration Points:
- OpenSearch Serverless: Primary data source for health events
- SSM Parameter Store: Configuration and timing parameters
- S3: Data storage and file organization
- Step Functions: Provides event counts for processing decisions
- Bedrock: Downstream processing for health event analysis
"""

import os
import sys
import json
import boto3
import re
from datetime import datetime
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

sys.path.append('/opt')
from prompt_gen_input import gen_batch_record_health
from s3 import store_data
from validate_jsonl import dict_to_jsonl

def validate_network_payload(data):
    """Validate network payload structure and content"""
    if not isinstance(data, dict):
        raise ValueError("Invalid payload: must be dictionary")
    
    # Validate required fields exist and are proper types
    required_fields = ['hits', 'took', 'timed_out']
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate hits structure
    hits = data.get('hits', {})
    if not isinstance(hits, dict) or 'hits' not in hits:
        raise ValueError("Invalid hits structure")
    
    # Validate individual hit records
    for hit in hits.get('hits', []):
        if not isinstance(hit, dict) or '_source' not in hit:
            raise ValueError("Invalid hit record structure")
        
        source = hit['_source']
        # Sanitize text fields to prevent injection
        for field in ['eventDescription', 'service', 'eventTypeCategory']:
            if field in source and isinstance(source[field], str):
                # Remove potentially dangerous characters
                source[field] = re.sub(r'[<>"\';\\]', '', source[field])
    
    return data

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
        return "placeholder-please-update-with-your-endpoint"  # default fallback

def get_opensearch_query_size_from_ssm():
    """Get OPENSEARCH_QUERY_SIZE value from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-query-size")
        return int(response['Parameter']['Value'])
    except Exception as e:
        print(f"Error getting opensearch-query-size from SSM: {e}")
        return 10000  # default fallback
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
            "sort": [{"lastUpdatedTime": {"order": "desc"}}],
            "size": get_opensearch_query_size_from_ssm()
        }

        response = client.search(index=opensearch_index, body=query)
        
        # Validate the response payload
        validated_response = validate_network_payload(response)
        
        return validated_response['hits']['hits']
        
    except Exception as e:
        print(f"Error querying OpenSearch: {e}")
        return []

def handler(event, context):
    # Environment variables
    opensearch_endpoint = get_opensearch_endpoint_from_ssm()  # Get from SSM instead of env var
    opensearch_index = os.environ['OPENSEARCH_INDEX']
    start_time = get_events_since_from_ssm()
    
    s3_health_agg = os.environ['S3_HEALTH_AGG']
    health_output_format = os.environ['HEALTH_OUTPUT_FORMAT']
    bedrock_categorize_temperature = float(os.environ['BEDROCK_CATEGORIZE_TEMPERATURE'])
    bedrock_max_tokens = int(os.environ['BEDROCK_MAX_TOKENS'])
    bedrock_categorize_top_p = float(os.environ['BEDROCK_CATEGORIZE_TOP_P'])

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
                health_output_format,
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
