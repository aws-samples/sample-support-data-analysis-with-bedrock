# gets files from s3
import boto3
from botocore.exceptions import ClientError
import os
import logging
from json_file_utils import isJsonFile, reformatJson

def empty_s3_bucket(bucket_name):
    """
    Deletes all contents of an S3 bucket.
    
    Args:
        bucket_name (str): Name of the bucket to empty
    """
    parts = bucket_name.rstrip('/').split('/')
    
    # Handle s3:// prefix
    if parts[0] == 's3:' and parts[1] == '':
        bucket_name = parts[2]

    try:
        s3 = boto3.client('s3')
        paginator = s3.get_paginator('list_objects_v2')
        
        # Iterate through all objects and delete them
        for page in paginator.paginate(Bucket=bucket_name):
            if 'Contents' in page:
                objects_to_delete = [{'Key': obj['Key']} for obj in page['Contents']]
                
                s3.delete_objects(
                    Bucket=bucket_name,
                    Delete={
                        'Objects': objects_to_delete,
                        'Quiet': True
                    }
                )
                
        print(f"Successfully emptied bucket: {bucket_name}")
        
    except ClientError as e:
        print(f"Error emptying bucket {bucket_name}: {e}")
        raise

def list_bucket_objects(bucket_name):
    print(f'Listing objects in bucket {bucket_name}')
    s3 = boto3.client('s3')
    try:
        response = s3.list_objects_v2(Bucket=bucket_name)
        contents = response['Contents']
    except ClientError as e:
        print(f'Could not list objects in bucket {bucket_name}')
        raise e
    return contents

def list_bucket_object_keys(bucket_name, prefix=None):
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    if prefix:
        return [obj.key for obj in bucket.objects.filter(Prefix=prefix)]
    return [obj.key for obj in bucket.objects.all()]

def get_category_desc(bucket_name,category):
    output = ''
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    for obj in bucket.objects.all():
        key = obj.key
        if (key.startswith(category)):
            if key.endswith('.txt'):
                body = obj.get()['Body'].read()
                output += key + '\n'
                output += body.decode('utf-8')
                output += '\n\n'
    return output

def get_category_examples(bucket_name, category):
    output = ''
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    for obj in bucket.objects.all():
        key = obj.key
        if (key.startswith(category)):
            if (key.endswith('.jsonl')):
                body = obj.get()['Body'].read()
                output += key + '\n'
                output += body.decode('utf-8')
                output += '\n\n'
            
    return output

def get_s3_obj_body(bucket_name, object_key, decode):
    s3_client = boto3.client('s3')
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        # Read the body and decode it if it's text content
        if (decode):
            return response['Body'].read().decode('utf-8')
        else:
            return response['Body'].read()
    except ClientError as e:
        print(f"Error getting object {object_key} from bucket {bucket_name}: {e}")
        raise

def store_data(data, bucket_name, object_key):
    s3_client = boto3.client('s3')
    try:
        if data is None:
            print(f"Error: Cannot store None data to {bucket_name}/{object_key}")
            return False
            
        if isJsonFile(object_key):
            data = reformatJson(data)
            if data is None:
                print(f"Error: JSON formatting failed for {object_key}")
                return False

        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=data
        )
        print(f"Successfully uploaded data to {bucket_name}/{object_key}")
        return True
    except ClientError as e:
        print(e)
        return False

def upload_directory_to_s3(local_directory, bucket_name, s3_prefix=""):
    """
    Upload a local directory to S3 bucket
    
    Args:
        local_directory (str): Path to the local directory
        bucket_name (str): Name of the S3 bucket
        s3_prefix (str): Prefix (folder path) to use in S3 bucket
    """
    
    try:
        s3_client = boto3.client('s3')
        
        # Validate local directory exists
        if not os.path.exists(local_directory):
            raise ValueError(f"Local directory '{local_directory}' does not exist")

        # Walk through the local directory
        for root, dirs, files in os.walk(local_directory):
            for filename in files:
                # Get the full local path
                local_path = os.path.join(root, filename)
                
                # Calculate relative path for S3 key
                relative_path = os.path.relpath(local_path, local_directory)
                
                # Construct S3 key with prefix
                s3_key = os.path.join(s3_prefix, relative_path).replace("\\", "/")
                
                try:
                    print(f"Uploading {local_path} to {bucket_name}/{s3_key}")
                    s3_client.upload_file(local_path, bucket_name, s3_key)
                except Exception as e:
                    logging.warning(f"Failed to upload {local_path}: {str(e)}")
                    raise

        print(f"Successfully uploaded directory '{local_directory}' to '{bucket_name}/{s3_prefix}'")
        
    except Exception as e:
        logging.warning(f"Error uploading directory to S3: {str(e)}")
        raise



