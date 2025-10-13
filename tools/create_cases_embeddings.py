#!/usr/bin/env python3

import boto3
import json
import os
import time
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BEDROCK_EMBEDDING_MODEL

def create_aoss_client():
    """Create OpenSearch Serverless client"""
    ssm = boto3.client('ssm')
    endpoint = ssm.get_parameter(Name='maki-923344048102-us-east-1-opensearch-endpoint')['Parameter']['Value']
    host = endpoint.replace('https://', '')
    region = "us-east-1"
    service = "aoss"
    credentials = boto3.Session().get_credentials()
    awsauth = AWSRequestsAuth(
        aws_access_key=credentials.access_key,
        aws_secret_access_key=credentials.secret_key,
        aws_host=host,
        aws_region=region,
        aws_service=service,
        aws_token=credentials.token
    )
    
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60,
        max_retries=3,
        retry_on_timeout=True
    )

def create_index(client):
    """Create maki-cases index"""
    index_name = "maki-cases"
    
    # Delete existing index if it exists to avoid mapping conflicts
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        print(f"Deleted existing index: {index_name}")
    
    index_body = {
        "mappings": {
            "properties": {
                "caseId": {"type": "keyword"},
                "displayId": {"type": "keyword"},
                "status": {"type": "keyword"},
                "serviceCode": {"type": "keyword"},
                "timeCreated": {"type": "date", "format": "yyyy/MM/dd HH:mm:ss||yyyy-MM-dd'T'HH:mm:ss.SSS'Z'||epoch_millis"},
                "timeResolved": {"type": "date", "format": "yyyy/MM/dd HH:mm:ss||yyyy-MM-dd'T'HH:mm:ss.SSS'Z'||epoch_millis"},
                "submittedBy": {"type": "keyword"},
                "category": {"type": "keyword"},
                "category_explanation": {"type": "text"},
                "case_summary": {"type": "text"},
                "sentiment": {"type": "keyword"},
                "suggested_action": {"type": "text"},
                "suggestion_link": {"type": "keyword"},
                "case_summary_suggested_action_embedding": {"type": "binary"}
            }
        }
    }
    
    client.indices.create(index=index_name, body=index_body)
    print(f"Created index: {index_name}")

def get_embedding(text, bedrock_client):
    """Generate embedding using Bedrock"""
    response = bedrock_client.invoke_model(
        modelId=BEDROCK_EMBEDDING_MODEL,
        body=json.dumps({"inputText": text})
    )
    return json.loads(response['body'].read())['embedding']

def index_with_retry(client, index_name, doc_id, body, max_retries=3):
    """Index document with retry logic"""
    for attempt in range(max_retries):
        try:
            client.index(index=index_name, id=doc_id, body=body)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Retry {attempt + 1} for {doc_id}: {str(e)}")
                time.sleep(2 ** attempt)
            else:
                print(f"Failed to index {doc_id}: {str(e)}")
                return False

def check_duplicate_and_make_unique(client, case_id):
    """Check if caseId exists and make it unique if needed"""
    if not case_id:
        return case_id
    
    try:
        # Check if document with this caseId already exists
        search_result = client.search(
            index="maki-cases",
            body={"query": {"term": {"caseId": case_id}}, "size": 1}
        )
        
        if search_result['hits']['total']['value'] > 0:
            # Duplicate found, append timestamp
            import time
            timestamp = str(int(time.time() * 1000))
            return f"{case_id}-{timestamp}"
        
        return case_id
    except:
        return case_id

def normalize_date_format(date_str):
    """Convert various date formats to yyyy/MM/dd HH:mm:ss"""
    if not date_str:
        return date_str
    
    from datetime import datetime
    
    # Try different input formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ", 
        "%Y/%m/%d %H:%M:%S"
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y/%m/%d %H:%M:%S")
        except ValueError:
            continue
    
    return date_str  # Return original if no format matches
    """Convert various date formats to yyyy/MM/dd HH:mm:ss"""
    if not date_str:
        return date_str
    
    from datetime import datetime
    
    # Try different input formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ", 
        "%Y/%m/%d %H:%M:%S"
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y/%m/%d %H:%M:%S")
        except ValueError:
            continue
    
    return date_str  # Return original if no format matches

def process_cases():
    """Read S3 cases and create embeddings"""
    s3_client = boto3.client('s3')
    bedrock_client = boto3.client('bedrock-runtime')
    aoss_client = create_aoss_client()
    
    create_index(aoss_client)
    
    bucket = "maki-report-riv"
    prefix = "cases/"
    
    paginator = s3_client.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' not in page:
            continue
            
        for obj in page['Contents']:
            if not obj['Key'].endswith('.json'):
                continue
                
            try:
                # Read case object
                response = s3_client.get_object(Bucket=bucket, Key=obj['Key'])
                case_data = json.loads(response['Body'].read())
                
                # Normalize date formats
                if 'timeCreated' in case_data:
                    case_data['timeCreated'] = normalize_date_format(case_data['timeCreated'])
                if 'timeResolved' in case_data:
                    case_data['timeResolved'] = normalize_date_format(case_data['timeResolved'])
                
                # Make caseId unique if duplicate exists
                original_case_id = case_data.get('caseId', obj['Key'])
                unique_case_id = check_duplicate_and_make_unique(aoss_client, original_case_id)
                case_data['caseId'] = unique_case_id
                
                # Combine case_summary and suggested_action
                combined_text = f"{case_data.get('case_summary', '')} {case_data.get('suggested_action', '')}"
                
                if combined_text.strip():
                    # Generate embedding
                    embedding = get_embedding(combined_text, bedrock_client)
                    
                    # Add embedding to case data
                    case_data['case_summary_suggested_action_embedding'] = embedding
                    
                    # Index in AOSS with retry using unique caseId
                    if index_with_retry(aoss_client, "maki-cases", unique_case_id, case_data):
                        print(f"Processed case: {unique_case_id}")
                    
            except Exception as e:
                print(f"Error processing {obj['Key']}: {str(e)}")

if __name__ == "__main__":
    process_cases()
