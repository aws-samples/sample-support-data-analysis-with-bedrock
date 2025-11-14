#!/usr/bin/env python3
"""
MAKI AWS Trusted Advisor Recommendations Collector

This tool queries the AWS Support API to retrieve Trusted Advisor recommendations 
and processes them for MAKI analysis. It serves as the primary data collection tool 
for Trusted Advisor processing mode.

Purpose:
- Collect actionable Trusted Advisor recommendations from the Support API
- Filter recommendations by category and status
- Generate structured data for MAKI processing
- Support both file output and direct processing

Data Collection Scope:
- Cost Optimization recommendations
- Security recommendations  
- Fault Tolerance recommendations
- Performance recommendations
- Service Limits recommendations
- Only actionable recommendations (warning/error status)

Usage:
    python tools/get_trusted_advisor_recommendations.py                    # Process for MAKI
    python tools/get_trusted_advisor_recommendations.py --output-dir ./ta_data  # Save to files
    python tools/get_trusted_advisor_recommendations.py --verbose         # Show detailed output

Requirements:
- AWS Business or Enterprise Support plan for full Trusted Advisor access
- Support API permissions for describe_trusted_advisor_checks
- Support API permissions for describe_trusted_advisor_check_result

Key Features:
- Automatic filtering of actionable recommendations
- Category-based organization
- Comprehensive error handling and progress reporting
- Support for both processing and file export
- Language support for localized recommendations
"""

import boto3
import json
import argparse
import os
import sys
from datetime import datetime
from botocore.exceptions import ClientError

# Add paths for config.py - handle both tools/ and root directory execution
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(current_dir) == 'tools':
    # Running from tools directory
    sys.path.append(os.path.dirname(current_dir))
else:
    # Running from root directory
    sys.path.append(current_dir)

import config

def write_to_files(recommendations, output_dir, verbose=False):
    """Write Trusted Advisor recommendations to JSON files in specified directory"""
    try:
        os.makedirs(output_dir, exist_ok=True)
        
        # Process and write each recommendation
        written_count = 0
        for recommendation in recommendations:
            check_id = recommendation['checkId']
            check_name = recommendation['checkName'].replace('/', '_').replace(' ', '_')
            
            # Write to file
            filename = f"{check_id}_{check_name}.json"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(recommendation, f, indent=2, default=str)
            
            written_count += 1
            
            if verbose:
                print(f"Written recommendation to: {filepath}")
        
        print(f"Written {written_count} Trusted Advisor recommendations to directory: {output_dir}")
        
    except Exception as e:
        print(f"Error writing to files: {e}")

