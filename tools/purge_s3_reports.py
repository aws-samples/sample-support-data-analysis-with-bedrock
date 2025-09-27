#!/usr/bin/env python3

import boto3

def purge_bucket():
    # Get account ID and region dynamically
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    
    session = boto3.Session()
    region = session.region_name
    
    bucket_name = f'maki-{account_id}-{region}-report'
    s3 = boto3.client('s3')
    
    # List and delete all objects
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket_name):
        if 'Contents' in page:
            objects = [{'Key': obj['Key']} for obj in page['Contents']]
            s3.delete_objects(Bucket=bucket_name, Delete={'Objects': objects})
            print(f"Deleted {len(objects)} objects")
    
    print(f"Bucket {bucket_name} purged successfully")

if __name__ == "__main__":
    purge_bucket()
