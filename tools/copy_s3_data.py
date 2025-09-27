#!/usr/bin/env python3

import boto3
import sys

def get_account_id():
    """Get current AWS account ID"""
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']

def get_region():
    """Get current AWS region"""
    session = boto3.Session()
    return session.region_name

def ensure_bucket_exists(bucket_name):
    """Create bucket if it doesn't exist"""
    s3 = boto3.client('s3')
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"✅ Bucket {bucket_name} already exists")
    except:
        try:
            s3.create_bucket(Bucket=bucket_name)
            print(f"✅ Created bucket {bucket_name}")
        except Exception as e:
            print(f"❌ Error creating bucket {bucket_name}: {e}")
            return False
    return True

def copy_s3_objects(source_bucket, dest_bucket):
    s3 = boto3.client('s3')
    
    try:
        # List all objects in source bucket
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=source_bucket)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    copy_source = {'Bucket': source_bucket, 'Key': key}
                    
                    print(f"Copying {key}...")
                    s3.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=key)
        
        print(f"✅ Copy completed from {source_bucket} to {dest_bucket}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ['to-temp', 'from-temp']:
        print("Usage: python copy_s3_data.py [to-temp|from-temp]")
        sys.exit(1)
    
    direction = sys.argv[1]
    
    # Get dynamic bucket names
    account_id = get_account_id()
    region = get_region()
    cases_bucket = f'maki-{account_id}-{region}-cases-agg'
    temp_bucket = 'maki-temp'
    
    # Ensure temp bucket exists
    if not ensure_bucket_exists(temp_bucket):
        sys.exit(1)
    
    if direction == 'to-temp':
        source = cases_bucket
        dest = temp_bucket
    else:  # from-temp
        source = temp_bucket
        dest = cases_bucket
    
    print(f"🚀 Copying from s3://{source} to s3://{dest}")
    copy_s3_objects(source, dest)