def get_trusted_advisor_recommendations(language='en', verbose=False, output_dir=None):
    """Query AWS Support API for Trusted Advisor recommendations"""
    
    # Show current identity
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"Current AWS identity: {identity['Arn']}")
    except Exception as e:
        print(f"Could not determine current identity: {e}")
    
    try:
        # Initialize Support client (only available in us-east-1)
        support_client = boto3.client('support', region_name='us-east-1')
        
        print(f"Querying AWS Trusted Advisor checks (language: {language})...")
        
        # Get all available Trusted Advisor checks
        checks_response = support_client.describe_trusted_advisor_checks(language=language)
        checks = checks_response['checks']
        
        print(f"Found {len(checks)} total Trusted Advisor checks")
        
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
        
        print(f"Filtered to {len(filtered_checks)} checks in target categories: {', '.join(target_categories)}")
        
        # Get detailed results for each check
        recommendations = []
        category_counts = {}
        status_counts = {}
        
        for check in filtered_checks:
            check_id = check['id']
            check_name = check['name']
            category = check['category']
            
            if verbose:
                print(f"Processing check: {check_name}")
                print(f"  ID: {check_id}")
                print(f"  Category: {category}")
            
            try:
                # Get detailed check result
                result_response = support_client.describe_trusted_advisor_check_result(
                    checkId=check_id,
                    language=language
                )
                
                result = result_response['result']
                status = result['status']
                
                if verbose:
                    print(f"  Status: {status}")
                    print(f"  Resources Summary: {result.get('resourcesSummary', {})}")
                
                # Count by status
                status_counts[status] = status_counts.get(status, 0) + 1
                
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
                    
                    # Add metadata if available
                    if 'metadata' in check:
                        recommendation_data['metadata'] = check['metadata']
                    
                    recommendations.append(recommendation_data)
                    
                    # Count by category
                    category_counts[category] = category_counts.get(category, 0) + 1
                    
                    if verbose:
                        print(f"  ✓ Added actionable recommendation")
                        print(f"  Flagged Resources: {len(recommendation_data['flaggedResources'])}")
                        print()
                elif verbose:
                    print(f"  - Skipped (status: {status})")
                    print()
                
            except ClientError as e:
                print(f"Error retrieving check result for {check_name}: {e}")
                continue
        
        # Summary report
        print(f"\n=== COLLECTION SUMMARY ===")
        print(f"Total checks processed: {len(filtered_checks)}")
        print(f"Actionable recommendations found: {len(recommendations)}")
        
        if status_counts:
            print(f"\n=== BY STATUS ===")
            for status, count in sorted(status_counts.items()):
                print(f"{status}: {count} checks")
        
        if category_counts:
            print(f"\n=== ACTIONABLE BY CATEGORY ===")
            for category, count in sorted(category_counts.items()):
                print(f"{category}: {count} recommendations")
        
        # Output to files if requested
        if output_dir:
            write_to_files(recommendations, output_dir, verbose)
        else:
            print(f"\nCollected {len(recommendations)} actionable Trusted Advisor recommendations")
            print("Use --output-dir to save recommendations to files")
        
        return recommendations
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'SubscriptionRequiredException':
            print("Error: Trusted Advisor API requires Business or Enterprise support plan")
            print("Basic support plan only provides access to a limited set of checks")
        else:
            print(f"Error querying Trusted Advisor API: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []

def redact_sensitive_info(recommendation):
    """Redact sensitive information from recommendation for display"""
    redacted = recommendation.copy()
    
    # Redact flagged resources to remove sensitive identifiers
    if 'flaggedResources' in redacted:
        redacted_resources = []
        for resource in redacted['flaggedResources'][:2]:  # Show max 2 examples
            redacted_resource = resource.copy()
            if 'resourceId' in redacted_resource:
                redacted_resource['resourceId'] = 'REDACTED'
            if 'metadata' in redacted_resource:
                # Keep structure but redact potential ARNs/IDs
                redacted_resource['metadata'] = ['REDACTED' if isinstance(item, str) and 
                    ('arn:' in item.lower() or len(item) > 20) else item 
                    for item in redacted_resource['metadata']]
            redacted_resources.append(redacted_resource)
        
        if len(redacted['flaggedResources']) > 2:
            redacted_resources.append(f"... and {len(redacted['flaggedResources']) - 2} more resources")
        
        redacted['flaggedResources'] = redacted_resources
    
    return redacted

def main():
    parser = argparse.ArgumentParser(description='Query AWS Trusted Advisor API and collect actionable recommendations')
    parser.add_argument('--language', default='en', help='Language for recommendations (default: en)')
    parser.add_argument('--verbose', action='store_true', help='Show detailed output for each recommendation retrieved')
    parser.add_argument('--output-dir', help='Write JSON files to directory instead of just collecting data')
    
    args = parser.parse_args()
    
    recommendations = get_trusted_advisor_recommendations(args.language, args.verbose, args.output_dir)
    
    if recommendations and not args.output_dir:
        print(f"\nSample recommendation structure (keys only for security):")
        sample_keys = list(recommendations[0].keys())
        print(f"Top-level fields: {sample_keys}")
        print("Note: Detailed content omitted to prevent exposure of sensitive resource identifiers.")
        print("Use --output-dir to save full data to files for processing.")

if __name__ == '__main__':
    main()