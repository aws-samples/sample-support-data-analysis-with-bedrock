import os
import sys
import json
import boto3
from datetime import datetime, timedelta
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
from botocore.exceptions import ClientError

sys.path.append('/opt')
from prompt_gen_cases_input import gen_batch_record
from s3 import store_data
from validate_jsonl import dict_to_jsonl

def generate_embedding(text, bedrock_client, embedding_model, region='us-east-1'):
    """Generate embedding using Bedrock model from config"""
    if not text or not text.strip():
        return None
    
    try:
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })
        
        response = bedrock_client.invoke_model(
            modelId=embedding_model,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['embedding']
        
    except ClientError as e:
        if 'AccessDeniedException' in str(e):
            print(f"Error: Access denied to {embedding_model} model. Request access at Bedrock console.")
        return None
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def get_health_events_from_api(region, start_time):
    """Query AWS Health API for events since start_time"""
    try:
        health_client = boto3.client('health', region_name=region)
        
        print(f"Querying AWS Health events since {start_time}")
        
        # Get events using paginator
        paginator = health_client.get_paginator('describe_events')
        
        # Get events received since start_time
        page_iterator = paginator.paginate(
            filter={
                'lastUpdatedTimes': [
                    {
                        'from': datetime.fromisoformat(start_time.replace('Z', '+00:00')),
                        'to': datetime.now()
                    }
                ]
            }
        )
        
        events = []
        for page in page_iterator:
            events.extend(page['events'])
        
        print(f"Found {len(events)} health events")
        
        # Get event details
        event_details = []
        affected_entities = []
        if events:
            print("Fetching event details...")
            event_arns = [event['arn'] for event in events]
            
            # Process in batches of 10 (API limit)
            for i in range(0, len(event_arns), 10):
                batch = event_arns[i:i+10]
                try:
                    response = health_client.describe_event_details(eventArns=batch)
                    event_details.extend(response['successfulSet'])
                    
                    # Get affected entities for each event
                    for event_arn in batch:
                        try:
                            entities_response = health_client.describe_affected_entities(
                                filter={'eventArns': [event_arn]}
                            )
                            batch_entities = entities_response['entities']
                            for entity in batch_entities:
                                entity['eventArn'] = event_arn
                                affected_entities.append(entity)
                        except ClientError:
                            pass  # Skip if can't get entities
                            
                except ClientError as e:
                    print(f"Warning: Could not fetch details for batch {i//10 + 1}: {e}")
        
        return events, event_details, affected_entities
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'SubscriptionRequiredException':
            print("Error: AWS Health API requires Business or Enterprise support plan")
        else:
            print(f"Error querying Health API: {e}")
        return [], [], []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return [], [], []

def load_to_opensearch(events, event_details, affected_entities, opensearch_endpoint, index_name, region, bedrock_client, embedding_model):
    """Load health events into OpenSearch Serverless collection"""
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
            connection_class=RequestsHttpConnection,
            timeout=30
        )
        
        # Create mappings
        details_map = {detail['event']['arn']: detail for detail in event_details}
        entities_map = {}
        for entity in affected_entities:
            event_arn = entity['eventArn']
            if event_arn not in entities_map:
                entities_map[event_arn] = []
            entities_map[event_arn].append(entity)
        
        # Load events into OpenSearch
        loaded_count = 0
        for event in events:
            event_arn = event['arn']
            
            # Merge event with its details
            if event_arn in details_map:
                detail = details_map[event_arn]
                
                detailed_event = detail['event'].copy()
                detailed_event.update(event)
                event.clear()
                event.update(detailed_event)
                
                if 'eventDescription' in detail:
                    event['eventDescription'] = detail['eventDescription']
                    
                    # Generate embedding for latestDescription
                    latest_desc = detail['eventDescription'].get('latestDescription', '')
                    if latest_desc:
                        embedding = generate_embedding(latest_desc, bedrock_client, embedding_model, region)
                        if embedding:
                            event['eventDescription']['latestDescriptionVector'] = embedding
                
                if 'eventMetadata' in detail:
                    event['eventMetadata'] = detail['eventMetadata']
                event['affectedEntities'] = detail.get('affectedEntities', [])
            else:
                event.update({
                    'eventDescription': {},
                    'affectedEntities': []
                })
            
            # Add detailed affected entities
            if event_arn in entities_map:
                event['detailedAffectedEntities'] = entities_map[event_arn]
            
            # Index the event
            client.index(
                index=index_name,
                body=event,
                id=event_arn
            )
            loaded_count += 1
        
        client.indices.refresh(index=index_name)
        print(f"Loaded {loaded_count} health events into OpenSearch index: {index_name}")
        return loaded_count
        
    except Exception as e:
        print(f"Error loading to OpenSearch: {e}")
        return 0

def get_health_events_from_opensearch(opensearch_endpoint, opensearch_index, start_time, region):
    """Query health events from OpenSearch Serverless since start_time"""
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

        # Query for health events after the specified time
        query = {
            "query": {
                "range": {
                    "startTime": {
                        "gte": start_time
                    }
                }
            },
            "size": 10000,
            "sort": [{"startTime": {"order": "desc"}}]
        }

        response = client.search(index=opensearch_index, body=query)
        return response['hits']['hits']
        
    except Exception as e:
        print(f"Error querying OpenSearch: {e}")
        return []

def handler(event, context):
    # Environment variables
    opensearch_skip = os.environ['OPENSEARCH_SKIP']
    opensearch_endpoint = os.environ['OPENSEARCH_ENDPOINT']
    opensearch_index = os.environ['OPENSEARCH_INDEX']
    start_time = os.environ['HEALTH_EVENTS_SINCE']
    
    s3_health_agg = os.environ['S3_HEALTH_AGG']
    bedrock_categorize_temperature = float(os.environ['BEDROCK_CATEGORIZE_TEMPERATURE'])
    bedrock_max_tokens = int(os.environ['BEDROCK_MAX_TOKENS'])
    bedrock_categorize_top_p = float(os.environ['BEDROCK_CATEGORIZE_TOP_P'])
    categoryBucketName = os.environ['CATEGORY_BUCKET_NAME']
    categories = os.environ['CATEGORIES']
    categoryOutputFormat = os.environ['CATEGORY_OUTPUT_FORMAT']
    embedding_model = os.environ.get('BEDROCK_EMBEDDING_MODEL', 'amazon.titan-embed-text-v2:0')

    if opensearch_skip == 'true':
        print("Skipping getting health events from OpenSearch")
        return {
            'healthEventsTotal': 0,
            'healthEvents': [],
            'ondemand_run_datetime': datetime.now().strftime("%Y%m%d-%H%M%S")
        }

    try:
        region = boto3.Session().region_name
        bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        
        # Check if we should refresh from Health API or use existing OpenSearch data
        refresh_from_api = event.get('refresh_from_api', False)
        
        if refresh_from_api:
            # Get fresh data from Health API and load to OpenSearch
            events, event_details, affected_entities = get_health_events_from_api(region, start_time)
            if events:
                load_to_opensearch(events, event_details, affected_entities, 
                                 opensearch_endpoint, opensearch_index, region, 
                                 bedrock_client, embedding_model)
        
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
