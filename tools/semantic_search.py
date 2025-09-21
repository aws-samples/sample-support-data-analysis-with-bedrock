#!/usr/bin/env python3

import boto3
import json
import argparse
import sys
sys.path.append('..')
import config
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def generate_query_embedding(query_text, bedrock_client):
    """Generate embedding for search query using Bedrock model from config"""
    try:
        body = json.dumps({
            "inputText": query_text,
            "dimensions": 1024,
            "normalize": True
        })
        
        response = bedrock_client.invoke_model(
            modelId=config.BEDROCK_EMBEDDING_MODEL,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['embedding']
        
    except Exception as e:
        print(f"Error generating query embedding: {e}")
        return None

def semantic_search(opensearch_endpoint, index_name, query_text, region=config.REGION, top_k=5):
    """Perform semantic search using vector embeddings"""
    try:
        # Initialize Bedrock client
        bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        
        # Generate embedding for query
        query_embedding = generate_query_embedding(query_text, bedrock_client)
        if not query_embedding:
            print("Failed to generate query embedding")
            return
        
        # Initialize OpenSearch client
        host = opensearch_endpoint.replace('https://', '')
        session = boto3.Session()
        credentials = session.get_credentials()
        
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            'es',
            session_token=credentials.token
        )
        
        client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30
        )
        
        # Check if index has any documents
        try:
            count_response = client.count(index=index_name)
            total_docs = count_response['count']
            print(f"Total documents in index: {total_docs}")
            
            if total_docs == 0:
                print("Index is empty. No documents to search.")
                return
                
            # Check a sample document structure
            sample_response = client.search(index=index_name, body={"size": 1, "query": {"match_all": {}}})
            if sample_response['hits']['hits']:
                sample_doc = sample_response['hits']['hits'][0]['_source']
                has_vector = 'eventDescription' in sample_doc and 'latestDescriptionVector' in sample_doc.get('eventDescription', {})
                print(f"Sample document has vector field: {has_vector}")
                if 'eventDescription' in sample_doc:
                    has_desc = 'latestDescription' in sample_doc['eventDescription']
                    print(f"Sample document has description: {has_desc}")
        except Exception as e:
            print(f"Error checking document count: {e}")
        
        # Perform vector search
        search_body = {
            "size": top_k,
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'eventDescription.latestDescriptionVector') + 1.0",
                        "params": {"query_vector": query_embedding}
                    }
                }
            }
        }
        
        try:
            response = client.search(index=index_name, body=search_body)
        except Exception as e:
            print(f"Vector search failed: {e}")
            print("Falling back to text search...")
            # Fallback to text search
            search_body = {
                "size": top_k,
                "query": {
                    "match": {
                        "eventDescription.latestDescription": query_text
                    }
                }
            }
            response = client.search(index=index_name, body=search_body)
        
        print(f"Found {len(response['hits']['hits'])} matching results for query: '{query_text}'")
        print("=" * 80)
        
        for i, hit in enumerate(response['hits']['hits'], 1):
            score = hit['_score']
            source = hit['_source']
            
            print(f"\nResult {i} (Score: {score:.4f})")
            print("-" * 40)
            print(f"Event ARN: {source.get('arn', 'N/A')}")
            print(f"Service: {source.get('service', 'N/A')}")
            print(f"Event Type: {source.get('eventTypeCode', 'N/A')}")
            print(f"Status: {source.get('statusCode', 'N/A')}")
            print(f"Region: {source.get('region', 'N/A')}")
            
            # Show description snippet
            desc = source.get('eventDescription', {}).get('latestDescription', '')
            if desc:
                snippet = desc[:200] + "..." if len(desc) > 200 else desc
                print(f"Description: {snippet}")
            
            print(f"\nFull Record:")
            # Remove vector field from output
            source_copy = source.copy()
            if 'eventDescription' in source_copy and 'latestDescriptionVector' in source_copy['eventDescription']:
                del source_copy['eventDescription']['latestDescriptionVector']
            print(json.dumps(source_copy, indent=2, default=str))
            print("=" * 80)
        
    except Exception as e:
        print(f"Error performing semantic search: {e}")

def main():
    parser = argparse.ArgumentParser(description='Semantic search against AWS Health events using vector embeddings')
    parser.add_argument('--opensearch-endpoint', required=True, help='OpenSearch endpoint URL')
    parser.add_argument('--index-name', required=True, help='OpenSearch index name')
    parser.add_argument('--query', required=True, help='Natural language search query')
    parser.add_argument('--region', default=config.REGION, help=f'AWS region (default: {config.REGION})')
    parser.add_argument('--top-k', type=int, default=5, help='Number of top results to return (default: 5)')
    
    args = parser.parse_args()
    
    semantic_search(args.opensearch_endpoint, args.index_name, args.query, args.region, args.top_k)

if __name__ == '__main__':
    main()
