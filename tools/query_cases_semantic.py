#!/usr/bin/env python3

import argparse
import boto3
import json
import os
import sys
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

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
        timeout=60
    )

def get_embedding(text, bedrock_client):
    """Generate embedding using Bedrock"""
    response = bedrock_client.invoke_model(
        modelId=BEDROCK_EMBEDDING_MODEL,
        body=json.dumps({"inputText": text})
    )
    return json.loads(response['body'].read())['embedding']

def semantic_search(query_text):
    """Perform semantic search on maki-cases index"""
    bedrock_client = boto3.client('bedrock-runtime')
    aoss_client = create_aoss_client()
    
    # Generate embedding for query
    query_embedding = get_embedding(query_text, bedrock_client)
    
    # Perform semantic search using script_score
    search_body = {
        "query": {
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'case_summary_suggested_action_embedding') + 1.0",
                    "params": {"query_vector": query_embedding}
                }
            }
        },
        "size": 10
    }
    
    try:
        results = aoss_client.search(index="maki-cases", body=search_body)
        return results
    except Exception as e:
        print(f"Search error: {e}")
        # Fallback to text search if vector search fails
        text_search_body = {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": ["case_summary", "suggested_action", "category_explanation"]
                }
            },
            "size": 10
        }
        return aoss_client.search(index="maki-cases", body=text_search_body)

def main():
    parser = argparse.ArgumentParser(description='Semantic search on maki-cases index')
    parser.add_argument('--input', required=True, help='Query text for semantic search')
    args = parser.parse_args()
    
    print(f"Searching for: {args.input}")
    results = semantic_search(args.input)
    
    print(f"\nFound {len(results['hits']['hits'])} results:")
    for i, hit in enumerate(results['hits']['hits'], 1):
        source = hit['_source']
        score = hit['_score']
        print(f"\n{i}. Score: {score:.4f}")
        print(f"   Case ID: {source.get('caseId', 'N/A')}")
        print(f"   Category: {source.get('category', 'N/A')}")
        print(f"   Summary: {source.get('case_summary', 'N/A')[:200]}...")
        print(f"   Suggested Action: {source.get('suggested_action', 'N/A')[:200]}...")

if __name__ == "__main__":
    main()
