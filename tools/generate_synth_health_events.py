#!/usr/bin/env python3
"""
MAKI Synthetic Health Events Generator

This tool generates realistic synthetic AWS Health events and loads them directly into 
OpenSearch Serverless for testing and development purposes. It creates events across 
multiple AWS services with vector embeddings for semantic search capabilities.

Purpose:
- Generate test health events when real AWS Health API data is not available
- Create varied synthetic events across AWS services (EC2, RDS, S3, Lambda, etc.)
- Support testing of health events processing pipeline
- Enable development without requiring Business/Enterprise support for Health API

Event Types Generated:
- Scheduled maintenance events (EC2, RDS, ELB)
- Operational issues across AWS services
- Service degradations and connectivity problems
- Infrastructure upgrades and capacity events

Usage:
    python tools/generate_synth_health_events.py                    # Generate 100 events
    python tools/generate_synth_health_events.py --synth 50        # Generate 50 events
    python tools/generate_synth_health_events.py --verbose         # Show detailed output

Key Features:
- Generates realistic health events with proper AWS ARN structure
- Creates vector embeddings using Bedrock Titan Embed model
- Loads events directly into OpenSearch Serverless collection
- Supports affected entities and detailed event metadata
- Auto-detects OpenSearch endpoint from MAKI configuration
- Provides comprehensive loading statistics and error handling
"""

import boto3
import json
import argparse
import os
import sys
import random
from datetime import datetime, timedelta
from uuid import uuid4

# Add paths for config.py - handle both tools/ and root directory execution
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(current_dir) == 'tools':
    # Running from tools directory
    sys.path.append(os.path.dirname(current_dir))
else:
    # Running from root directory
    sys.path.append(current_dir)

import config
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def generate_embedding(text, bedrock_client, region='us-east-1'):
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
            modelId=config.BEDROCK_EMBEDDING_MODEL,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['embedding']
        
    except ClientError as e:
        if 'AccessDeniedException' in str(e):
            print(f"  Error: Access denied to {config.BEDROCK_EMBEDDING_MODEL} model. Request access at Bedrock console.")
        return None
    except Exception as e:
        print(f"  Error generating embedding: {e}")
        return None

