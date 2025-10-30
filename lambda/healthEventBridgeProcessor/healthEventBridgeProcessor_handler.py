"""
MAKI Health Events EventBridge Processor

This Lambda function processes AWS Health events received from EventBridge in real-time,
enriches them with vector embeddings, and stores them in OpenSearch for MAKI analysis.

Purpose:
- Process AWS Health events from EventBridge immediately when they occur
- Enrich events with Bedrock vector embeddings for semantic search
- Store events in OpenSearch Serverless for MAKI processing
- Optionally trigger immediate MAKI analysis for critical events

Key Features:
- Real-time event processing (vs polling)
- Automatic embedding generation for event descriptions
- Deduplication using event ARN as unique identifier
- Integration with existing MAKI OpenSearch storage
- Optional immediate analysis triggering for urgent events

EventBridge Event Structure:
{
    "source": ["aws.health"],
    "detail-type": ["AWS Health Event"],
    "detail": {
        "eventArn": "arn:aws:health:region::event/service/eventTypeCode/...",
        "service": "EC2",
        "eventTypeCode": "AWS_EC2_INSTANCE_REBOOT_MAINTENANCE_SCHEDULED",
        "eventTypeCategory": "scheduledChange",
        "region": "us-east-1",
        "startTime": "2024-01-15T10:00:00Z",
        "endTime": "2024-01-15T12:00:00Z",
        "lastUpdatedTime": "2024-01-15T09:00:00Z",
        "statusCode": "open"
    }
}

Processing Flow:
1. Receive EventBridge health event
2. Extract event details from EventBridge payload
3. Fetch additional details from Health API if needed
4. Generate vector embeddings for event description
5. Store enriched event in OpenSearch
6. Optionally trigger immediate MAKI processing

Environment Variables:
- OPENSEARCH_INDEX: OpenSearch index for health events
- BEDROCK_EMBEDDING_MODEL: Model for generating embeddings
- REGION: AWS region
- STATE_MACHINE_ARN: ARN of MAKI state machine for immediate processing
- IMMEDIATE_PROCESSING: Flag to enable immediate analysis
- LOG_LEVEL: Logging level

Integration Points:
- EventBridge: Receives real-time health events
- Health API: Fetches additional event details
- Bedrock: Generates vector embeddings
- OpenSearch Serverless: Stores enriched events
- Step Functions: Triggers immediate processing (optional)
"""

import json
import os
import sys
import boto3
from datetime import datetime

from botocore.exceptions import ClientError
import logging
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

# Set up logging - force redeploy v2
logger = logging.getLogger()
logger.info("Health EventBridge Processor v2.0 - with opensearch layer")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())



