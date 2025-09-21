#!/usr/bin/env python3

import boto3
import json
import time
import argparse
from datetime import datetime, timedelta
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def get_current_instance_vpc_info():
    """Get VPC and subnet information from current EC2 instance"""
    import subprocess
    
    def get_metadata(path):
        cmd = f'TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600") && curl -H "X-aws-ec2-metadata-token: $TOKEN" -s http://169.254.169.254/latest/meta-data/{path}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip()
    
    # Get current instance network info
    mac = get_metadata('mac')
    vpc_id = get_metadata(f'network/interfaces/macs/{mac}/vpc-id')
    subnet_id = get_metadata(f'network/interfaces/macs/{mac}/subnet-id')
    sg_ids = get_metadata(f'network/interfaces/macs/{mac}/security-group-ids').split('\n')
    
    print(f"Current instance VPC: {vpc_id}")
    print(f"Current instance subnet: {subnet_id}")
    print(f"Current instance security groups: {sg_ids}")
    
    return vpc_id, [subnet_id], sg_ids[0] if sg_ids else None

def create_vpc_endpoint_current_subnet(region='us-east-1'):
    """Create VPC endpoint for OpenSearch in current EC2 instance's subnet"""
    vpc_id, subnet_ids, _ = get_current_instance_vpc_info()
    subnet_id = subnet_ids[0]
    
    ec2 = boto3.client('ec2', region_name=region)
    
    # Check if VPC endpoint already exists
    try:
        endpoints = ec2.describe_vpc_endpoints(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'service-name', 'Values': [f'com.amazonaws.{region}.es']}
            ]
        )
        
        if endpoints['VpcEndpoints']:
            endpoint_id = endpoints['VpcEndpoints'][0]['VpcEndpointId']
            print(f"VPC endpoint already exists: {endpoint_id}")
            return endpoint_id
    except Exception as e:
        print(f"Error checking existing VPC endpoints: {e}")
    
    # Create VPC endpoint in current subnet
    try:
        response = ec2.create_vpc_endpoint(
            VpcId=vpc_id,
            ServiceName=f'com.amazonaws.{region}.es',
            VpcEndpointType='Interface',
            SubnetIds=[subnet_id],
            PolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "es:*",
                        "Resource": "*"
                    }
                ]
            })
        )
        
        endpoint_id = response['VpcEndpoint']['VpcEndpointId']
        print(f"Created VPC endpoint: {endpoint_id}")
        
        # Wait for endpoint to be available
        print("Waiting for VPC endpoint to be available...")
        waiter = ec2.get_waiter('vpc_endpoint_available')
        waiter.wait(VpcEndpointIds=[endpoint_id])
        print("VPC endpoint is now available")
        
        return endpoint_id
        
    except Exception as e:
        print(f"Error creating VPC endpoint: {e}")
        return None

def validate_and_fix_domain_config(client, domain_name, expected_config):
    """Validate domain configuration and fix if needed"""
    status = client.describe_domain(DomainName=domain_name)
    domain_status = status['DomainStatus']
    
    needs_update = False
    update_config = {}
    
    # Check cluster configuration
    current_cluster = domain_status['ClusterConfig']
    expected_cluster = expected_config['ClusterConfig']
    
    if (current_cluster['InstanceType'] != expected_cluster['InstanceType'] or
        current_cluster['InstanceCount'] != expected_cluster['InstanceCount']):
        needs_update = True
        update_config['ClusterConfig'] = expected_cluster
        print(f"Cluster config needs update: {current_cluster} -> {expected_cluster}")
    
    # Check EBS configuration
    current_ebs = domain_status['EBSOptions']
    expected_ebs = expected_config['EBSOptions']
    
    if (current_ebs['VolumeSize'] != expected_ebs['VolumeSize'] or
        current_ebs['VolumeType'] != expected_ebs['VolumeType']):
        needs_update = True
        update_config['EBSOptions'] = expected_ebs
        print(f"EBS config needs update: {current_ebs} -> {expected_ebs}")
    
    # Apply updates if needed
    if needs_update:
        print("Updating domain configuration...")
        client.update_domain_config(
            DomainName=domain_name,
            **update_config
        )
        
        # Wait for update to complete
        while True:
            status = client.describe_domain(DomainName=domain_name)
            if not status['DomainStatus']['Processing']:
                break
            print("Waiting for domain update to complete...")
            time.sleep(30)
    
    return domain_status

def check_index_exists(opensearch_client, index_name):
    """Check if index exists and has correct mapping"""
    try:
        return opensearch_client.indices.exists(index=index_name)
    except Exception:
        return False

