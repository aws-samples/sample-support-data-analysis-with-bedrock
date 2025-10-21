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
        def support_cases_semantic_search(query: str, size: int = 10) -> Dict[str, Any]:
            """Search AWS Support Cases using semantic vector embeddings to find similar case summaries and suggested actions"""
            if not self.opensearch_client:
                return {"error": "OpenSearch not configured. Please deploy MAKI infrastructure first."}
            
            try:
                import boto3
                from config import BEDROCK_EMBEDDING_MODEL
                
                # Generate embedding for query
                bedrock_client = boto3.client('bedrock-runtime')
                response = bedrock_client.invoke_model(
                    modelId=BEDROCK_EMBEDDING_MODEL,
                    body=json.dumps({"inputText": query})
                )
                query_embedding = json.loads(response['body'].read())['embedding']
                
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
                    "size": size
                }
                
                try:
                    response = self.opensearch_client.search(index="maki-cases", body=search_body)
                except Exception:
                    # Fallback to text search if vector search fails
                    search_body = {
                        "query": {
                            "multi_match": {
                                "query": query,
                                "fields": ["case_summary", "suggested_action", "category_explanation"]
                            }
                        },
                        "size": size
                    }
                    response = self.opensearch_client.search(index="maki-cases", body=search_body)
                
                results = []
                for hit in response['hits']['hits']:
                    source = hit['_source']
                    results.append({
                        "score": hit['_score'],
                        "case_id": source.get('caseId', 'N/A'),
                        "category": source.get('category', 'N/A'),
                        "service": source.get('serviceCode', 'N/A'),
                        "summary": source.get('case_summary', 'N/A')[:200] + "..." if len(source.get('case_summary', '')) > 200 else source.get('case_summary', 'N/A'),
                        "suggested_action": source.get('suggested_action', 'N/A')[:200] + "..." if len(source.get('suggested_action', '')) > 200 else source.get('suggested_action', 'N/A')
                    })
                
                return {
                    "query": query,
                    "total_hits": response['hits']['total']['value'],
                    "results": results
                }
                
            except Exception as e:
                return {"error": f"Support cases semantic search failed: {str(e)}"}
        
        @self.mcp.tool()
        def support_cases_lexical_search(query: str, size: int = 10) -> Dict[str, Any]:
            """Search AWS Support Cases using exact keyword matching across case summaries, categories, and service codes"""
            if not self.opensearch_client:
                return {"error": "OpenSearch not configured. Please deploy MAKI infrastructure first."}
            
            try:
                search_body = {
                    "query": {
                        "multi_match": {
                            "query": query,
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
                    "size": size,
                    "highlight": {
                        "fields": {
                            "case_summary": {},
                            "suggested_action": {},
                            "category_explanation": {}
                        }
                    }
                }
                
                response = self.opensearch_client.search(index="maki-cases", body=search_body)
                
                results = []
                for hit in response['hits']['hits']:
                    source = hit['_source']
                    result = {
                        "score": hit['_score'],
                        "case_id": source.get('caseId', 'N/A'),
                        "category": source.get('category', 'N/A'),
                        "service": source.get('serviceCode', 'N/A'),
                        "status": source.get('status', 'N/A'),
                        "summary": source.get('case_summary', 'N/A')[:200] + "..." if len(source.get('case_summary', '')) > 200 else source.get('case_summary', 'N/A'),
                        "suggested_action": source.get('suggested_action', 'N/A')[:200] + "..." if len(source.get('suggested_action', '')) > 200 else source.get('suggested_action', 'N/A')
                    }
                    
                    # Add highlights if available
                    if 'highlight' in hit:
                        result['highlights'] = {}
                        for field, highlights in hit['highlight'].items():
                            result['highlights'][field] = highlights[0][:150] + "..." if len(highlights[0]) > 150 else highlights[0]
                    
                    results.append(result)
                
                return {
                    "query": query,
                    "total_hits": response['hits']['total']['value'],
                    "results": results
                }
                
            except Exception as e:
                return {"error": f"Support cases lexical search failed: {str(e)}"}
        
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
        
        @self.mcp.tool()
        def support_cases_hybrid_search(query: str, size: int = 10) -> Dict[str, Any]:
            """Search AWS Support Cases using hybrid lexical and semantic search against the opensearch index which has both lexical and embeddings fields"""
            if not self.opensearch_client:
                return {"error": "OpenSearch not configured. Please deploy MAKI infrastructure first."}
            
            try:
                # Hybrid search combining lexical and semantic approaches
                search_body = {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "multi_match": {
                                        "query": query,
                                        "fields": [
                                            "case_summary^2",
                                            "suggested_action^2", 
                                            "category_explanation",
                                            "category",
                                            "serviceCode"
                                        ],
                                        "type": "best_fields"
                                    }
                                }
                            ]
                        }
                    },
                    "size": size
                }
                
                # Try to add semantic search if embeddings are available
                try:
                    import boto3
                    from config import BEDROCK_EMBEDDING_MODEL
                    
                    bedrock_client = boto3.client('bedrock-runtime')
                    response = bedrock_client.invoke_model(
                        modelId=BEDROCK_EMBEDDING_MODEL,
                        body=json.dumps({"inputText": query})
                    )
                    query_embedding = json.loads(response['body'].read())['embedding']
                    
                    # Add semantic search to the hybrid query
                    search_body["query"]["bool"]["should"].append({
                        "script_score": {
                            "query": {"match_all": {}},
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'case_summary_suggested_action_embedding') + 1.0",
                                "params": {"query_vector": query_embedding}
                            }
                        }
                    })
                except:
                    # Continue with lexical-only search if embedding fails
                    pass
                
                response = self.opensearch_client.search(index="maki-cases", body=search_body)
                
                results = []
                for hit in response['hits']['hits']:
                    source = hit['_source']
                    results.append({
                        "score": hit['_score'],
                        "case_id": source.get('caseId', 'N/A'),
                        "category": source.get('category', 'N/A'),
                        "service": source.get('serviceCode', 'N/A'),
                        "summary": source.get('case_summary', 'N/A')[:200] + "..." if len(source.get('case_summary', '')) > 200 else source.get('case_summary', 'N/A'),
                        "suggested_action": source.get('suggested_action', 'N/A')[:200] + "..." if len(source.get('suggested_action', '')) > 200 else source.get('suggested_action', 'N/A')
                    })
                
                return {
                    "query": query,
                    "total_hits": response['hits']['total']['value'],
                    "results": results,
                    "search_type": "hybrid"
                }
                
            except Exception as e:
                return {"error": f"Support cases hybrid search failed: {str(e)}"}
        
        @self.mcp.tool()
        def aws_health_events_hybrid_search(query: str, size: int = None, index: str = None) -> Dict[str, Any]:
            """Search AWS Health Events using hybrid lexical and semantic search against the opensearch index which has both lexical and embeddings fields"""
            if not self.opensearch_client:
                return {"error": "OpenSearch not configured. Please deploy MAKI infrastructure first."}
            
            # Use defaults from SSM parameters
            if size is None:
                size = self.default_size
            if index is None:
                index = self.default_index
            
            try:
                # Hybrid search combining lexical and semantic approaches
                search_body = {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "query_string": {
                                        "query": query,
                                        "default_operator": "OR"
                                    }
                                }
                            ]
                        }
                    },
                    "size": size
                }
                
                # Try to add semantic search if embeddings are available
                try:
                    import boto3
                    from config import BEDROCK_EMBEDDING_MODEL
                    
                    bedrock_client = boto3.client('bedrock-runtime')
                    response = bedrock_client.invoke_model(
                        modelId=BEDROCK_EMBEDDING_MODEL,
                        body=json.dumps({"inputText": query})
                    )
                    query_embedding = json.loads(response['body'].read())['embedding']
                    
                    # Add semantic search to the hybrid query
                    search_body["query"]["bool"]["should"].append({
                        "script_score": {
                            "query": {"match_all": {}},
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'embedding_field') + 1.0",
                                "params": {"query_vector": query_embedding}
                            }
                        }
                    })
                except:
                    # Continue with lexical-only search if embedding fails
                    pass
                
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
                    "results": results,
                    "search_type": "hybrid"
                }
                
            except Exception as e:
                return {"error": f"AWS Health Events hybrid search failed: {str(e)}"}

    
    def run(self):
        """Run the FastMCP agent"""
        self.mcp.run()

def main():
    """Main entry point for the MAKI agent"""
    agent = MakiAgent()
    agent.run()

if __name__ == "__main__":
    main()
