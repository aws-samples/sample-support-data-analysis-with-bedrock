"""
MAKI Resource Naming Utilities

This utility module provides consistent resource naming functions for all MAKI 
infrastructure components, ensuring standardized naming conventions across 
AWS resources deployed by the CDK stacks.

Purpose:
- Generate consistent resource names across all MAKI infrastructure
- Implement standardized naming convention with account and region prefixes
- Ensure unique resource names to avoid conflicts in multi-account/region deployments
- Provide centralized naming logic for maintainability

Key Features:
- Account and region-aware resource naming
- Consistent prefix application using config.KEY
- Support for all MAKI resource types (S3 buckets, Lambda functions, IAM roles, etc.)
- Centralized naming logic for easy maintenance and updates

Functions Provided:
- returnName(type): Generate standardized resource names with MAKI prefix

Naming Convention:
The naming convention follows the pattern: {config.KEY}-{type}
Where:
- config.KEY = "maki-{account_id}-{region}" (e.g., "maki-123456789012-us-east-1")
- type = Resource-specific identifier from config.py constants

Example Usage:
- S3 Buckets: utils.returnName(config.BUCKET_NAME_CASES_AGG_BASE)
  Result: "maki-123456789012-us-east-1-cases-agg"
  
- IAM Roles: utils.returnName(config.EXEC_ROLE)
  Result: "maki-123456789012-us-east-1-exec-role"
  
- Lambda Functions: utils.returnName(config.CHECK_ENABLED_MODELS_NAME_BASE)
  Result: "maki-123456789012-us-east-1-check-enabled-models"

Used Throughout:
- maki/maki_stack.py: S3 bucket names, IAM role ARNs, log groups, SSM parameters
- maki/BuildIAM.py: IAM role names and resource ARNs
- maki/BuildCloudWatch.py: CloudWatch log group names
- maki/BuildLambda.py: Lambda function names and state machine ARNs
- maki/BuildSageMaker.py: SageMaker notebook instance names
- maki/BuildOpenSearch.py: OpenSearch Serverless resource names
- maki/BuildSSM.py: Systems Manager parameter names
- maki/BuildStateMachine.py: Step Functions state machine names
- maki/BuildEventBridge.py: EventBridge rule names

Benefits:
- Prevents resource name conflicts across accounts and regions
- Enables easy identification of MAKI resources in AWS console
- Supports multi-environment deployments (dev, staging, prod)
- Simplifies resource cleanup and management
- Maintains consistency across all infrastructure components

Integration:
- Imports config.py for KEY constant (contains account ID and region)
- Used by all CDK Build*.py modules for resource creation
- Essential for proper resource identification and management
"""

import sys

sys.path.append('..')
import config

def returnName(type):
    return config.KEY + '-' + type