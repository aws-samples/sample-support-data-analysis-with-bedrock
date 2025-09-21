#!/usr/bin/env python3

import boto3
import json
import argparse
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def load_to_opensearch(events, event_details, affected_entities, opensearch_endpoint, index_name, region, verbose=False):
    """Load health events into OpenSearch index"""
    try:
        host = opensearch_endpoint.replace('https://', '')
        session = boto3.Session()
        credentials = session.get_credentials()
        
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            'es',
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
        
        # Check if index exists
        if not client.indices.exists(index=index_name):
            print(f"Error: Index {index_name} does not exist. Create it first.")
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
                event.update({
                    'eventDescription': detail['event'].get('eventDescription', {}),
                    'affectedEntities': detail.get('affectedEntities', [])
                })
                if verbose:
                    print(f"  Added event description and {len(detail.get('affectedEntities', []))} affected entities")
            
            # Add comprehensive affected entities data
            if event_arn in entities_map:
                event['detailedAffectedEntities'] = entities_map[event_arn]
                if verbose:
                    print(f"  Added {len(entities_map[event_arn])} detailed affected entities")
            
            # Index the event
            client.index(
                index=index_name,
                body=event,
                id=event_arn
            )
            loaded_count += 1
            
            if verbose:
                print(f"  ✓ Loaded into index {index_name}")
                print()
        
        client.indices.refresh(index=index_name)
        print(f"Loaded {loaded_count} health events into OpenSearch index: {index_name}")
        
    except Exception as e:
        print(f"Error loading to OpenSearch: {e}")

def get_health_events(opensearch_endpoint, index_name, region='us-east-1', verbose=False):
    """Query AWS Health API for events from the past year and load into OpenSearch"""
    
    # Calculate date range (past year)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=365)
    
    try:
        # Initialize Health client
        health_client = boto3.client('health', region_name=region)
        
        print(f"Querying AWS Health events from {start_time.date()} to {end_time.date()}")
        
        # Get events - all event types (issue, accountNotification, scheduledChange)
        paginator = health_client.get_paginator('describe_events')
        page_iterator = paginator.paginate(
            filter={
                'startTimes': [
                    {
                        'from': start_time,
                        'to': end_time
                    }
                ],
                'eventTypeCategories': ['issue', 'accountNotification', 'scheduledChange']
            }
        )
        
        events = []
        for page in page_iterator:
            page_events = page['events']
            events.extend(page_events)
            
            if verbose:
                for event in page_events:
                    print(f"Retrieved event: {event['arn']}")
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
                    event_details.extend(batch_details)
                    
                    if verbose:
                        for detail in batch_details:
                            print(f"Retrieved details for: {detail['event']['arn']}")
                    
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
            
            # Load to OpenSearch
            load_to_opensearch(events, event_details, affected_entities, opensearch_endpoint, index_name, region, verbose)
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'SubscriptionRequiredException':
            print("Error: AWS Health API requires Business or Enterprise support plan")
        else:
            print(f"Error querying Health API: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def main():
    parser = argparse.ArgumentParser(description='Query AWS Health API and load events directly into OpenSearch')
    parser.add_argument('--opensearch-endpoint', required=True, help='OpenSearch endpoint URL (required)')
    parser.add_argument('--index-name', required=True, help='OpenSearch index name (required)')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--verbose', action='store_true', help='Show detailed output for each record retrieved and loaded')
    
    args = parser.parse_args()
    
    get_health_events(args.opensearch_endpoint, args.index_name, args.region, args.verbose)

if __name__ == '__main__':
    main()