# use this to get the cases from CID 
# defaults to finding jsonl files
def find_files_in_s3(bucket_name, prefix='', file_ext='.jsonl', recursive=True):

    try:
        s3_client = boto3.client('s3')
        files = []
        
        # Configure the paginator
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(
            Bucket=bucket_name,
            Prefix=prefix
        )

        # Iterate through all pages
        for page in page_iterator:
            if 'Contents' not in page:
                logging.warning(f"No contents found in bucket '{bucket_name}' with prefix '{prefix}'")
                return []

            # Check each object
            for obj in page['Contents']:
                key = obj['Key']
                
                # file_ext, e.g,  '.jsonl' or '.json'
                if key.lower().endswith(file_ext):
                    files.append({
                        'Key': key,
                        'Size': obj['Size'],
                        'LastModified': obj['LastModified']
                    })

        return files

    except ClientError as e:
        logging.warning(f"AWS Error: {str(e)}")
        raise
    except Exception as e:
        logging.warning(f"Error: {str(e)}")
        raise

def extract_bucket_name(s3_uri):
    """
    Extracts bucket name from an S3 URI.
    
    Args:
        s3_uri (str): S3 URI in the format 's3://bucket-name/path/to/files/'
        
    Returns:
        str: Bucket name
        
    Raises:
        ValueError: If the S3 URI format is invalid
    """
    try:
        # Remove 's3://' prefix and split by '/'
        if not s3_uri.startswith('s3://'):
            raise ValueError("Invalid S3 URI format. URI must start with 's3://'")
            
        # Remove 's3://' and trailing slashes, then split
        uri_without_prefix = s3_uri[5:].strip('/')
        parts = uri_without_prefix.split('/')
        
        if not parts[0]:
            raise ValueError("No bucket name found in S3 URI")
            
        return parts[0]
        
    except Exception as e:
        print(f"Error extracting bucket name from URI '{s3_uri}': {str(e)}")
        raise

def rename_s3_object(bucket_name, old_key, new_key):
    """
    Rename an S3 object by copying it to a new key and deleting the old one
    
    Args:
        bucket_name (str): Name of the S3 bucket
        old_key (str): Current object key
        new_key (str): New object key
    """
    try:
        # Create S3 client
        s3_client = boto3.client('s3')
        
        # Copy object to new key
        s3_client.copy_object(
            Bucket=bucket_name,
            CopySource={'Bucket': bucket_name, 'Key': old_key},
            Key=new_key
        )
        
        # Delete the old object
        s3_client.delete_object(
            Bucket=bucket_name,
            Key=old_key
        )
        
        print(f"{old_key} to {new_key}")
        
    except ClientError as e:
        print(f"Error: {e}")
        raise
        
def move_s3_object(source_bucket, source_key, target_bucket, target_key):
    """
    Move an S3 object from one bucket/prefix to another bucket/prefix
    
    Args:
        source_bucket (str): Source bucket name
        source_key (str): Source object key (with prefix)
        target_bucket (str): Target bucket name
        target_key (str): Target object key (with prefix)
    """
    try:
        s3_client = boto3.client('s3')
        
        # Copy the object to the target location
        s3_client.copy_object(
            Bucket=target_bucket,
            CopySource={'Bucket': source_bucket, 'Key': source_key},
            Key=target_key
        )
        
        # Delete the object from the source location
        s3_client.delete_object(
            Bucket=source_bucket,
            Key=source_key
        )
        
        print(f"Successfully moved s3://{source_bucket}/{source_key} to s3://{target_bucket}/{target_key}")
        
    except ClientError as e:
        print(f"Error moving S3 object: {e}")
        raise
        
def delete_s3_object(bucket_name, object_key):
    """
    Delete an object from an S3 bucket
    
    Args:
        bucket_name (str): Name of the S3 bucket
        object_key (str): Object key to delete
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        s3_client = boto3.client('s3')
        
        # Delete the object
        s3_client.delete_object(
            Bucket=bucket_name,
            Key=object_key
        )
        
        print(f"Successfully deleted s3://{bucket_name}/{object_key}")
        return True
        
    except ClientError as e:
        print(f"Error deleting S3 object: {e}")
        return False