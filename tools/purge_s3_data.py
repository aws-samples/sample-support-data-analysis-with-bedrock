#!/usr/bin/env python3
"""
MAKI S3 Data Purge Utility

This tool cleans all MAKI S3 buckets by deleting their contents while preserving the 
bucket structure. It's essential for test preparation and ensuring clean execution 
environments between different test scenarios.

Purpose:
- Clean all MAKI S3 buckets before test execution
- Remove previous processing results and generated data
- Ensure consistent starting state for test scenarios
- Prevent interference between different test runs

Buckets Purged:
- maki-{account}-{region}-archive: Archived processing data
- maki-{account}-{region}-batches: Batch inference job data
- maki-{account}-{region}-cases-agg: Support cases aggregation data
- maki-{account}-{region}-health-agg: Health events aggregation data
- maki-{account}-{region}-llm-output: LLM processing outputs
- maki-{account}-{region}-report: Final analysis reports

Usage:
    python tools/purge_s3_data.py

Key Features:
- Automatic AWS account ID and region detection
- Batch deletion for efficient processing
- Comprehensive error handling and reporting
- Preserves bucket structure while removing all objects
- Used by all test scenarios to ensure clean starting state
"""

import boto3

def purge_buckets():
    # Get account ID and region dynamically
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    
    session = boto3.Session()
    region = session.region_name
    
    # Define bucket suffixes
    bucket_suffixes = ['archive', 'batches', 'cases-agg', 'health-agg', 'llm-output', 'report']
    
    s3 = boto3.client('s3')
    
    for suffix in bucket_suffixes:
        bucket_name = f'maki-{account_id}-{region}-{suffix}'
        
        try:
            # List and delete all objects
            paginator = s3.get_paginator('list_objects_v2')
            total_deleted = 0
            
            for page in paginator.paginate(Bucket=bucket_name):
                if 'Contents' in page:
                    objects = [{'Key': obj['Key']} for obj in page['Contents']]
                    s3.delete_objects(Bucket=bucket_name, Delete={'Objects': objects})
                    total_deleted += len(objects)
            
            print(f"Bucket {bucket_name}: deleted {total_deleted} objects")
            
        except Exception as e:
            print(f"Error purging bucket {bucket_name}: {e}")

if __name__ == "__main__":
    purge_buckets()
