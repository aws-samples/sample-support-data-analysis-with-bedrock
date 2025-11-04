"""
MAKI Trusted Advisor Data Retrieval Handler

This Lambda function retrieves AWS Trusted Advisor recommendations from the Support API
and prepares them for analysis by Amazon Bedrock. It serves as the data ingestion
component for the Trusted Advisor processing mode.

Purpose:
- Retrieve Trusted Advisor recommendations from AWS Support API
- Filter and process recommendations for analysis
- Generate Bedrock-compatible prompts for each recommendation
- Store processed data in S3 for batch or on-demand processing

Key Features:
- Support API integration for Trusted Advisor data
- Recommendation filtering by status and category
- Bedrock prompt generation with structured analysis framework
- S3 file management with organized storage structure
- Error handling and retry mechanisms
- Support for both English and localized recommendations

Processing Flow:
1. Query Support API for Trusted Advisor checks
2. Retrieve detailed recommendation data for each check
3. Filter recommendations based on status and relevance
4. Generate structured Bedrock prompts for analysis
5. Store individual recommendation files in S3
6. Return summary of processed recommendations

Environment Variables:
- S3_INPUT: Input bucket for storing recommendation files
- BEDROCK_TEXT_MODEL: Bedrock model ID for inference
- BEDROCK_CATEGORIZE_TEMPERATURE: Temperature for analysis

Input Event Structure:
- mode: Processing mode (should be 'trusted_advisor')
- language: Language preference for recommendations (default: 'en')

Output Structure:
- eventsTotal: Total number of recommendations processed
- events: List of S3 keys for individual recommendation files
- ondemand_run_datetime: Timestamp for processing organization

Trusted Advisor Categories:
- Cost Optimization: Recommendations to reduce costs
- Security: Security-related recommendations
- Fault Tolerance: Availability and resilience recommendations
- Performance: Performance optimization recommendations
- Service Limits: Service quota and limit recommendations

API Requirements:
- AWS Business or Enterprise Support plan for full Trusted Advisor access
- Support API permissions for describe_trusted_advisor_checks
- Support API permissions for describe_trusted_advisor_check_result
"""

import sys
sys.path.append('/opt')

import boto3
import json
import os
from datetime import datetime
from botocore.exceptions import ClientError

from s3 import store_data

def handler(event, context):
    
    print(f"boto3 version: {boto3.__version__}")
    
    # Get environment variables
    input_s3 = os.environ['S3_INPUT']
    model_id = os.environ['BEDROCK_TEXT_MODEL']
    temperature = float(os.environ['BEDROCK_CATEGORIZE_TEMPERATURE'])
    
    # Get language preference from event (default to English)
    language = event.get('language', 'en')
    
    # Initialize clients
    support_client = boto3.client('support', region_name='us-east-1')  # Support API only available in us-east-1
    
    try:
        print("Retrieving Trusted Advisor checks...")
        
        # Get all available Trusted Advisor checks
        checks_response = support_client.describe_trusted_advisor_checks(language=language)
        checks = checks_response['checks']
        
        print(f"Found {len(checks)} Trusted Advisor checks")
        
        # Filter checks by category (focus on actionable recommendations)
        target_categories = [
            'cost_optimizing',
            'security', 
            'fault_tolerance',
            'performance',
            'service_limits'
        ]
        
        filtered_checks = [
            check for check in checks 
            if check['category'] in target_categories
        ]
        
        print(f"Filtered to {len(filtered_checks)} checks in target categories")
        
        # Get detailed results for each check
        recommendations = []
        processed_count = 0
        
        for check in filtered_checks:
            check_id = check['id']
            check_name = check['name']
            category = check['category']
            
            try:
                # Get detailed check result
                result_response = support_client.describe_trusted_advisor_check_result(
                    checkId=check_id,
                    language=language
                )
                
                result = result_response['result']
                status = result['status']
                
                # Only process checks with actionable recommendations
                if status in ['warning', 'error']:
                    recommendation_data = {
                        'checkId': check_id,
                        'checkName': check_name,
                        'category': category,
                        'status': status,
                        'timestamp': result['timestamp'],
                        'resourcesSummary': result.get('resourcesSummary', {}),
                        'categorySpecificSummary': result.get('categorySpecificSummary', {}),
                        'flaggedResources': result.get('flaggedResources', [])
                    }
                    
                    # Add metadata
                    if 'metadata' in check:
                        recommendation_data['metadata'] = check['metadata']
                    
                    recommendations.append(recommendation_data)
                    processed_count += 1
                    
                    print(f"Processed check: {check_name} (Status: {status})")
                
            except ClientError as e:
                print(f"Error retrieving check result for {check_name}: {e}")
                continue
        
        print(f"Retrieved {len(recommendations)} actionable recommendations")
        
        # Generate timestamp for this run
        ondemand_run_datetime = datetime.now().strftime("%Y%m%d-%H%M%S")
        
        # Process each recommendation and create Bedrock prompts
        events = []
        
        for i, recommendation in enumerate(recommendations):
            # Generate structured prompt for Bedrock analysis
            system_prompt = generate_trusted_advisor_system_prompt()
            user_prompt = generate_trusted_advisor_user_prompt(recommendation)
            
            # Create Bedrock input structure
            bedrock_input = {
                "modelInput": {
                    "system": system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": user_prompt}]
                        }
                    ],
                    "inferenceConfig": {
                        "temperature": temperature
                    }
                }
            }
            
            # Store in S3
            file_key = f"trusted_advisor_{recommendation['checkId']}_{i+1}.jsonl"
            store_data(json.dumps(bedrock_input), input_s3, file_key)
            events.append(file_key)
            
            print(f"Stored recommendation {i+1}: {file_key}")
        
        print(f"Successfully processed {len(events)} Trusted Advisor recommendations")
        
        return {
            'eventsTotal': len(events),
            'events': events,
            'ondemand_run_datetime': ondemand_run_datetime,
            'mode': 'trusted_advisor'
        }
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'SubscriptionRequiredException':
            print("Error: Trusted Advisor API requires Business or Enterprise support plan")
            return {
                'eventsTotal': 0,
                'events': [],
                'error': 'Business or Enterprise support plan required for Trusted Advisor API access'
            }
        else:
            print(f"Error querying Trusted Advisor API: {e}")
            raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