def generate_embedding(text, bedrock_client, region='us-east-1'):
    """Generate embedding using Bedrock model"""
    if not text or not text.strip():
        return None
    
    try:
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })
        
        response = bedrock_client.invoke_model(
            modelId=os.environ['BEDROCK_EMBEDDING_MODEL'],
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['embedding']
        
    except ClientError as e:
        if 'AccessDeniedException' in str(e):
            logger.error(f"Access denied to {os.environ['BEDROCK_EMBEDDING_MODEL']} model")
        return None
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return None

def get_additional_event_details(event_arn, health_client):
    """
    Fetch additional event details from Health API
    
    EventBridge provides basic event info, but we need full details
    including description and affected entities for MAKI processing.
    """
    try:
        # Get detailed event information
        response = health_client.describe_event_details(eventArns=[event_arn])
        event_details = response.get('successfulSet', [])
        
        if not event_details:
            logger.warning(f"No additional details found for event: {event_arn}")
            return None, []
        
        event_detail = event_details[0]
        
        # Get affected entities
        try:
            entities_response = health_client.describe_affected_entities(
                filter={'eventArns': [event_arn]}
            )
            affected_entities = entities_response.get('entities', [])
        except ClientError as e:
            logger.warning(f"Could not fetch entities for {event_arn}: {e}")
            affected_entities = []
        
        return event_detail, affected_entities
        
    except ClientError as e:
        logger.error(f"Error fetching additional details for {event_arn}: {e}")
        return None, []

def get_opensearch_endpoint_from_ssm():
    """Get OpenSearch endpoint from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = boto3.Session().region_name
        response = ssm.get_parameter(Name=f"maki-{account_id}-{region}-opensearch-endpoint")
        return response['Parameter']['Value']
    except Exception as e:
        logger.error(f"Error getting opensearch-endpoint from SSM: {e}")
        raise

def store_event_in_opensearch(event_data, opensearch_endpoint, index_name, region):
    """Store enriched health event in OpenSearch Serverless"""
    try:
        host = opensearch_endpoint.replace('https://', '')
        
        # Use AWSV4SignerAuth for OpenSearch Serverless (same as getHealthFromOpenSearch)
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, region, 'aoss')
        
        client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            timeout=30
        )
        
        # Skip index creation - assume index exists (created by init function or synthetic generator)
        logger.info(f"Indexing event directly to existing index: {index_name}")
        
        # Use event ARN as document ID for deduplication
        event_arn = event_data.get('arn') or event_data.get('eventArn')
        
        # Index the event directly without checking if index exists
        response = client.index(
            index=index_name,
            body=event_data,
            id=event_arn
        )
        
        logger.info(f"Successfully stored event in OpenSearch: {event_arn}")
        return True
        
    except Exception as e:
        logger.error(f"Error storing event in OpenSearch: {e}")
        return False



def should_trigger_immediate_processing(event_data):
    """
    Determine if event should trigger immediate MAKI processing
    
    Criteria for immediate processing:
    - Critical service issues
    - High-impact events
    - Security-related events
    """
    immediate_processing = os.environ.get('IMMEDIATE_PROCESSING', 'false').lower() == 'true'
    
    if not immediate_processing:
        return False
    
    # Get critical services from environment
    critical_services = os.environ.get('CRITICAL_SERVICES', 'EC2,RDS,S3,LAMBDA').split(',')
    
    # Check for critical conditions
    event_type_category = event_data.get('eventTypeCategory', '')
    service = event_data.get('service', '')
    status_code = event_data.get('statusCode', '')
    
    # Trigger immediate processing for:
    # - Active issues (not scheduled changes)
    # - Critical services
    # - Open/ongoing events
    critical_conditions = [
        event_type_category == 'issue',
        service in critical_services,
        status_code == 'open'
    ]
    
    return any(critical_conditions)

def trigger_immediate_maki_processing():
    """Trigger MAKI state machine for immediate processing"""
    try:
        stepfunctions = boto3.client('stepfunctions')
        
        # Start MAKI state machine execution with health mode
        response = stepfunctions.start_execution(
            stateMachineArn=os.environ['STATE_MACHINE_ARN'],
            name=f"health-eventbridge-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            input=json.dumps({
                "mode": "health",
                "trigger": "health-eventbridge",
                "timestamp": datetime.now().isoformat()
            })
        )
        
        logger.info(f"Triggered immediate MAKI processing: {response['executionArn']}")
        return True
        
    except Exception as e:
        logger.error(f"Error triggering immediate MAKI processing: {e}")
        return False

def handler(event, context):
    """
    Main handler for processing AWS Health events from EventBridge
    
    Processes health events in real-time, enriches with embeddings,
    and stores in OpenSearch for MAKI analysis.
    """
    
    logger.info(f"Received EventBridge health event: {json.dumps(event)}")
    
    try:
        # Extract health event details from EventBridge event
        detail = event.get('detail', {})
        
        if not detail:
            logger.error("No detail found in EventBridge event")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No event detail found'})
            }
        
        event_arn = detail.get('eventArn')
        if not event_arn:
            logger.error("No eventArn found in event detail")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No eventArn found'})
            }
        
        logger.info(f"Processing health event: {event_arn}")
        
        # Initialize clients
        bedrock_client = boto3.client('bedrock-runtime', region_name=os.environ['REGION'])
        health_client = boto3.client('health', region_name='us-east-1')  # Health API is global
        
        # Get additional event details from Health API
        event_detail, affected_entities = get_additional_event_details(event_arn, health_client)
        
        # Build comprehensive event data from EventBridge format
        event_data = {
            'arn': event_arn,
            'service': detail.get('service'),
            'eventTypeCode': detail.get('eventTypeCode'),
            'eventTypeCategory': detail.get('eventTypeCategory'),
            'region': detail.get('eventRegion', detail.get('region')),
            'startTime': detail.get('startTime'),
            'endTime': detail.get('endTime'),
            'lastUpdatedTime': detail.get('lastUpdatedTime'),
            'statusCode': detail.get('statusCode'),
            'eventScopeCode': detail.get('eventScopeCode'),
            'communicationId': detail.get('communicationId'),
            'affectedAccount': detail.get('affectedAccount')
        }
        
        # Handle EventBridge eventDescription format (array vs object)
        event_descriptions = detail.get('eventDescription', [])
        if event_descriptions and isinstance(event_descriptions, list):
            latest_desc = event_descriptions[0].get('latestDescription', '')
            event_data['eventDescription'] = {
                'latestDescription': latest_desc
            }
            
            # Generate embedding for description
            if latest_desc:
                embedding = generate_embedding(latest_desc, bedrock_client, os.environ['REGION'])
                if embedding:
                    event_data['eventDescription']['latestDescriptionVector'] = embedding
                    logger.info(f"Generated embedding for event: {event_arn}")
        
        # Add additional details from Health API if available
        if event_detail:
            # Merge with detailed event information
            detailed_event = event_detail.get('event', {})
            # Only update fields that aren't already set from EventBridge
            for key, value in detailed_event.items():
                if key not in event_data or event_data[key] is None:
                    event_data[key] = value
            
            # Add event metadata
            if 'eventMetadata' in event_detail:
                event_data['eventMetadata'] = event_detail['eventMetadata']
        
        # Add affected entities
        event_data['affectedEntities'] = affected_entities
        
        # Add processing metadata
        event_data['processedAt'] = datetime.now().isoformat()
        event_data['processingSource'] = 'eventbridge'
        
        # Ensure we have the ARN field for compatibility
        if 'arn' not in event_data and 'eventArn' in event_data:
            event_data['arn'] = event_data['eventArn']
        
        # Store in OpenSearch for health workflow
        opensearch_endpoint = get_opensearch_endpoint_from_ssm()
        success = store_event_in_opensearch(
            event_data, 
            opensearch_endpoint, 
            os.environ['OPENSEARCH_INDEX'], 
            os.environ['REGION']
        )
        
        if not success:
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to store event in OpenSearch'})
            }
        
        # Check if immediate processing should be triggered
        if should_trigger_immediate_processing(event_data):
            logger.info(f"Triggering immediate processing for critical event: {event_arn}")
            trigger_immediate_maki_processing()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Health event processed successfully',
                'eventArn': event_arn,
                'hasEmbedding': 'latestDescriptionVector' in event_data.get('eventDescription', {}),
                'affectedEntitiesCount': len(affected_entities),
                'immediateProcessing': should_trigger_immediate_processing(event_data)
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing health event: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }