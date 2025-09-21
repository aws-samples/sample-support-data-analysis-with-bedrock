#!/usr/bin/env python3

import boto3
import json
import argparse
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def create_simple_dashboard(client, index_name='aws-health-events'):
    """Create dashboard using direct API calls"""
    
    # Create index pattern using PUT (simpler than import)
    pattern_id = f"{index_name}*"
    index_pattern_body = {
        "attributes": {
            "title": pattern_id,
            "timeFieldName": "startTime"
        }
    }
    
    try:
        response = client.transport.perform_request(
            'PUT',
            f'/_dashboards/api/saved_objects/index-pattern/{pattern_id}',
            headers={'osd-xsrf': 'true'},
            body=json.dumps(index_pattern_body)
        )
        print(f"Created index pattern: {pattern_id}")
    except Exception as e:
        print(f"Index pattern may already exist: {e}")
    
    # Create simple visualization using PUT
    viz_body = {
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
        response = client.transport.perform_request(
            'PUT',
            '/_dashboards/api/saved_objects/visualization/health-events-by-service',
            headers={'osd-xsrf': 'true'},
            body=json.dumps(viz_body)
        )
        print("Created visualization: Health Events by Service")
    except Exception as e:
        print(f"Visualization may already exist: {e}")
    
    # Create dashboard
    dashboard_body = {
        "attributes": {
            "title": "AWS Health Events Dashboard",
            "description": "Dashboard for AWS Health events",
            "panelsJSON": json.dumps([
                {
                    "id": "health-events-by-service",
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
        response = client.transport.perform_request(
            'PUT',
            '/_dashboards/api/saved_objects/dashboard/aws-health-dashboard',
            headers={'osd-xsrf': 'true'},
            body=json.dumps(dashboard_body)
        )
        print("Created dashboard: AWS Health Events Dashboard")
        return True
    except Exception as e:
        print(f"Could not create dashboard: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Create OpenSearch dashboard for AWS Health events')
    parser.add_argument('--domain-name', default='maki-health', help='OpenSearch domain name')
    parser.add_argument('--index-name', default='aws-health-events', help='Index name')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    
    args = parser.parse_args()
    
    # Get domain endpoint
    client = boto3.client('opensearch', region_name=args.region)
    try:
        status = client.describe_domain(DomainName=args.domain_name)
        domain_status = status['DomainStatus']
        
        if 'Endpoint' in domain_status:
            endpoint = f"https://{domain_status['Endpoint']}"
        elif 'Endpoints' in domain_status:
            endpoint = f"https://{list(domain_status['Endpoints'].values())[0]}"
        else:
            endpoint = f"https://{args.domain_name}-{domain_status['DomainId']}.{args.region}.es.amazonaws.com"
        
        print(f"Using domain endpoint: {endpoint}")
        
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
        
        # Check if index exists
        if not opensearch_client.indices.exists(index=args.index_name):
            print(f"Error: Index {args.index_name} does not exist")
            return 1
        
        # Create dashboard
        success = create_simple_dashboard(opensearch_client, args.index_name)
        
        if success:
            print(f"\n✅ Dashboard created successfully!")
            print(f"Access at: {endpoint}/_dashboards")
        else:
            print(f"\n❌ Dashboard creation failed")
            print("Try creating manually in OpenSearch Dashboards UI")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == '__main__':
    main()
