#!/usr/bin/env python3

import boto3
import json
import os
import argparse
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def load_to_opensearch(events, event_details, opensearch_endpoint, index_name, region):
    """Load health events into OpenSearch index"""
    if not opensearch_endpoint:
        print("No OpenSearch endpoint provided, skipping index loading")
        return
    
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
            print(f"Index {index_name} does not exist. Create it first.")
            return
        
        # Create a mapping of event ARNs to details
        details_map = {detail['event']['arn']: detail for detail in event_details}
        
        # Load events into OpenSearch
        loaded_count = 0
        for event in events:
            event_arn = event['arn']
            
            # Merge event with its details
            if event_arn in details_map:
                detail = details_map[event_arn]
                event.update({
                    'eventDescription': detail['event'].get('eventDescription', {}),
                    'affectedEntities': detail.get('affectedEntities', [])
                })
            
            # Index the event
            client.index(
                index=index_name,
                body=event,
                id=event_arn
            )
            loaded_count += 1
        
        client.indices.refresh(index=index_name)
        print(f"Loaded {loaded_count} health events into OpenSearch index: {index_name}")
        
    except Exception as e:
        print(f"Error loading to OpenSearch: {e}")

def get_health_events(output_dir, region='us-east-1', opensearch_endpoint=None, index_name='aws-health-events'):
    """Query AWS Health API for events from the past 12 months"""
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Calculate date range (past 12 months)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=365)
    
    try:
        # Initialize Health client
        health_client = boto3.client('health', region_name=region)
        
        print(f"Querying AWS Health events from {start_time.date()} to {end_time.date()}")
        
        # Get events
        paginator = health_client.get_paginator('describe_events')
        page_iterator = paginator.paginate(
            filter={
                'startTimes': [
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
        
        # Write events to JSON file
        output_file = os.path.join(output_dir, f"aws_health_events_{start_time.strftime('%Y%m%d')}_{end_time.strftime('%Y%m%d')}.json")
        
        with open(output_file, 'w') as f:
            json.dump(events, f, indent=2, default=str)
        
        print(f"Health events written to: {output_file}")
        
        # Get event details for each event
        event_details = []
        if events:
            print("Fetching event details...")
            event_arns = [event['arn'] for event in events]
            
            # Process in batches of 10 (API limit)
            for i in range(0, len(event_arns), 10):
                batch = event_arns[i:i+10]
                try:
                    response = health_client.describe_event_details(eventArns=batch)
                    event_details.extend(response['successfulSet'])
                except ClientError as e:
                    print(f"Warning: Could not fetch details for batch {i//10 + 1}: {e}")
            
            # Write event details
            details_file = os.path.join(output_dir, f"aws_health_event_details_{start_time.strftime('%Y%m%d')}_{end_time.strftime('%Y%m%d')}.json")
            with open(details_file, 'w') as f:
                json.dump(event_details, f, indent=2, default=str)
            
            print(f"Event details written to: {details_file}")
            
            # Load to OpenSearch if endpoint provided
            if opensearch_endpoint:
                load_to_opensearch(events, event_details, opensearch_endpoint, index_name, region)
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'SubscriptionRequiredException':
            print("Error: AWS Health API requires Business or Enterprise support plan")
        else:
            print(f"Error querying Health API: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def main():
    parser = argparse.ArgumentParser(description='Query AWS Health API for events from the past 12 months and load into OpenSearch')
    parser.add_argument('--output-dir', required=True, help='Directory to write health events')
    parser.add_argument('--region', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--opensearch-endpoint', help='OpenSearch endpoint URL')
    parser.add_argument('--index-name', default='aws-health-events', help='OpenSearch index name')
    
    args = parser.parse_args()
    
    get_health_events(args.output_dir, args.region, args.opensearch_endpoint, args.index_name)

if __name__ == '__main__':
    main()