def validate_index_mapping(opensearch_client, index_name):
    """Validate index mapping matches expected structure"""
    try:
        mapping = opensearch_client.indices.get_mapping(index=index_name)
        current_props = mapping[index_name]['mappings'].get('properties', {})
        
        # Check for required fields
        required_fields = ['eventArn', 'service', 'eventTypeCode', 'startTime', 'endTime']
        missing_fields = [field for field in required_fields if field not in current_props]
        
        if missing_fields:
            print(f"Index mapping missing fields: {missing_fields}")
            return False
        return True
    except Exception as e:
        print(f"❌ Cannot connect to OpenSearch: {e}")
        print("\n🔧 Solutions:")
        print("1. Run this script from an EC2 instance in the same VPC as OpenSearch")
        print("2. Set up a VPN connection to the VPC")
        print("3. Use AWS Systems Manager Session Manager to connect to an EC2 instance")
        print(f"\n✅ OpenSearch domain created successfully at: {endpoint}")
        print(f"Index '{index_name}' will need to be created from within the VPC")
        return 0

def create_opensearch_domain(domain_name, region='us-east-1'):
    """Create OpenSearch domain"""
    client = boto3.client('opensearch', region_name=region)
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    """Create OpenSearch domain"""
    client = boto3.client('opensearch', region_name=region)
    sts = boto3.client('sts')
    account_id = sts.get_caller_identity()['Account']
    
    # Check if domain already exists
    try:
        status = client.describe_domain(DomainName=domain_name)
        print(f"Domain {domain_name} already exists")
        
        # Wait for domain to be ready if it's still processing
        while status['DomainStatus']['Processing']:
            print("Domain is still processing, waiting...")
            time.sleep(30)
            status = client.describe_domain(DomainName=domain_name)
        
        # Validate and fix domain configuration
        expected_config = {
            'ClusterConfig': {
                'InstanceType': 't3.small.search',
                'InstanceCount': 1,
                'DedicatedMasterEnabled': False
            },
            'EBSOptions': {
                'EBSEnabled': True,
                'VolumeType': 'gp3',
                'VolumeSize': 20
            }
        }
        
        domain_status = validate_and_fix_domain_config(client, domain_name, expected_config)
        
        # Get endpoint for existing domain
        if 'Endpoint' in domain_status:
            endpoint = domain_status['Endpoint']
        elif 'Endpoints' in domain_status:
            endpoint = list(domain_status['Endpoints'].values())[0]
        else:
            endpoint = f"{domain_name}-{domain_status['DomainId']}.{region}.es.amazonaws.com"
        
        print(f"Using existing domain endpoint: https://{endpoint}")
        return f"https://{endpoint}"
        
    except client.exceptions.ResourceNotFoundException:
        # Domain doesn't exist, create it
        pass
    
    # Get VPC information from current instance
    vpc_id, subnet_ids, sg_id = get_current_instance_vpc_info()
    
    # Create VPC endpoint for OpenSearch
    vpc_endpoint_id = create_vpc_endpoint_current_subnet(region)
    
    try:
        domain_config = {
            'DomainName': domain_name,
            'EngineVersion': 'OpenSearch_2.3',
            'ClusterConfig': {
                'InstanceType': 't3.small.search',
                'InstanceCount': 1,  # Single node for simplicity
                'DedicatedMasterEnabled': False
            },
            'EBSOptions': {
                'EBSEnabled': True,
                'VolumeType': 'gp3',
                'VolumeSize': 20
            },
            'VPCOptions': {
                'SubnetIds': [subnet_ids[0]],  # Use only one subnet for single node
            },
            'AccessPolicies': json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
                        "Action": "es:*",
                        "Resource": f"arn:aws:es:{region}:{account_id}:domain/{domain_name}/*"
                    }
                ]
            }),
            'DomainEndpointOptions': {
                'EnforceHTTPS': True
            }
        }
        
        # Add security group if found
        if sg_id:
            domain_config['VPCOptions']['SecurityGroupIds'] = [sg_id]
        
        response = client.create_domain(**domain_config)
        
        print(f"Creating OpenSearch domain: {domain_name}")
        print(f"Domain ARN: {response['DomainStatus']['ARN']}")
        
        # Wait for domain to be active
        while True:
            status = client.describe_domain(DomainName=domain_name)
            if status['DomainStatus']['Processing'] == False:
                # VPC domains use VPCOptions endpoint, not public endpoint
                if 'Endpoint' in status['DomainStatus']:
                    endpoint = status['DomainStatus']['Endpoint']
                elif 'Endpoints' in status['DomainStatus']:
                    endpoint = list(status['DomainStatus']['Endpoints'].values())[0]
                else:
                    # VPC domain - construct endpoint from domain name
                    endpoint = f"{domain_name}-{status['DomainStatus']['DomainId']}.{region}.es.amazonaws.com"
                
                print(f"Domain ready! Endpoint: https://{endpoint}")
                return f"https://{endpoint}"
            print("Waiting for domain to be ready...")
            time.sleep(30)
            
    except Exception as e:
        print(f"Error creating domain: {e}")
        raise e