def generate_synthetic_health_events(count=100, start_date=None, end_date=None):
    """Generate synthetic AWS Health events within specified date range"""
    
    # Use real AWS Health API service-to-eventTypeCode mappings from config
    service_event_mapping = config.POPULAR_HEALTH_SERVICES
    categories = ['scheduledChange', 'issue', 'accountNotification', 'investigation']
    statuses = ['open', 'upcoming', 'closed']
    regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1', 'us-east-2']
    
    descriptions = [
        "Scheduled maintenance to improve service reliability and performance.",
        "We are investigating connectivity issues affecting some instances in this region.",
        "Network connectivity issues have been resolved. Service is operating normally.",
        "Planned infrastructure upgrades to enhance system capacity and reliability.",
        "We are experiencing elevated error rates and are working to resolve the issue.",
        "Service degradation has been identified and mitigation is in progress.",
        "Maintenance window completed successfully. All services are operating normally.",
        "We are investigating reports of increased latency in this region."
    ]
    
    events = []
    
    for i in range(count):
        # Generate random timestamps within specified date range
        if start_date and end_date:
            days_diff = (end_date - start_date).days
            random_days = random.randint(0, max(0, days_diff))
            start_time = start_date + timedelta(days=random_days)
        else:
            start_time = datetime.now() - timedelta(days=random.randint(1, 365))
        
        end_time = start_time + timedelta(hours=random.randint(1, 48)) if random.choice([True, False]) else None
        last_updated = start_time + timedelta(minutes=random.randint(0, 120))
        
        service = random.choice(list(service_event_mapping.keys()))
        event_type = random.choice(service_event_mapping[service])
        category = random.choice(categories)
        status = random.choice(statuses)
        region = random.choice(regions)
        
        # Generate unique ARN
        event_id = str(uuid4())
        arn = f"arn:aws:health:{region}::event/{service.lower()}/{event_id}"
        
        # Generate description
        description = random.choice(descriptions)
        
        # Create synthetic event
        event = {
            'arn': arn,
            'service': service,
            'eventTypeCode': event_type,
            'eventTypeCategory': category,
            'region': region,
            'availabilityZone': f"{region}{random.choice(['a', 'b', 'c'])}" if random.choice([True, False]) else None,
            'startTime': start_time,
            'endTime': end_time,
            'lastUpdatedTime': last_updated,
            'statusCode': status,
            'eventScopeCode': random.choice(['PUBLIC', 'ACCOUNT_SPECIFIC', 'NONE']),
            'eventDescription': {
                'latestDescription': description
            },
            'eventMetadata': {
                'service': service,
                'eventTypeCode': event_type,
                'eventTypeCategory': category
            },
            'affectedEntities': [],
            'detailedAffectedEntities': []
        }
        
        # Add some affected entities for certain event types
        if random.choice([True, False]):
            num_entities = random.randint(1, 5)
            for j in range(num_entities):
                entity_id = f"i-{uuid4().hex[:17]}" if service == 'EC2' else f"{service.lower()}-{uuid4().hex[:8]}"
                entity = {
                    'entityArn': f"arn:aws:{service.lower()}:{region}:123456789012:instance/{entity_id}",
                    'eventArn': arn,
                    'entityValue': entity_id,
                    'entityUrl': f"https://console.aws.amazon.com/{service.lower()}/",
                    'awsAccountId': '123456789012',
                    'lastUpdatedTime': last_updated,
                    'statusCode': status
                }
                event['affectedEntities'].append(entity)
                event['detailedAffectedEntities'].append(entity)
        
        events.append(event)
    
    return events

def load_to_opensearch(events, opensearch_endpoint, index_name, region, verbose=False):
    """Load synthetic health events into OpenSearch Serverless index"""
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
        try:
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
                                    "latestDescription": {"type": "text"}
                                }
                            }
                        }
                    }
                }
                client.indices.create(index=index_name, body=index_mapping)
                print(f"✓ Created index: {index_name}")
        except Exception as e:
            print(f"Error creating index {index_name}: {e}")
            return
        
        # Load events into OpenSearch
        loaded_count = 0
        failed_count = 0
        category_counts = {}
        
        for event in events:
            event_arn = event['arn']
            
            if verbose:
                print(f"Loading synthetic event: {event_arn}")
                print(f"  Service: {event.get('service', 'N/A')}")
                print(f"  Event Type: {event.get('eventTypeCode', 'N/A')}")
                print(f"  Status: {event.get('statusCode', 'N/A')}")
                print(f"  Region: {event.get('region', 'N/A')}")
            
            # Generate embedding for description
            latest_desc = event['eventDescription'].get('latestDescription', '')
            if latest_desc:
                embedding = generate_embedding(latest_desc, bedrock_client, region)
                if embedding:
                    event['eventDescription']['latestDescriptionVector'] = embedding
                    if verbose:
                        print(f"  Generated embedding for synthetic event: {event_arn}")
            
            # Index the event
            try:
                client.index(
                    index=index_name,
                    body=event,
                    id=event_arn
                )
                loaded_count += 1
                
                # Count by category
                category = event.get('eventTypeCategory', 'Unknown')
                category_counts[category] = category_counts.get(category, 0) + 1
                
                if verbose:
                    print(f"  ✓ Loaded synthetic event into index {index_name}")
                    print()
            except Exception as e:
                failed_count += 1
                print(f"  ✗ Failed to load synthetic event {event_arn}: {e}")
        
        # Summary report
        print(f"\n=== SYNTHETIC HEALTH EVENTS LOAD SUMMARY ===")
        print(f"Successfully loaded: {loaded_count} synthetic events")
        print(f"Failed to load: {failed_count} synthetic events")
        print(f"Total processed: {loaded_count + failed_count} synthetic events")
        
        if category_counts:
            print(f"\n=== BY EVENT TYPE CATEGORY ===")
            for category, count in sorted(category_counts.items()):
                print(f"{category}: {count} events")
        
        print(f"\nLoaded synthetic health events into OpenSearch index: {index_name}")
        
    except Exception as e:
        print(f"Error loading synthetic events to OpenSearch: {e}")