def generate_trusted_advisor_system_prompt():
    """Generate system prompt for Trusted Advisor recommendation analysis"""
    return """You are an AWS technical account manager and cloud optimization expert. 
    You will analyze AWS Trusted Advisor recommendations to provide actionable insights for customers.
    
    Your analysis should focus on:
    1. Understanding the specific optimization opportunity or issue
    2. Assessing the potential impact (cost savings, security improvement, performance gain)
    3. Providing clear, actionable recommendations
    4. Prioritizing recommendations based on impact and effort
    5. Explaining the business value of implementing the recommendation
    
    Always provide practical, implementable advice that considers real-world constraints and customer context."""

def generate_trusted_advisor_user_prompt(recommendation):
    """Generate user prompt for specific Trusted Advisor recommendation"""
    
    # Extract key information
    check_name = recommendation.get('checkName', 'Unknown Check')
    category = recommendation.get('category', 'Unknown Category')
    status = recommendation.get('status', 'Unknown Status')
    resources_summary = recommendation.get('resourcesSummary', {})
    flagged_resources = recommendation.get('flaggedResources', [])
    
    # Define output format
    output_format = """{ 
"checkId": "checkId", 
"checkName": "checkName", 
"category": "category", 
"status": "status", 
"priority": "High|Medium|Low", 
"estimatedImpact": "estimatedImpact", 
"recommendation_summary": "recommendation_summary", 
"actionable_steps": "actionable_steps", 
"implementation_effort": "implementation_effort", 
"expected_benefits": "expected_benefits" 
}"""
    
    # Build comprehensive prompt
    prompt = f"""Analyze this AWS Trusted Advisor recommendation:

Check Name: {check_name}
Category: {category}
Status: {status}

Resources Summary:
{json.dumps(resources_summary, indent=2)}

Number of Flagged Resources: {len(flagged_resources)}

"""
    
    # Add sample of flagged resources if available
    if flagged_resources:
        prompt += "Sample Flagged Resources:\n"
        # Include up to 3 sample resources to avoid prompt length issues
        for i, resource in enumerate(flagged_resources[:3]):
            prompt += f"Resource {i+1}: {json.dumps(resource, indent=2)}\n"
        
        if len(flagged_resources) > 3:
            prompt += f"... and {len(flagged_resources) - 3} more resources\n"
    
    prompt += f"""
Please provide a comprehensive analysis in the following JSON format:
{output_format}

Focus on:
1. Clear explanation of the issue or opportunity
2. Potential impact (cost, security, performance, availability)
3. Specific actionable recommendations
4. Implementation priority and effort level
5. Expected benefits of remediation"""
    
    return prompt