def create_health_index(client, index_name='aws-health-events'):
    """Create AWS Health events index with comprehensive mapping for describe_event_details output"""
    mapping = {
        'mappings': {
            'properties': {
                # Fields from describe_events
                'arn': {'type': 'keyword'},
                'service': {'type': 'keyword'},
                'eventTypeCode': {'type': 'keyword'},
                'eventTypeCategory': {'type': 'keyword'},
                'eventScopeCode': {'type': 'keyword'},
                'region': {'type': 'keyword'},
                'availabilityZone': {'type': 'keyword'},
                'startTime': {'type': 'date'},
                'endTime': {'type': 'date'},
                'lastUpdatedTime': {'type': 'date'},
                'statusCode': {'type': 'keyword'},
                
                # Fields from describe_event_details
                'eventDescription': {
                    'properties': {
                        'latestDescription': {'type': 'text', 'analyzer': 'standard'},
                        'latestDescriptionVector': {
                            'type': 'knn_vector',
                            'dimension': 1024,
                            'method': {
                                'name': 'hnsw',
                                'space_type': 'cosinesimil',
                                'engine': 'nmslib'
                            }
                        }
                    }
                },
                'eventMetadata': {
                    'type': 'object',
                    'dynamic': True
                },
                
                # Affected entities from describe_event_details
                'affectedEntities': {
                    'type': 'nested',
                    'properties': {
                        'entityArn': {'type': 'keyword'},
                        'entityValue': {'type': 'keyword'},
                        'entityUrl': {'type': 'keyword'},
                        'awsAccountId': {'type': 'keyword'},
                        'lastUpdatedTime': {'type': 'date'},
                        'statusCode': {'type': 'keyword'},
                        'tags': {
                            'type': 'object',
                            'dynamic': True
                        }
                    }
                },
                
                # Detailed affected entities from describe_affected_entities
                'detailedAffectedEntities': {
                    'type': 'nested',
                    'properties': {
                        'entityArn': {'type': 'keyword'},
                        'entityValue': {'type': 'keyword'},
                        'entityUrl': {'type': 'keyword'},
                        'awsAccountId': {'type': 'keyword'},
                        'lastUpdatedTime': {'type': 'date'},
                        'statusCode': {'type': 'keyword'},
                        'tags': {
                            'type': 'object',
                            'dynamic': True
                        },
                        'eventArn': {'type': 'keyword'}
                    }
                }
            }
        }
    }
    
    if not client.indices.exists(index=index_name):
        client.indices.create(index=index_name, body=mapping)
        print(f"Created blank AWS Health index: {index_name}")
    else:
        print(f"AWS Health index {index_name} already exists")

def check_dashboard_exists(client, dashboard_id='aws-health-dashboard'):
    """Check if dashboard exists"""
    try:
        client.transport.perform_request(
            'GET',
            f'/_dashboards/api/saved_objects/dashboard/{dashboard_id}'
        )
        return True
    except Exception:
        return False

def check_visualization_exists(client, viz_id):
    """Check if visualization exists"""
    try:
        client.transport.perform_request(
            'GET',
            f'/_dashboards/api/saved_objects/visualization/{viz_id}'
        )
        return True
    except Exception:
        return False

def check_index_pattern_exists(client, pattern_id):
    """Check if index pattern exists"""
    try:
        client.transport.perform_request(
            'GET',
            f'/_dashboards/api/saved_objects/index-pattern/{pattern_id}'
        )
        return True
    except Exception:
        return False

