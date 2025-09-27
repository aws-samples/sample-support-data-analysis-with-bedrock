#!/usr/bin/env python3

import boto3
import argparse
import sys

def get_opensearch_query_size():
    """Get current OPENSEARCH_QUERY_SIZE from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-query-size")
        return int(response['Parameter']['Value'])
    except Exception as e:
        print(f"Error getting opensearch-query-size from SSM: {e}")
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

def main():
    parser = argparse.ArgumentParser(description="Get or set OpenSearch query size parameter")
    parser.add_argument("--size", type=int, help="Set the OpenSearch query size")
    args = parser.parse_args()
    
    if args.size:
        if args.size <= 0:
            print("❌ Size must be a positive integer")
            sys.exit(1)
        set_opensearch_query_size(args.size)
    else:
        current_size = get_opensearch_query_size()
        print(f"Current OPENSEARCH_QUERY_SIZE: {current_size}")

if __name__ == "__main__":
    main()
