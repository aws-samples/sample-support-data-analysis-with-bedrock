#!/usr/bin/env python3

import boto3
import json
import argparse
import os
import sys

# Add paths for config.py - handle both tools/ and root directory execution
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(current_dir) == 'tools':
    # Running from tools directory
    sys.path.append(os.path.dirname(current_dir))
else:
    # Running from root directory
    sys.path.append(current_dir)

import config
from datetime import datetime, timedelta
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

def write_to_files(events, event_details, affected_entities, output_dir, verbose=False):
    """Write health events to JSON files in specified directory"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize Bedrock client for embeddings
        bedrock_client = boto3.client('bedrock-runtime', region_name=config.REGION)
        
        # Create mappings
        details_map = {detail['event']['arn']: detail for detail in event_details}
        entities_map = {}
        for entity in affected_entities:
            event_arn = entity['eventArn']
            if event_arn not in entities_map:
                entities_map[event_arn] = []
            entities_map[event_arn].append(entity)
        
        # Process and write each event
        written_count = 0
        for event in events:
            event_arn = event['arn']
            
            # Merge event with its details
            if event_arn in details_map:
                detail = details_map[event_arn]
                
                # Start with the detailed event data and merge with original
                detailed_event = detail['event'].copy()
                detailed_event.update(event)  # Add any fields from describe_events that aren't in details
                event.clear()
                event.update(detailed_event)
                
                # Add the additional fields from describe_event_details
                if 'eventDescription' in detail:
                    event['eventDescription'] = detail['eventDescription']
                    
                    # Generate embedding for latestDescription
                    latest_desc = detail['eventDescription'].get('latestDescription', '')
                    if latest_desc:
                        embedding = generate_embedding(latest_desc, bedrock_client)
                        if embedding:
                            event['eventDescription']['latestDescriptionVector'] = embedding
                            if verbose:
                                print(f"  Generated embedding for event: {event_arn}")
                
                if 'eventMetadata' in detail:
                    event['eventMetadata'] = detail['eventMetadata']
                event['affectedEntities'] = detail.get('affectedEntities', [])
                
                if verbose:
                    latest_desc = event['eventDescription'].get('latestDescription', '')
                    print(f"  Added event description: {'YES' if latest_desc else 'NO (empty)'}")
                    print(f"  Description length: {len(latest_desc) if latest_desc else 0}")
                    print(f"  Added {len(event['affectedEntities'])} affected entities")
                    print(f"  Full describe_event_details output: {json.dumps(detail, indent=2, default=str)}")
            else:
                event.update({
                    'eventDescription': {},
                    'affectedEntities': []
                })
            
            # Add detailed affected entities
            if event_arn in entities_map:
                event['detailedAffectedEntities'] = entities_map[event_arn]
            
            # Write to file
            filename = f"{event_arn.replace(':', '_').replace('/', '_')}.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(event, f, indent=2, default=str)
            
            written_count += 1
            
            if verbose:
                print(f"Written event to: {filepath}")
        
        print(f"Written {written_count} health events to directory: {output_dir}")
        
    except Exception as e:
        print(f"Error writing to files: {e}")

def load_to_opensearch(events, event_details, affected_entities, opensearch_endpoint, index_name, region, verbose=False):
    """Load health events into OpenSearch Serverless index"""
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
            
            # Get current user/role ARN for troubleshooting
            try:
                sts = boto3.client('sts')
                identity = sts.get_caller_identity()
                current_arn = identity['Arn']
                print(f"Current identity: {current_arn}")
            except:
                print("Could not determine current identity")
            
            print("Please ensure the current user/role has the necessary permissions for OpenSearch Serverless:")
            print("- aoss:CreateIndex")
            print("- aoss:WriteDocument") 
            print("- aoss:UpdateIndex")
            print("Add this ARN to the OpenSearch Serverless collection's access policy.")
            return
        
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
        failed_count = 0
        category_counts = {}
        
        for event in events:
            event_arn = event['arn']
            
            if verbose:
                print(f"Loading event: {event_arn}")
                print(f"  Service: {event.get('service', 'N/A')}")
                print(f"  Event Type: {event.get('eventTypeCode', 'N/A')}")
                print(f"  Status: {event.get('statusCode', 'N/A')}")
                print(f"  Region: {event.get('region', 'N/A')}")
            
            # Merge event with its details
            if event_arn in details_map:
                detail = details_map[event_arn]
                
                # Start with the detailed event data and merge with original
                detailed_event = detail['event'].copy()
                detailed_event.update(event)  # Add any fields from describe_events that aren't in details
                event.clear()
                event.update(detailed_event)
                
                # Add the additional fields from describe_event_details
                if 'eventDescription' in detail:
                    event['eventDescription'] = detail['eventDescription']
                    
                    # Generate embedding for latestDescription
                    latest_desc = detail['eventDescription'].get('latestDescription', '')
                    if latest_desc:
                        embedding = generate_embedding(latest_desc, bedrock_client, region)
                        if embedding:
                            event['eventDescription']['latestDescriptionVector'] = embedding
                            if verbose:
                                print(f"  Generated embedding for event: {event_arn}")
                
                if 'eventMetadata' in detail:
                    event['eventMetadata'] = detail['eventMetadata']
                event['affectedEntities'] = detail.get('affectedEntities', [])
                
                if verbose:
                    latest_desc = event.get('eventDescription', {}).get('latestDescription', '')
                    vector = event.get('eventDescription', {}).get('latestDescriptionVector', [])
                    print(f"  Added event description: {'YES' if latest_desc else 'NO (empty)'}")
                    print(f"  Description length: {len(latest_desc) if latest_desc else 0}")
                    print(f"  Vector embedding: {'YES' if vector else 'NO'}")
                    if vector:
                        print(f"  Vector dimensions: {len(vector)}")
                        print(f"  Vector sample (first 5): {vector[:5]}")
                    print(f"  Added {len(event.get('affectedEntities', []))} affected entities")
                    
                    # Create a copy of detail for printing with truncated vector
                    detail_for_print = json.loads(json.dumps(detail, default=str))
                    if 'eventDescription' in detail_for_print and 'latestDescriptionVector' in detail_for_print['eventDescription']:
                        full_vector = detail_for_print['eventDescription']['latestDescriptionVector']
                        detail_for_print['eventDescription']['latestDescriptionVector'] = full_vector[:5] + [f"... ({len(full_vector)-5} more values)"] if len(full_vector) > 5 else full_vector
                    
                    print(f"  Full describe_event_details output: {json.dumps(detail_for_print, indent=2, default=str)}")
            else:
                if verbose:
                    print(f"  No details found for event: {event_arn}")
                # Add empty structures to maintain consistency
                event.update({
                    'eventDescription': {},
                    'affectedEntities': []
                })
            
            # Add comprehensive affected entities data
            if event_arn in entities_map:
                event['detailedAffectedEntities'] = entities_map[event_arn]
                if verbose:
                    print(f"  Added {len(entities_map[event_arn])} detailed affected entities")
            
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
                    print(f"  ✓ Loaded into index {index_name}")
                    print()
            except Exception as e:
                failed_count += 1
                print(f"  ✗ Failed to load event {event_arn}: {e}")
        
        # Summary report
        print(f"\n=== LOAD SUMMARY ===")
        print(f"Successfully loaded: {loaded_count} events")
        print(f"Failed to load: {failed_count} events")
        print(f"Total processed: {loaded_count + failed_count} events")
        
        if category_counts:
            print(f"\n=== BY EVENT TYPE CATEGORY ===")
            for category, count in sorted(category_counts.items()):
                print(f"{category}: {count} events")
        
        print(f"\nLoaded into OpenSearch index: {index_name}")
        
    except Exception as e:
        print(f"Error loading to OpenSearch: {e}")

def get_health_events(opensearch_endpoint, index_name, region=config.REGION, verbose=False, output_dir=None):
    """Query AWS Health API for events from the past year and load into OpenSearch"""
    
    # Show current identity
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"Current AWS identity: {identity['Arn']}")
    except Exception as e:
        print(f"Could not determine current identity: {e}")
    
    # Calculate date range (past year)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=365)
    
    try:
        # Initialize Health client
        health_client = boto3.client('health', region_name=region)
        
        print(f"Querying AWS Health events received from {start_time.date()} to {end_time.date()}")
        
        # Get events - all event types including planned lifecycle events
        # Filter by lastUpdatedTime to get events received in the past year
        paginator = health_client.get_paginator('describe_events')
        
        # Get events received in the past year
        page_iterator_received = paginator.paginate(
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
        for page in page_iterator_received:
            page_events = page['events']
            events.extend(page_events)
            
            if verbose:
                for event in page_events:
                    print(f"Retrieved event (received): {event['arn']}")
                    print(f"  Service: {event.get('service', 'N/A')}")
                    print(f"  Event Type: {event.get('eventTypeCode', 'N/A')}")
                    print(f"  Category: {event.get('eventTypeCategory', 'N/A')}")
                    print(f"  Status: {event.get('statusCode', 'N/A')}")
                    print(f"  Region: {event.get('region', 'N/A')}")
                    print(f"  Start Time: {event.get('startTime', 'N/A')}")
                    print()
        
        # Also get future events that haven't started yet but were received
        future_start_time = end_time
        future_end_time = end_time + timedelta(days=365)  # Next year
        
        page_iterator_future = paginator.paginate(
            filter={
                'startTimes': [
                    {
                        'from': future_start_time,
                        'to': future_end_time
                    }
                ],
                'lastUpdatedTimes': [
                    {
                        'from': start_time,
                        'to': end_time
                    }
                ]
            }
        )
        
        for page in page_iterator_future:
            page_events = page['events']
            # Avoid duplicates by checking ARNs
            existing_arns = {event['arn'] for event in events}
            new_events = [event for event in page_events if event['arn'] not in existing_arns]
            events.extend(new_events)
            
            if verbose:
                for event in new_events:
                    print(f"Retrieved event (future): {event['arn']}")
                    print(f"  Service: {event.get('service', 'N/A')}")
                    print(f"  Event Type: {event.get('eventTypeCode', 'N/A')}")
                    print(f"  Category: {event.get('eventTypeCategory', 'N/A')}")
                    print(f"  Status: {event.get('statusCode', 'N/A')}")
                    print(f"  Region: {event.get('region', 'N/A')}")
                    print(f"  Start Time: {event.get('startTime', 'N/A')}")
                    print()
        
        print(f"Found {len(events)} health events")
        
        # Get event details for each event
        event_details = []
        affected_entities = []
        if events:
            print("Fetching event details...")
            event_arns = [event['arn'] for event in events]
            
            # Process in batches of 10 (API limit)
            for i in range(0, len(event_arns), 10):
                batch = event_arns[i:i+10]
                try:
                    # Get detailed event information
                    response = health_client.describe_event_details(eventArns=batch)
                    batch_details = response['successfulSet']
                    failed_details = response.get('failedSet', [])
                    
                    event_details.extend(batch_details)
                    
                    if verbose:
                        for detail in batch_details:
                            event_desc = detail['event'].get('eventDescription', {})
                            latest_desc = event_desc.get('latestDescription', '')
                            print(f"Retrieved details for: {detail['event']['arn']}")
                            print(f"  Has description: {'YES' if latest_desc else 'NO'}")
                            if latest_desc:
                                print(f"  Description: {latest_desc}")
                            else:
                                print(f"  Description: (empty)")
                        
                        for failed in failed_details:
                            print(f"Failed to get details for: {failed.get('eventArn', 'Unknown')}")
                            print(f"  Error: {failed.get('errorName', 'Unknown')} - {failed.get('errorMessage', 'No message')}")
                    
                    if failed_details:
                        print(f"Warning: Failed to get details for {len(failed_details)} events in batch {i//10 + 1}")
                    
                    # Get affected entities for each event
                    for event_arn in batch:
                        try:
                            entities_response = health_client.describe_affected_entities(
                                filter={'eventArns': [event_arn]}
                            )
                            batch_entities = entities_response['entities']
                            for entity in batch_entities:
                                entity['eventArn'] = event_arn  # Link entity to event
                                affected_entities.append(entity)
                            
                            if verbose and batch_entities:
                                print(f"Retrieved {len(batch_entities)} affected entities for: {event_arn}")
                                
                        except ClientError as entity_error:
                            print(f"Warning: Could not fetch entities for {event_arn}: {entity_error}")
                            
                except ClientError as e:
                    print(f"Warning: Could not fetch details for batch {i//10 + 1}: {e}")
            
            print(f"Fetched details for {len(event_details)} events and {len(affected_entities)} affected entities")
            
            # Output to files or load to OpenSearch
            if output_dir:
                write_to_files(events, event_details, affected_entities, output_dir, verbose)
            else:
                load_to_opensearch(events, event_details, affected_entities, opensearch_endpoint, index_name, region, verbose)
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'SubscriptionRequiredException':
            print("Error: AWS Health API requires Business or Enterprise support plan")
        else:
            print(f"Error querying Health API: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

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
    parser = argparse.ArgumentParser(description='Query AWS Health API and load events directly into OpenSearch')
    parser.add_argument('--opensearch-endpoint', help=f'OpenSearch endpoint URL (default: auto-detect from collection {config.OPENSEARCH_COLLECTION_NAME})')
    parser.add_argument('--index-name', default=config.OPENSEARCH_INDEX, help=f'OpenSearch index name (default: {config.OPENSEARCH_INDEX})')
    parser.add_argument('--region', default=config.REGION, help=f'AWS region (default: {config.REGION})')
    parser.add_argument('--verbose', action='store_true', help='Show detailed output for each record retrieved and loaded')
    parser.add_argument('--output-dir', help='Write JSON files to directory instead of loading to OpenSearch')
    
    args = parser.parse_args()
    
    # Get OpenSearch endpoint - either from argument or auto-detect from collection
    opensearch_endpoint = args.opensearch_endpoint
    if not opensearch_endpoint and not args.output_dir:
        opensearch_endpoint = get_opensearch_endpoint_from_collection()
        if not opensearch_endpoint:
            parser.error(f'Could not auto-detect OpenSearch endpoint from collection {config.OPENSEARCH_COLLECTION_NAME}. Please specify --opensearch-endpoint manually.')
    
    index_name = args.index_name
    
    # Validate required arguments based on mode
    if not args.output_dir and (not opensearch_endpoint or not index_name):
        parser.error('--opensearch-endpoint and --index-name are required unless --output-dir is specified')
    
    get_health_events(opensearch_endpoint, index_name, args.region, args.verbose, args.output_dir)

if __name__ == '__main__':
    main()