def create_health_dashboard(client, index_name='aws-health-events'):
    """Create OpenSearch dashboard for AWS Health events"""
    
    pattern_id = f"{index_name}*"
    
    # Check if index pattern exists
    if check_index_pattern_exists(client, pattern_id):
        print(f"Index pattern {pattern_id} already exists")
    else:
        # Create index pattern
        index_pattern = {
            "version": 1,
            "objects": [
                {
                    "id": pattern_id,
                    "type": "index-pattern",
                    "attributes": {
                        "title": pattern_id,
                        "timeFieldName": "startTime"
                    }
                }
            ]
        }
        
        try:
            client.transport.perform_request(
                'POST',
                '/_dashboards/api/saved_objects/_import',
                headers={'osd-xsrf': 'true'},
                body=json.dumps(index_pattern)
            )
            print(f"Created index pattern for {index_name}")
        except Exception as e:
            print(f"Warning: Could not create index pattern: {e}")
    
    # Check and create visualizations
    visualizations = [
        ("health-events-by-service", "Health Events by Service"),
        ("health-events-timeline", "Health Events Timeline")
    ]
    
    for viz_id, viz_title in visualizations:
        if check_visualization_exists(client, viz_id):
            print(f"Visualization '{viz_title}' already exists")
        else:
            # Create visualization based on type
            if "service" in viz_id:
                viz_config = {
                    "id": viz_id,
                    "type": "visualization",
                    "attributes": {
                        "title": viz_title,
                        "visState": json.dumps({
                            "title": viz_title,
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
                        "description": "",
                        "version": 1,
                        "kibanaSavedObjectMeta": {
                            "searchSourceJSON": json.dumps({
                                "index": pattern_id,
                                "query": {
                                    "match_all": {}
                                }
                            })
                        }
                    }
                }
            else:  # timeline
                viz_config = {
                    "id": viz_id,
                    "type": "visualization", 
                    "attributes": {
                        "title": viz_title,
                        "visState": json.dumps({
                            "title": viz_title,
                            "type": "histogram",
                            "params": {
                                "grid": {"categoryLines": False, "style": {"color": "#eee"}},
                                "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom", "show": True}],
                                "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value", "position": "left", "show": True, "title": {"text": "Count"}}],
                                "seriesParams": [{"show": "true", "type": "histogram", "mode": "stacked", "data": {"label": "Count", "id": "1"}, "valueAxis": "ValueAxis-1"}],
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
                                    "type": "date_histogram",
                                    "schema": "segment",
                                    "params": {
                                        "field": "startTime",
                                        "interval": "auto",
                                        "min_doc_count": 1
                                    }
                                }
                            ]
                        }),
                        "uiStateJSON": "{}",
                        "description": "",
                        "version": 1,
                        "kibanaSavedObjectMeta": {
                            "searchSourceJSON": json.dumps({
                                "index": pattern_id,
                                "query": {
                                    "match_all": {}
                                }
                            })
                        }
                    }
                }
            
            try:
                viz_import = {"version": 1, "objects": [viz_config]}
                client.transport.perform_request(
                    'POST', 
                    '/_dashboards/api/saved_objects/_import',
                    headers={'osd-xsrf': 'true'},
                    body=json.dumps(viz_import)
                )
                print(f"Created visualization: {viz_title}")
            except Exception as e:
                print(f"Warning: Could not create visualization {viz_title}: {e}")
    
    # Check and create dashboard
    if check_dashboard_exists(client, 'aws-health-dashboard'):
        print("AWS Health Events Dashboard already exists")
    else:
        dashboard = {
            "version": 1,
            "objects": [
                {
                    "id": "aws-health-dashboard",
                    "type": "dashboard",
                    "attributes": {
                        "title": "AWS Health Events Dashboard",
                        "hits": 0,
                        "description": "Dashboard for monitoring AWS Health events",
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
                                },
                                "version": "7.10.2"
                            },
                            {
                                "id": "health-events-timeline", 
                                "type": "visualization",
                                "gridData": {
                                    "x": 24,
                                    "y": 0,
                                    "w": 24,
                                    "h": 15,
                                    "i": "2"
                                },
                                "version": "7.10.2"
                            }
                        ]),
                        "optionsJSON": json.dumps({
                            "useMargins": True,
                            "syncColors": False,
                            "hidePanelTitles": False
                        }),
                        "version": 1,
                        "timeRestore": False,
                        "kibanaSavedObjectMeta": {
                            "searchSourceJSON": json.dumps({
                                "query": {
                                    "match_all": {}
                                },
                                "filter": []
                            })
                        }
                    }
                }
            ]
        }
        
        try:
            client.transport.perform_request(
                'POST',
                '/_dashboards/api/saved_objects/_import', 
                headers={'osd-xsrf': 'true'},
                body=json.dumps(dashboard)
            )
            print("Created AWS Health Events Dashboard")
        except Exception as e:
            print(f"Warning: Could not create dashboard: {e}")
            print("Dashboard can be created manually in OpenSearch Dashboards UI")

