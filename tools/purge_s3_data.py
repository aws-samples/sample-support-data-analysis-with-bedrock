#!/usr/bin/env python3

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
