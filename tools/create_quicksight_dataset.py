#!/usr/bin/env python3
"""
MAKI QuickSight Dataset Creator

Creates a QuickSight dataset from specified S3 URI for MAKI report data analysis.
Supports both cases and health modes with appropriate table schemas.
"""

import boto3
import argparse
import json
import sys
import tempfile
import os

def get_account_id():
    """Get current AWS account ID."""
    sts = boto3.client('sts')
    return sts.get_caller_identity()['Account']

def get_current_region():
    """Get current AWS region."""
    session = boto3.Session()
    return session.region_name

def get_table_schema(mode):
    """Get table schema based on mode (cases or health)."""
    if mode == 'cases':
        return [
            {'Name': 'caseId', 'Type': 'STRING'},
            {'Name': 'displayId', 'Type': 'STRING'},
            {'Name': 'status', 'Type': 'STRING'},
            {'Name': 'serviceCode', 'Type': 'STRING'},
            {'Name': 'timeCreated', 'Type': 'STRING'},
            {'Name': 'timeResolved', 'Type': 'STRING'},
            {'Name': 'submittedBy', 'Type': 'STRING'},
            {'Name': 'category', 'Type': 'STRING'},
            {'Name': 'category_explanation', 'Type': 'STRING'},
            {'Name': 'case_summary', 'Type': 'STRING'},
            {'Name': 'sentiment', 'Type': 'STRING'},
            {'Name': 'suggested_action', 'Type': 'STRING'},
            {'Name': 'suggestion_link', 'Type': 'STRING'}
        ]
    elif mode == 'health':
        return [
            {'Name': 'arn', 'Type': 'STRING'},
            {'Name': 'service', 'Type': 'STRING'},
            {'Name': 'eventTypeCode', 'Type': 'STRING'},
            {'Name': 'eventTypeCategory', 'Type': 'STRING'},
            {'Name': 'region', 'Type': 'STRING'},
            {'Name': 'startTime', 'Type': 'STRING'},
            {'Name': 'lastUpdatedTime', 'Type': 'STRING'},
            {'Name': 'statusCode', 'Type': 'STRING'},
            {'Name': 'eventScopeCode', 'Type': 'STRING'},
            {'Name': 'latestDescription', 'Type': 'STRING'},
            {'Name': 'event_summary', 'Type': 'STRING'},
            {'Name': 'suggestion_action', 'Type': 'STRING'},
            {'Name': 'suggestion_link', 'Type': 'STRING'}
        ]
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'cases' or 'health'")

def find_mode_data_path(bucket_name, mode):
    """Find the appropriate data path in S3 bucket based on mode."""
    s3 = boto3.client('s3')
    
    try:
        # List all objects in the bucket to find data files
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name)
        
        data_files = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    # Look for JSON files that might contain our data
                    if key.endswith('.json') and ('events/' in key or 'batch/' in key):
                        data_files.append(key)
        
        if data_files:
            # Find the most recent batch folder
            batch_folders = set()
            for file_key in data_files:
                if 'batch/' in file_key:
                    batch_part = file_key.split('batch/')[1]
                    if '/' in batch_part:
                        batch_folders.add('batch/' + batch_part.split('/')[0] + '/')
            
            if batch_folders:
                latest_batch = sorted(batch_folders, reverse=True)[0]
                events_path = f"{latest_batch}events/"
                print(f"Found {mode} data in: {events_path}")
                return events_path
        
        print(f"No structured data found, using root path")
        return ""
            
    except Exception as e:
        print(f"Warning: Could not auto-detect data path: {e}")
        return ""

    """Grant read/write permissions to the dataset for the specified user."""
    if not username:
        return
        
    quicksight = boto3.client('quicksight')
    account_id = get_account_id()
    
    try:
        # Get user info to use correct principal format
        user_response = quicksight.describe_user(
            AwsAccountId=account_id,
            Namespace='default',
            UserName=username
        )
        user_arn = user_response['User']['Arn']
        
        quicksight.update_data_set_permissions(
            AwsAccountId=account_id,
            DataSetId=dataset_id,
            GrantPermissions=[
                {
                    'Principal': user_arn,
                    'Actions': [
                        'quicksight:DescribeDataSet',
                        'quicksight:DescribeDataSetPermissions',
                        'quicksight:PassDataSet',
                        'quicksight:DescribeIngestion',
                        'quicksight:ListIngestions',
                        'quicksight:UpdateDataSet',
                        'quicksight:DeleteDataSet',
                        'quicksight:CreateIngestion',
                        'quicksight:CancelIngestion',
                        'quicksight:UpdateDataSetPermissions'
                    ]
                }
            ]
        )
        print(f"Granted permissions to dataset {dataset_id} for user: {username}")
    except Exception as e:
        print(f"Note: Could not grant permissions to dataset {dataset_id} for user {username}: {e}")

    """Grant read/write permissions to the data source for the specified user."""
    if not username:
        return
        
    quicksight = boto3.client('quicksight')
    account_id = get_account_id()
    
    try:
        # Get user info to use correct principal format
        user_response = quicksight.describe_user(
            AwsAccountId=account_id,
            Namespace='default',
            UserName=username
        )
        user_arn = user_response['User']['Arn']
        
        quicksight.update_data_source_permissions(
            AwsAccountId=account_id,
            DataSourceId=data_source_id,
            GrantPermissions=[
                {
                    'Principal': user_arn,
                    'Actions': [
                        'quicksight:DescribeDataSource',
                        'quicksight:DescribeDataSourcePermissions',
                        'quicksight:PassDataSource',
                        'quicksight:UpdateDataSource',
                        'quicksight:DeleteDataSource',
                        'quicksight:UpdateDataSourcePermissions'
                    ]
                }
            ]
        )
        print(f"Granted permissions to data source {data_source_id} for user: {username}")
    except Exception as e:
        print(f"Note: Could not grant permissions to data source {data_source_id} for user {username}: {e}")