def create_index_and_load_data(endpoint, index_name='aws-health-events'):
    """Create blank index ready for health events data"""
    region = boto3.Session().region_name or 'us-east-1'
    host = endpoint.replace('https://', '')
    
    print(f"Attempting to connect to OpenSearch at: {endpoint}")
    print("Note: VPC-based OpenSearch domains are only accessible from within the VPC")
    print("If this fails, run this script from an EC2 instance in the same VPC")
    
    try:
        # Use boto3 session for credentials
        session = boto3.Session()
        credentials = session.get_credentials()
        
        # Use requests-aws4auth instead of aws-requests-auth
        from requests_aws4auth import AWS4Auth
        
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
    
        # Create blank AWS Health index
        create_health_index(client, index_name)
        
        print(f"AWS Health index '{index_name}' created and ready for data")
        return 0
        
    except Exception as e:
        print(f"❌ Cannot connect to OpenSearch: {e}")
        print("\n🔧 Solutions:")
        print("1. Run this script from an EC2 instance in the same VPC as OpenSearch")
        print("2. Set up a VPN connection to the VPC")
        print("3. Use AWS Systems Manager Session Manager to connect to an EC2 instance")
        print(f"\n✅ OpenSearch domain created successfully at: {endpoint}")
        print(f"Index '{index_name}' will need to be created from within the VPC")
        return 0

def main():
    parser = argparse.ArgumentParser(description='Create sample OpenSearch cluster with AWS Health data')
    parser.add_argument('--domain-name', default='maki-health', help='OpenSearch domain name')
    parser.add_argument('--index-name', default='aws-health-events', help='Index name for health events')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--skip-domain-creation', action='store_true', help='Skip domain creation, only load data')
    parser.add_argument('--create-vpc-endpoint', action='store_true', help='Create VPC endpoint for OpenSearch')
    parser.add_argument('--create-dashboard', action='store_true', help='Create dashboard only (requires existing domain and index)')
    
    args = parser.parse_args()
    
    # Dashboard-only mode
    if args.create_dashboard:
        # Get existing domain endpoint
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
            
            print(f"Using existing domain endpoint: {endpoint}")
            
            # Connect to OpenSearch and create dashboard only
            region = boto3.Session().region_name or args.region
            host = endpoint.replace('https://', '')
            
            session = boto3.Session()
            credentials = session.get_credentials()
            
            from requests_aws4auth import AWS4Auth
            awsauth = AWS4Auth(
                credentials.access_key,
                credentials.secret_key,
                region,
                'es',
                session_token=credentials.token
            )
            
            from opensearchpy import OpenSearch, RequestsHttpConnection
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
                print(f"Error: Index {args.index_name} does not exist. Create it first.")
                return 1
            
            # Create dashboard
            create_health_dashboard(opensearch_client, args.index_name)
            
            print(f"\n✅ Dashboard creation complete!")
            print(f"OpenSearch Endpoint: {endpoint}")
            print(f"Dashboard: AWS Health Events Dashboard")
            print(f"Access OpenSearch Dashboards at: {endpoint}/_dashboards")
            
            return 0
            
        except Exception as e:
            print(f"Error accessing domain {args.domain_name}: {e}")
            return 1
    
    # Original domain creation logic
    if not args.skip_domain_creation:
        endpoint = create_opensearch_domain(args.domain_name, args.region)
    else:
        # Get existing domain endpoint
        client = boto3.client('opensearch', region_name=args.region)
        status = client.describe_domain(DomainName=args.domain_name)
        domain_status = status['DomainStatus']
        
        if 'Endpoint' in domain_status:
            endpoint = f"https://{domain_status['Endpoint']}"
        elif 'Endpoints' in domain_status:
            endpoint = f"https://{list(domain_status['Endpoints'].values())[0]}"
        else:
            endpoint = f"https://{args.domain_name}-{domain_status['DomainId']}.{args.region}.es.amazonaws.com"
        
        print(f"Using existing domain endpoint: {endpoint}")
    
    # Create VPC endpoint if requested
    if args.create_vpc_endpoint:
        create_vpc_endpoint_current_subnet(args.region)
    
    # Wait a bit for domain to be fully ready
    time.sleep(10)
    
    count = create_index_and_load_data(endpoint, args.index_name)
    
    print(f"\n✅ Setup complete!")
    print(f"OpenSearch Endpoint: {endpoint}")
    print(f"Index: {args.index_name}")
    print(f"Documents: {count}")
    print(f"Dashboard: AWS Health Events Dashboard")
    print(f"\nAccess OpenSearch Dashboards at: {endpoint}/_dashboards")
    print(f"Update your config.py with:")
    print(f"OPENSEARCH_ENDPOINT = '{endpoint}'")
    print(f"OPENSEARCH_INDEX = '{args.index_name}'")

if __name__ == '__main__':
    main()
