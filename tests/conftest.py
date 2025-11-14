"""
Test configuration for MAKI Trusted Advisor tests

This file provides common test configuration and fixtures for all MAKI tests,
with specific support for Trusted Advisor functionality testing.
"""

import os
import sys
import pytest
from unittest.mock import Mock

# Add project paths to sys.path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'lambda'))
sys.path.insert(0, os.path.join(project_root, 'tools'))

# Common test fixtures
@pytest.fixture
def mock_aws_credentials():
    """Mock AWS credentials for testing"""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

@pytest.fixture
def mock_trusted_advisor_environment():
    """Mock environment variables for Trusted Advisor tests"""
    env_vars = {
        'S3_INPUT': 'test-input-bucket',
        'S3_OUTPUT': 'test-output-bucket',
        'S3_BATCH_OUTPUT': 'test-batch-output-bucket',
        'S3_REPORT': 'test-report-bucket',
        'S3_ARCHIVE': 'test-archive-bucket',
        'S3_BATCHES': 'test-batches-bucket',
        'BEDROCK_TEXT_MODEL': 'anthropic.claude-3-sonnet-20240229-v1:0',
        'BEDROCK_CATEGORIZE_TEMPERATURE': '0.1',
        'BEDROCK_SUMMARY_TEMPERATURE': '0.1',
        'BEDROCK_MAX_TOKENS': '4000',
        'MODEL_ID': 'anthropic.claude-3-sonnet-20240229-v1:0',
        'SUMMARY_OUTPUT_FORMAT': '{"Summary": "", "Plan": ""}'
    }
    
    for key, value in env_vars.items():
        os.environ[key] = value
    
    yield env_vars
    
    # Cleanup
    for key in env_vars.keys():
        os.environ.pop(key, None)

@pytest.fixture
def sample_trusted_advisor_data():
    """Sample Trusted Advisor data for testing"""
    return {
        'checks': [
            {
                'id': 'check123',
                'name': 'Security Groups - Specific Ports Unrestricted',
                'category': 'security',
                'metadata': ['Port', 'Protocol', 'Source IP']
            },
            {
                'id': 'check456',
                'name': 'Low Utilization Amazon EC2 Instances',
                'category': 'cost_optimizing',
                'metadata': ['Instance ID', 'Instance Type', 'Utilization']
            }
        ],
        'results': {
            'check123': {
                'status': 'warning',
                'timestamp': '2024-01-01T00:00:00Z',
                'resourcesSummary': {
                    'resourcesProcessed': 10,
                    'resourcesFlagged': 3,
                    'resourcesIgnored': 0,
                    'resourcesSuppressed': 0
                },
                'flaggedResources': [
                    {
                        'status': 'warning',
                        'resourceId': 'sg-123456',
                        'metadata': ['22', 'tcp', '0.0.0.0/0']
                    }
                ]
            },
            'check456': {
                'status': 'error',
                'timestamp': '2024-01-01T00:00:00Z',
                'resourcesSummary': {
                    'resourcesProcessed': 50,
                    'resourcesFlagged': 5,
                    'resourcesIgnored': 0,
                    'resourcesSuppressed': 0
                },
                'flaggedResources': [
                    {
                        'status': 'error',
                        'resourceId': 'i-123456789',
                        'metadata': ['i-123456789', 't3.large', '5%']
                    }
                ]
            }
        }
    }

@pytest.fixture
def mock_bedrock_response():
    """Mock Bedrock response for testing"""
    return {
        'output': {
            'message': {
                'role': 'assistant',
                'content': [{
                    'text': '{"checkId": "check123", "status": "warning", "recommendation_summary": "Fix security group configuration"}'
                }]
            }
        }
    }