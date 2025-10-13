#!/usr/bin/env python3

import argparse
import boto3
import os
import sys
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

def lexical_search(query_text):
    """Perform lexical search on maki-cases index"""
    aoss_client = create_aoss_client()
    
    search_body = {
        "query": {
            "multi_match": {
                "query": query_text,
                "fields": [
                    "case_summary^2",
                    "suggested_action^2", 
                    "category_explanation",
                    "category",
                    "serviceCode",
                    "status",
                    "submittedBy",
                    "sentiment"
                ],
                "type": "best_fields"
            }
        },
        "size": 10,
        "highlight": {
            "fields": {
                "case_summary": {},
                "suggested_action": {},
                "category_explanation": {}
            }
        }
    }
    
    return aoss_client.search(index="maki-cases", body=search_body)

def main():
    parser = argparse.ArgumentParser(description='Lexical search on maki-cases index')
    parser.add_argument('--input', required=True, help='Query text for lexical search')
    args = parser.parse_args()
    
    print(f"Searching for: {args.input}")
    results = lexical_search(args.input)
    
    print(f"\nFound {len(results['hits']['hits'])} results:")
    for i, hit in enumerate(results['hits']['hits'], 1):
        source = hit['_source']
        score = hit['_score']
        print(f"\n{i}. Score: {score:.4f}")
        print(f"   Case ID: {source.get('caseId', 'N/A')}")
        print(f"   Category: {source.get('category', 'N/A')}")
        print(f"   Service: {source.get('serviceCode', 'N/A')}")
        print(f"   Status: {source.get('status', 'N/A')}")
        print(f"   Summary: {source.get('case_summary', 'N/A')[:200]}...")
        print(f"   Suggested Action: {source.get('suggested_action', 'N/A')[:200]}...")
        
        # Show highlights if available
        if 'highlight' in hit:
            print("   Highlights:")
            for field, highlights in hit['highlight'].items():
                print(f"     {field}: {highlights[0][:150]}...")

if __name__ == "__main__":
    main()