def create_manifest_file(bucket_name, data_path, mode, keep_temp=False):
    """Create and upload a temporary manifest file to S3."""
    s3 = boto3.client('s3')
    
    # List actual JSON files in the data path
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=data_path)
        json_files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('.json') and not obj['Key'].endswith('manifest.json'):
                    json_files.append(f"s3://{bucket_name}/{obj['Key']}")
        
        if not json_files:
            print(f"Warning: No JSON files found in {data_path}")
            # Fallback to directory path
            json_files = [f"s3://{bucket_name}/{data_path}"]
    except Exception as e:
        print(f"Error listing files: {e}")
        json_files = [f"s3://{bucket_name}/{data_path}"]
    
    # Create manifest content
    manifest = {
        "fileLocations": [
            {
                "URIs": json_files
            }
        ],
        "globalUploadSettings": {
            "format": "JSON"
        }
    }
    
    # Create temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
        json.dump(manifest, tmp_file, indent=2)
        tmp_file_path = tmp_file.name
    
    try:
        # Upload manifest to S3
        manifest_key = f"{data_path}manifest.json"
        s3.upload_file(tmp_file_path, bucket_name, manifest_key)
        print(f"Created manifest file: s3://{bucket_name}/{manifest_key}")
        print(f"Manifest points to {len(json_files)} JSON files")
        if keep_temp:
            print(f"Temporary manifest kept at: {tmp_file_path}")
        return manifest_key
    finally:
        if not keep_temp:
            os.unlink(tmp_file_path)
    """Check if dataset exists and prompt for overwrite."""
    quicksight = boto3.client('quicksight')
    account_id = get_account_id()
    
    try:
        quicksight.describe_data_set(AwsAccountId=account_id, DataSetId=dataset_id)
        response = input(f"Dataset '{dataset_id}' already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            return False
        # Delete existing dataset
        quicksight.delete_data_set(AwsAccountId=account_id, DataSetId=dataset_id)
        print(f"Deleted existing dataset: {dataset_id}")
        return True
    except quicksight.exceptions.ResourceNotFoundException:
        return True
    except Exception as e:
        print(f"Error checking dataset: {e}")
        return False

def check_dataset_exists(dataset_id):
    """Check if dataset exists and prompt for overwrite."""
    quicksight = boto3.client('quicksight')
    account_id = get_account_id()
    
    try:
        quicksight.describe_data_set(AwsAccountId=account_id, DataSetId=dataset_id)
        response = input(f"Dataset '{dataset_id}' already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            return False
        # Delete existing dataset
        quicksight.delete_data_set(AwsAccountId=account_id, DataSetId=dataset_id)
        print(f"Deleted existing dataset: {dataset_id}")
        return True
    except quicksight.exceptions.ResourceNotFoundException:
        return True
    except Exception as e:
        print(f"Error checking dataset: {e}")
        return False

def grant_permissions_to_user(dataset_id, data_source_id, username):
    """Grant permissions to QuickSight user."""
    if not username:
        return
        
    quicksight = boto3.client('quicksight')
    account_id = get_account_id()
    
    try:
        user_response = quicksight.describe_user(
            AwsAccountId=account_id,
            Namespace='default',
            UserName=username
        )
        user_arn = user_response['User']['Arn']
        
        # Grant dataset permissions - use the full valid permission set
        quicksight.update_data_set_permissions(
            AwsAccountId=account_id,
            DataSetId=dataset_id,
            GrantPermissions=[{
                'Principal': user_arn,
                'Actions': [
                    'quicksight:DescribeDataSet',
                    'quicksight:DescribeDataSetPermissions',
                    'quicksight:PassDataSet',
                    'quicksight:DescribeIngestion',
                    'quicksight:ListIngestions',
                    'quicksight:UpdateDataSet',
                    'quicksight:DeleteDataSet',
                    'quicksight:CreateIngestion',
                    'quicksight:CancelIngestion',
                    'quicksight:UpdateDataSetPermissions'
                ]
            }]
        )
        
        # Grant data source permissions
        quicksight.update_data_source_permissions(
            AwsAccountId=account_id,
            DataSourceId=data_source_id,
            GrantPermissions=[{
                'Principal': user_arn,
                'Actions': [
                    'quicksight:DescribeDataSource',
                    'quicksight:DescribeDataSourcePermissions',
                    'quicksight:PassDataSource',
                    'quicksight:UpdateDataSource',
                    'quicksight:DeleteDataSource',
                    'quicksight:UpdateDataSourcePermissions'
                ]
            }]
        )
        
        print(f"Granted permissions to user: {username}")
        return
    except Exception as e:
        print(f"Could not grant permissions to {username}: {e}")

def create_quicksight_dataset(s3_uri, dataset_name, dataset_id, mode, keep_manifests=False, username=None):
    """Create QuickSight dataset from S3 URI."""
    if not check_dataset_exists(dataset_id):
        print(f"Skipping dataset creation for: {dataset_id}")
        return None
        
    quicksight = boto3.client('quicksight')
    account_id = get_account_id()
    
    # Parse S3 URI and find mode-specific data path
    bucket_name = s3_uri.split('/')[2]
    data_path = find_mode_data_path(bucket_name, mode)
    
    # Create manifest file
    manifest_key = create_manifest_file(bucket_name, data_path, mode, keep_manifests)
    
    # Create data source
    data_source_id = f"{dataset_id}-datasource"
    table_name = f"maki-table-{mode}"
    
    try:
        quicksight.create_data_source(
            AwsAccountId=account_id,
            DataSourceId=data_source_id,
            Name=f"{dataset_name} Data Source",
            Type='S3',
            DataSourceParameters={
                'S3Parameters': {
                    'ManifestFileLocation': {
                        'Bucket': bucket_name,
                        'Key': manifest_key
                    }
                }
            }
        )
        print(f"Created data source: {data_source_id}")
    except quicksight.exceptions.ResourceExistsException:
        print(f"Data source {data_source_id} already exists")
    
    # Create dataset
    try:
        response = quicksight.create_data_set(
            AwsAccountId=account_id,
            DataSetId=dataset_id,
            Name=dataset_name,
            PhysicalTableMap={
                table_name: {
                    'S3Source': {
                        'DataSourceArn': f"arn:aws:quicksight:{get_current_region()}:{account_id}:datasource/{data_source_id}",
                        'InputColumns': get_table_schema(mode)
                    }
                }
            },
            ImportMode='SPICE'
        )
        print(f"Created dataset: {dataset_id} with table: {table_name}")
        if username:
            grant_permissions_to_user(dataset_id, data_source_id, username)
        return response['Arn']
    except quicksight.exceptions.ResourceExistsException:
        print(f"Dataset {dataset_id} already exists")
        return None
    except Exception as e:
        print(f"Dataset creation failed: {e}")
        return None

def create_combined_dataset(s3_uri, dataset_name, dataset_id):
    """Create combined QuickSight dataset with UNION of cases and health data."""
    if not check_dataset_exists(dataset_id):
        print(f"Skipping combined dataset creation for: {dataset_id}")
        return None
        
    print(f"Combined dataset creation requires existing cases and health data sources.")
    print(f"Skipping combined dataset creation until individual datasets are ready.")
    return None
    """Create QuickSight dataset from S3 URI."""
    quicksight = boto3.client('quicksight')
    account_id = get_account_id()
    
    # Parse S3 URI and find mode-specific data path
    bucket_name = s3_uri.split('/')[2]
    data_path = find_mode_data_path(bucket_name, mode)
    
    # Create data source
    data_source_id = f"{dataset_id}-datasource"
    table_name = f"maki-table-{mode}"
    
    try:
        quicksight.create_data_source(
            AwsAccountId=account_id,
            DataSourceId=data_source_id,
            Name=f"{dataset_name} Data Source",
            Type='S3',
            DataSourceParameters={
                'S3Parameters': {
                    'ManifestFileLocation': {
                        'Bucket': bucket_name,
                        'Key': f"{data_path}manifest.json"
                    }
                }
            }
        )
        print(f"Created data source: {data_source_id}")
    except quicksight.exceptions.ResourceExistsException:
        print(f"Data source {data_source_id} already exists")
    
    # Create dataset
    try:
        response = quicksight.create_data_set(
            AwsAccountId=account_id,
            DataSetId=dataset_id,
            Name=dataset_name,
            PhysicalTableMap={
                table_name: {
                    'S3Source': {
                        'DataSourceArn': f"arn:aws:quicksight:{get_current_region()}:{account_id}:datasource/{data_source_id}",
                        'InputColumns': get_table_schema(mode)
                    }
                }
            },
            ImportMode='SPICE'
        )
        print(f"Created dataset: {dataset_id} with table: {table_name} using data from: s3://{bucket_name}/{data_path}")
        return response['Arn']
    except quicksight.exceptions.ResourceExistsException:
        print(f"Dataset {dataset_id} already exists")
        return None

def main():
    parser = argparse.ArgumentParser(description='Create QuickSight dataset from S3 URI')
    
    # Default S3 URI
    account_id = get_account_id()
    region = get_current_region()
    default_s3_uri = f"s3://maki-{account_id}-{region}-report"
    
    parser.add_argument('--s3-uri', default=default_s3_uri,
                       help=f'S3 URI for dataset (default: {default_s3_uri})')
    parser.add_argument('--dataset-name', default='MAKI Report Dataset',
                       help='Name for the QuickSight dataset')
    parser.add_argument('--dataset-id', default='maki-report-dataset',
                       help='ID for the QuickSight dataset')
    parser.add_argument('--mode', choices=['cases', 'health'], 
                       help='Mode for dataset creation: cases, health, or omit to create all datasets')
    parser.add_argument('--keep-manifests', action='store_true',
                       help='Keep temporary manifest files in /tmp directory')
    parser.add_argument('--user', type=str,
                       help='QuickSight username to grant read/write access to all created resources')
    
    args = parser.parse_args()
    
    if args.mode:
        # Create single dataset for specified mode
        if args.dataset_name == 'MAKI Report Dataset':
            args.dataset_name = f'MAKI {args.mode.title()} Dataset'
        if args.dataset_id == 'maki-report-dataset':
            args.dataset_id = f'maki-{args.mode}-dataset'
        
        print(f"Creating QuickSight dataset for {args.mode} mode from: {args.s3_uri}")
        print(f"Auto-discovering {args.mode} data in bucket...")
        
        try:
            dataset_arn = create_quicksight_dataset(args.s3_uri, args.dataset_name, args.dataset_id, args.mode, args.keep_manifests, args.user)
            if dataset_arn:
                print(f"Successfully created dataset: {dataset_arn}")
            else:
                print("Dataset creation completed (may already exist)")
        except Exception as e:
            print(f"Error creating dataset: {e}")
            sys.exit(1)
    else:
        # Create all three datasets
        print(f"Creating all QuickSight datasets from: {args.s3_uri}")
        
        datasets = [
            ('cases', 'MAKI Cases Dataset', 'maki-cases-dataset'),
            ('health', 'MAKI Health Dataset', 'maki-health-dataset'),
            ('combined', 'MAKI All Dataset', 'maki-all-dataset')
        ]
        
        for mode, name, dataset_id in datasets:
            try:
                if mode == 'combined':
                    dataset_arn = create_combined_dataset(args.s3_uri, name, dataset_id)
                else:
                    dataset_arn = create_quicksight_dataset(args.s3_uri, name, dataset_id, mode, args.keep_manifests, args.user)
                
                if dataset_arn:
                    print(f"Successfully created {mode} dataset: {dataset_arn}")
                else:
                    print(f"{mode.title()} dataset creation completed (may already exist)")
            except Exception as e:
                print(f"Error creating {mode} dataset: {e}")
                continue

if __name__ == '__main__':
    main()