def get_opensearch_endpoint_from_collection():
    """Get OpenSearch endpoint from the collection specified in config.py"""
    try:
        client = boto3.client('opensearchserverless', region_name=config.REGION)
        response = client.batch_get_collection(names=[config.OPENSEARCH_COLLECTION_NAME])
        
        if response['collectionDetails']:
            collection = response['collectionDetails'][0]
            endpoint = collection['collectionEndpoint']
            print(f"Found OpenSearch collection '{config.OPENSEARCH_COLLECTION_NAME}' with endpoint: {endpoint}")
            return endpoint
        else:
            print(f"OpenSearch collection '{config.OPENSEARCH_COLLECTION_NAME}' not found")
            return None
    except Exception as e:
        print(f"Error getting OpenSearch collection endpoint: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Generate synthetic AWS Health events and load into OpenSearch')
    parser.add_argument('--opensearch-endpoint', help=f'OpenSearch endpoint URL (default: auto-detect from collection {config.OPENSEARCH_COLLECTION_NAME})')
    parser.add_argument('--index-name', default=config.OPENSEARCH_INDEX, help=f'OpenSearch index name (default: {config.OPENSEARCH_INDEX})')
    parser.add_argument('--region', default=config.REGION, help=f'AWS region (default: {config.REGION})')
    parser.add_argument('--verbose', action='store_true', help='Show detailed output for each synthetic event generated and loaded')
    parser.add_argument('--synth', type=int, default=100, help='Number of synthetic health events to generate (default: 100)')
    parser.add_argument('--start-t', help='Start date for health events in YYYYMMDD format (default: 1 year ago)')
    parser.add_argument('--end-t', help='End date for health events in YYYYMMDD format (default: today)')
    
    args = parser.parse_args()
    
    # Parse date parameters
    start_date = None
    end_date = None
    
    if args.start_t:
        try:
            start_date = datetime.strptime(args.start_t, '%Y%m%d')
        except ValueError:
            parser.error('--start-t must be in YYYYMMDD format')
    else:
        start_date = datetime.now() - timedelta(days=365)
    
    if args.end_t:
        try:
            end_date = datetime.strptime(args.end_t, '%Y%m%d')
        except ValueError:
            parser.error('--end-t must be in YYYYMMDD format')
    else:
        end_date = datetime.now()
    
    if start_date > end_date:
        parser.error('--start-t must be before --end-t')
    
    # Get OpenSearch endpoint - either from argument or auto-detect from collection
    opensearch_endpoint = args.opensearch_endpoint
    if not opensearch_endpoint:
        opensearch_endpoint = get_opensearch_endpoint_from_collection()
        if not opensearch_endpoint:
            parser.error(f'Could not auto-detect OpenSearch endpoint from collection {config.OPENSEARCH_COLLECTION_NAME}. Please specify --opensearch-endpoint manually.')
    
    index_name = args.index_name
    
    # Show current identity
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"Current AWS identity: {identity['Arn']}")
    except Exception as e:
        print(f"Could not determine current identity: {e}")
    
    print(f"Generating {args.synth} synthetic AWS Health events between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}...")
    
    # Generate synthetic events
    events = generate_synthetic_health_events(args.synth, start_date, end_date)
    
    print(f"Generated {len(events)} synthetic health events")
    
    # Load to OpenSearch
    load_to_opensearch(events, opensearch_endpoint, index_name, args.region, args.verbose)

if __name__ == '__main__':
    main()
