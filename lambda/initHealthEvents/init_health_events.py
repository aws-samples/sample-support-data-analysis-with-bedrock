#!/usr/bin/env python3
"""
Lambda function to initialize health events data in OpenSearch after collection creation.
This function creates the amazon-health-events index and loads health events data.
"""

import json
import os
import sys
import subprocess
import boto3
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def generate_embedding(text, bedrock_client, region='us-east-1'):
    """Generate embedding using Bedrock model"""
    if not text or not text.strip():
        return None
    
    try:
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })
        
        response = bedrock_client.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['embedding']
        
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return None

def create_index_and_load_data(opensearch_endpoint, index_name, region):
    """Create OpenSearch index and load health events data"""
    try:
        host = opensearch_endpoint.replace('https://', '')
        session = boto3.Session()
        credentials = session.get_credentials()
        
        # Initialize Bedrock client for embeddings
        bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        
        # Use 'aoss' service for OpenSearch Serverless
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            'aoss',
            session_token=credentials.token
        )
        
        client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30
        )
        
        # Create index if it doesn't exist
        if not client.indices.exists(index=index_name):
            print(f"Creating index: {index_name}")
            index_mapping = {
                "mappings": {
                    "properties": {
                        "arn": {"type": "keyword"},
                        "service": {"type": "keyword"},
                        "eventTypeCode": {"type": "keyword"},
                        "eventTypeCategory": {"type": "keyword"},
                        "statusCode": {"type": "keyword"},
                        "region": {"type": "keyword"},
                        "startTime": {"type": "date"},
                        "endTime": {"type": "date"},
                        "lastUpdatedTime": {"type": "date"},
                        "eventDescription": {
                            "properties": {
                                "latestDescription": {"type": "text"},
                                "latestDescriptionVector": {
                                    "type": "knn_vector",
                                    "dimension": 1024,
                                    "method": {
                                        "name": "hnsw",
                                        "space_type": "cosinesimil",
                                        "engine": "nmslib"
                                    }
                                }
                            }
                        }
                    }
                }
            }
            client.indices.create(index=index_name, body=index_mapping)
            print(f"✓ Created index: {index_name}")
        else:
            print(f"Index {index_name} already exists")
        
        # Load health events data
        print("Loading health events data...")
        load_health_events(client, index_name, bedrock_client, region)
        
        return True
        
    except Exception as e:
        print(f"Error creating index and loading data: {e}")
        return False

def load_health_events(client, index_name, bedrock_client, region):
    """Load health events from AWS Health API"""
    try:
        # Initialize Health client
        health_client = boto3.client('health', region_name=region)
        
        # Calculate date range (past year)
        end_time = datetime.now()
        start_time = end_time - timedelta(days=365)
        
        print(f"Querying AWS Health events from {start_time.date()} to {end_time.date()}")
        
        # Get events
        paginator = health_client.get_paginator('describe_events')
        page_iterator = paginator.paginate(
            filter={
                'lastUpdatedTimes': [
                    {
                        'from': start_time,
                        'to': end_time
                    }
                ]
            }
        )
        
        events = []
        for page in page_iterator:
            events.extend(page['events'])
        
        print(f"Found {len(events)} health events")
        
        if not events:
            print("No health events found")
            return
        
        # Get event details
        event_details = []
        event_arns = [event['arn'] for event in events]
        
        # Process in batches of 10 (API limit)
        for i in range(0, len(event_arns), 10):
            batch = event_arns[i:i+10]
            try:
                response = health_client.describe_event_details(eventArns=batch)
                event_details.extend(response['successfulSet'])
            except ClientError as e:
                print(f"Warning: Could not fetch details for batch {i//10 + 1}: {e}")
        
        # Create mappings
        details_map = {detail['event']['arn']: detail for detail in event_details}
        
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
                        embedding = generate_embedding(latest_desc, bedrock_client, region)
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
            
            # Index the event
            try:
                client.index(
                    index=index_name,
                    body=event,
                    id=event_arn
                )
                loaded_count += 1
            except Exception as e:
                print(f"Failed to load event {event_arn}: {e}")
        
        print(f"Successfully loaded {loaded_count} events into index {index_name}")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'SubscriptionRequiredException':
            print("Warning: AWS Health API requires Business or Enterprise support plan")
        else:
            print(f"Error querying Health API: {e}")
    except Exception as e:
        print(f"Error loading health events: {e}")

def handler(event, context):
    """Lambda handler function"""
    try:
        print(f"Received event: {json.dumps(event)}")
        
        # Get configuration from environment variables
        opensearch_endpoint = os.environ.get('OPENSEARCH_ENDPOINT')
        index_name = os.environ.get('INDEX_NAME', 'amazon-health-events')
        region = os.environ.get('REGION', 'us-east-1')
        
        if not opensearch_endpoint:
            return {
                'statusCode': 400,
                'body': json.dumps('Missing OPENSEARCH_ENDPOINT environment variable')
            }
        
        print(f"Initializing health events data...")
        print(f"OpenSearch endpoint: {opensearch_endpoint}")
        print(f"Index name: {index_name}")
        print(f"Region: {region}")
        
        success = create_index_and_load_data(opensearch_endpoint, index_name, region)
        
        if success:
            return {
                'statusCode': 200,
                'body': json.dumps('Health events data initialized successfully')
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to initialize health events data')
            }
            
    except Exception as e:
        print(f"Error in handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
