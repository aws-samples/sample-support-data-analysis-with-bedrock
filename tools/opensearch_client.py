#!/usr/bin/env python3

import boto3
import argparse
import sys
import os
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# Add the parent directory to the path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def get_opensearch_query_size():
    """Get current OPENSEARCH_QUERY_SIZE from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-query-size")
        return int(response['Parameter']['Value'])
    except Exception as e:
        print(f"❌ Error getting opensearch-query-size from SSM: {e}")
        sys.exit(1)

def set_opensearch_query_size(size):
    """Set OPENSEARCH_QUERY_SIZE in SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        ssm.put_parameter(
            Name=f"maki-{account_id}-{region}-opensearch-query-size",
            Value=str(size),
            Overwrite=True
        )
        print(f"✅ Updated OPENSEARCH_QUERY_SIZE to {size}")
    except Exception as e:
        print(f"❌ Error setting opensearch-query-size in SSM: {e}")
        sys.exit(1)

def get_opensearch_endpoint_from_collection():
    """Get OpenSearch endpoint from collection name in config"""
    try:
        client = boto3.client('opensearchserverless', region_name=config.REGION)
        response = client.batch_get_collection(names=[config.OPENSEARCH_COLLECTION_NAME])
        
        if not response['collectionDetails']:
            print(f"❌ Collection '{config.OPENSEARCH_COLLECTION_NAME}' not found")
            sys.exit(1)
            
        collection = response['collectionDetails'][0]
        endpoint = collection['collectionEndpoint']
        print(f"✅ Found collection endpoint: {endpoint}")
        return endpoint
        
    except Exception as e:
        print(f"❌ Error getting collection endpoint: {e}")
        sys.exit(1)

def get_opensearch_endpoint():
    """Get current OpenSearch endpoint from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-endpoint")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"❌ Error getting opensearch-endpoint from SSM: {e}")
        sys.exit(1)

def set_opensearch_endpoint(endpoint):
    """Set OpenSearch endpoint in SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        ssm.put_parameter(
            Name=f"maki-{account_id}-{region}-opensearch-endpoint",
            Value=endpoint,
            Overwrite=True
        )
        print(f"✅ Updated OpenSearch endpoint to {endpoint}")
    except Exception as e:
        print(f"❌ Error setting opensearch-endpoint in SSM: {e}")
        sys.exit(1)

def count_records(endpoint, index_name):
    """Count records in OpenSearch index"""
    try:
        region = boto3.Session().region_name
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, region, 'aoss')
        
        host = endpoint.replace('https://', '')
        client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20
        )
        
        response = client.count(index=index_name)
        count = response['count']
        print(f"✅ Records in index '{index_name}': {count}")
        return count
        
    except Exception as e:
        print(f"❌ Error counting records in OpenSearch: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="OpenSearch client tool for MAKI")
    parser.add_argument("--size", type=int, help="Set the OpenSearch query size")
    parser.add_argument("--endpoint", nargs='?', const='auto', help="Set the OpenSearch endpoint URL (auto-detect from collection if no URL provided)")
    parser.add_argument("--count", action="store_true", help="Count records in the OpenSearch index")
    parser.add_argument("--index", default=config.OPENSEARCH_INDEX, help=f"OpenSearch index name (default: {config.OPENSEARCH_INDEX})")
    
    args = parser.parse_args()
    
    # If no arguments provided, show current settings
    if not any([args.size, args.endpoint, args.count]):
        current_size = get_opensearch_query_size()
        current_endpoint = get_opensearch_endpoint()
        print(f"Current OPENSEARCH_QUERY_SIZE: {current_size}")
        print(f"Current OpenSearch endpoint: {current_endpoint}")
        return
    
    # Handle size parameter
    if args.size:
        if args.size <= 0:
            print("❌ Size must be a positive integer")
            sys.exit(1)
        set_opensearch_query_size(args.size)
    
    # Handle endpoint parameter
    if args.endpoint is not None:
        if args.endpoint == 'auto':
            # Auto-detect from collection
            endpoint = get_opensearch_endpoint_from_collection()
        else:
            # Use provided endpoint
            endpoint = args.endpoint
            if not endpoint.startswith('https://'):
                print("❌ Endpoint must start with https://")
                sys.exit(1)
        set_opensearch_endpoint(endpoint)
    
    # Handle count parameter
    if args.count:
        endpoint = get_opensearch_endpoint()
        if endpoint == "placeholder-please-update-with-your-endpoint":
            print("❌ OpenSearch endpoint not configured. Use --endpoint to set it first.")
            sys.exit(1)
        count_records(endpoint, args.index)

if __name__ == "__main__":
    main()
