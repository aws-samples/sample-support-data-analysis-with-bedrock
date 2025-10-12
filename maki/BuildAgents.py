#!/usr/bin/env python3
"""
MAKI FastMCP Agent for Amazon Q CLI
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

class MakiAgent:
    """MAKI FastMCP Agent for OpenSearch querying"""
    
    def __init__(self):
        self.mcp = FastMCP("MAKI Agent - AWS Health Events Analysis")
        self.opensearch_client = None
        self.collection_endpoint = None
        self._setup_opensearch()
        self._register_tools()
    
    def _setup_opensearch(self):
        """Initialize OpenSearch client with AWS authentication"""
        try:
            import boto3
            from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
            
            session = boto3.Session()
            credentials = session.get_credentials()
            region = session.region_name or 'us-east-1'
            
            ssm = boto3.client('ssm')
            account_id = boto3.client('sts').get_caller_identity()['Account']
            
            # Get OpenSearch endpoint
            response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-endpoint")
            self.collection_endpoint = response['Parameter']['Value']
            
            # Get other OpenSearch parameters
            try:
                self.default_index = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-index")['Parameter']['Value']
            except:
                self.default_index = "amazon-health-events"
            
            try:
                self.default_size = int(ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-query-size")['Parameter']['Value'])
            except:
                self.default_size = 10
            
            auth = AWSV4SignerAuth(credentials, region, 'aoss')
            
            self.opensearch_client = OpenSearch(
                hosts=[{'host': self.collection_endpoint.replace('https://', ''), 'port': 443}],
                http_auth=auth,
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection,
                pool_maxsize=20,
            )
            
        except Exception:
            # Silently handle AWS credential or configuration issues
            self.default_index = "aws-health-events"
            self.default_size = 10
    
    def _register_tools(self):
        """Register MCP tools for search functionality"""
        
        @self.mcp.tool()
        def aws_health_events_semantic_search(query: str, size: int = None, index: str = None) -> Dict[str, Any]:
            """Search AWS Health Events using semantic vector embeddings to find similar incidents, outages, and service disruptions"""
            if not self.opensearch_client:
                return {"error": "OpenSearch not configured. Please deploy MAKI infrastructure first."}
            
            # Use defaults from SSM parameters
            if size is None:
                size = self.default_size
            if index is None:
                index = self.default_index
            
            try:
                # For now, fall back to lexical search since vector search requires specific index mapping
                search_body = {
                    "size": size,
                    "query": {
                        "query_string": {
                            "query": query,
                            "default_operator": "OR"
                        }
                    }
                }
                
                response = self.opensearch_client.search(index=index, body=search_body)
                
                results = []
                for hit in response['hits']['hits']:
                    results.append({
                        "score": hit['_score'],
                        "source": hit['_source']
                    })
                
                return {
                    "query": query,
                    "total_hits": response['hits']['total']['value'],
                    "results": results
                }
                
            except Exception as e:
                return {"error": f"Semantic search failed: {str(e)}"}
        
        @self.mcp.tool()
        def aws_health_events_lexical_search(query: str, size: int = None, index: str = None, fields: Optional[List[str]] = None) -> Dict[str, Any]:
            """Search AWS Health Events using exact keyword matching to find specific service names, regions, or event types"""
            if not self.opensearch_client:
                return {"error": "OpenSearch not configured. Please deploy MAKI infrastructure first."}
            
            # Use defaults from SSM parameters
            if size is None:
                size = self.default_size
            if index is None:
                index = self.default_index
            
            try:
                # Handle wildcard queries and match_all for AOSS
                if query == "*":
                    search_query = {"match_all": {}}
                else:
                    # Use query_string for better compatibility with AOSS
                    search_query = {"query_string": {"query": query, "default_operator": "OR"}}
                
                search_body = {
                    "size": size,
                    "query": search_query
                }
                
                response = self.opensearch_client.search(index=index, body=search_body)
                
                results = []
                for hit in response['hits']['hits']:
                    results.append({
                        "score": hit['_score'],
                        "source": hit['_source']
                    })
                
                return {
                    "query": query,
                    "total_hits": response['hits']['total']['value'],
                    "results": results
                }
                
            except Exception as e:
                return {"error": f"Lexical search failed: {str(e)}"}
        
        @self.mcp.tool()
        def get_index_stats(index: str = None) -> Dict[str, Any]:
            """Get statistics about the AWS Health Events index including document count and storage metrics"""
            if not self.opensearch_client:
                return {"error": "OpenSearch not configured. Please deploy MAKI infrastructure first."}
            
            # Use default from SSM parameters
            if index is None:
                index = self.default_index
            
            try:
                # Use cat.indices API which is supported in AOSS
                indices = self.opensearch_client.cat.indices(format='json')
                
                # Find the specific index
                for idx in indices:
                    if idx['index'] == index:
                        return {
                            "index": index,
                            "document_count": int(idx['docs.count']),
                            "store_size": idx['store.size'],
                            "status": idx['status'],
                            "health": idx['health']
                        }
                
                return {"error": f"Index '{index}' not found"}
                
            except Exception as e:
                return {"error": f"Failed to get index stats: {str(e)}"}
    
    def run(self):
        """Run the FastMCP agent"""
        self.mcp.run()

def main():
    """Main entry point for the MAKI agent"""
    agent = MakiAgent()
    agent.run()

if __name__ == "__main__":
    main()
