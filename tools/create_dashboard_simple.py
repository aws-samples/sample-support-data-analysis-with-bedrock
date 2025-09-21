#!/usr/bin/env python3

import boto3
import json
import argparse
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def create_dashboard_objects(client, index_name='aws-health-events'):
    """Create dashboard objects using OpenSearch API"""
    
    # First, let's check what API endpoints are available
    try:
        # Try to list existing saved objects to verify API path
        response = client.transport.perform_request('GET', '/_plugins/_dashboards/api/saved_objects/_find?type=dashboard')
        print("Using _plugins/_dashboards API path")
        api_base = '/_plugins/_dashboards/api/saved_objects'
    except:
        try:
            response = client.transport.perform_request('GET', '/_dashboards/api/saved_objects/_find?type=dashboard')
            print("Using _dashboards API path")
            api_base = '/_dashboards/api/saved_objects'
        except:
            print("Could not determine correct API path. Creating manually...")
            return False
    
    pattern_id = f"{index_name}*"
    
    # Create index pattern
    index_pattern = {
        "attributes": {
            "title": pattern_id,
            "timeFieldName": "startTime"
        }
    }
    
    try:
        client.transport.perform_request(
            'POST',
            f'{api_base}/index-pattern/{pattern_id}',
            headers={'osd-xsrf': 'true'},
            body=json.dumps(index_pattern)
        )
        print(f"Created index pattern: {pattern_id}")
    except Exception as e:
        print(f"Index pattern creation: {e}")
    
    # Create visualization
    viz_id = "health-events-by-service"
    visualization = {
        "attributes": {
            "title": "Health Events by Service",
            "type": "pie",
            "visState": json.dumps({
                "title": "Health Events by Service",
                "type": "pie",
                "params": {
                    "addTooltip": True,
                    "addLegend": True,
                    "legendPosition": "right"
                },
                "aggs": [
                    {
                        "id": "1",
                        "type": "count",
                        "schema": "metric",
                        "params": {}
                    },
                    {
                        "id": "2", 
                        "type": "terms",
                        "schema": "segment",
                        "params": {
                            "field": "service",
                            "size": 10,
                            "order": "desc",
                            "orderBy": "1"
                        }
                    }
                ]
            }),
            "uiStateJSON": "{}",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "index": pattern_id,
                    "query": {"match_all": {}}
                })
            }
        }
    }
    
    try:
        client.transport.perform_request(
            'POST',
            f'{api_base}/visualization/{viz_id}',
            headers={'osd-xsrf': 'true'},
            body=json.dumps(visualization)
        )
        print(f"Created visualization: {viz_id}")
    except Exception as e:
        print(f"Visualization creation: {e}")
    
    # Create dashboard
    dashboard_id = "aws-health-dashboard"
    dashboard = {
        "attributes": {
            "title": "AWS Health Events Dashboard",
            "description": "Dashboard for AWS Health events",
            "panelsJSON": json.dumps([
                {
                    "id": viz_id,
                    "type": "visualization",
                    "gridData": {
                        "x": 0,
                        "y": 0,
                        "w": 24,
                        "h": 15,
                        "i": "1"
                    }
                }
            ]),
            "optionsJSON": json.dumps({
                "useMargins": True,
                "hidePanelTitles": False
            })
        }
    }
    
    try:
        client.transport.perform_request(
            'POST',
            f'{api_base}/dashboard/{dashboard_id}',
            headers={'osd-xsrf': 'true'},
            body=json.dumps(dashboard)
        )
        print(f"Created dashboard: {dashboard_id}")
        return True
    except Exception as e:
        print(f"Dashboard creation: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Create OpenSearch dashboard')
    parser.add_argument('--domain-name', default='maki-health')
    parser.add_argument('--index-name', default='aws-health-events')
    parser.add_argument('--region', default='us-east-1')
    
    args = parser.parse_args()
    
    # Get domain endpoint
    client = boto3.client('opensearch', region_name=args.region)
    status = client.describe_domain(DomainName=args.domain_name)
    domain_status = status['DomainStatus']
    
    if 'Endpoint' in domain_status:
        endpoint = f"https://{domain_status['Endpoint']}"
    elif 'Endpoints' in domain_status:
        endpoint = f"https://{list(domain_status['Endpoints'].values())[0]}"
    else:
        endpoint = f"https://{args.domain_name}-{domain_status['DomainId']}.{args.region}.es.amazonaws.com"
    
    print(f"Endpoint: {endpoint}")
    
    # Connect to OpenSearch
    host = endpoint.replace('https://', '')
    session = boto3.Session()
    credentials = session.get_credentials()
    
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        args.region,
        'es',
        session_token=credentials.token
    )
    
    opensearch_client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=30
    )
    
    # Check index exists
    if not opensearch_client.indices.exists(index=args.index_name):
        print(f"Error: Index {args.index_name} does not exist")
        return 1
    
    # Create dashboard
    success = create_dashboard_objects(opensearch_client, args.index_name)
    
    if success:
        print(f"\n✅ Dashboard created!")
        print(f"Access: {endpoint}/_dashboards")
    else:
        print(f"\n❌ Dashboard creation failed")
        print("Manual creation required in OpenSearch Dashboards UI")

if __name__ == '__main__':
    main()
