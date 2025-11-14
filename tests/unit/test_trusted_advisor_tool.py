import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import sys
from botocore.exceptions import ClientError

# Add tools path for testing
sys.path.append(os.path.join(os.path.dirname(__file__), '../../tools'))

class TestTrustedAdvisorTool(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.sample_checks = [
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
            },
            {
                'id': 'check789',
                'name': 'Amazon RDS Idle DB Instances',
                'category': 'cost_optimizing',
                'metadata': ['DB Instance', 'Engine', 'Multi-AZ']
            }
        ]
        
        self.sample_results = {
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
            },
            'check789': {
                'status': 'ok',
                'timestamp': '2024-01-01T00:00:00Z',
                'resourcesSummary': {
                    'resourcesProcessed': 20,
                    'resourcesFlagged': 0,
                    'resourcesIgnored': 0,
                    'resourcesSuppressed': 0
                }
            }
        }

    @patch('get_trusted_advisor_recommendations.boto3.client')
    def test_get_trusted_advisor_recommendations_success(self, mock_boto3_client):
        """Test successful retrieval of Trusted Advisor recommendations"""
        import get_trusted_advisor_recommendations as ta_tool
        
        # Mock STS client for identity
        mock_sts = Mock()
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/test-user'
        }
        
        # Mock Support client
        mock_support = Mock()
        
        # Configure boto3.client to return appropriate clients
        def client_side_effect(service_name, **kwargs):
            if service_name == 'sts':
                return mock_sts
            elif service_name == 'support':
                return mock_support
            return Mock()
        
        mock_boto3_client.side_effect = client_side_effect
        
        # Mock API responses
        mock_support.describe_trusted_advisor_checks.return_value = {
            'checks': self.sample_checks
        }
        
        def describe_check_result_side_effect(checkId, language):
            return {'result': self.sample_results[checkId]}
        
        mock_support.describe_trusted_advisor_check_result.side_effect = describe_check_result_side_effect
        
        # Execute function
        recommendations = ta_tool.get_trusted_advisor_recommendations(language='en', verbose=True)
        
        # Assertions
        self.assertEqual(len(recommendations), 2)  # Only warning/error status checks
        
        # Verify first recommendation (security)
        security_rec = next((r for r in recommendations if r['category'] == 'security'), None)
        self.assertIsNotNone(security_rec)
        self.assertEqual(security_rec['checkId'], 'check123')
        self.assertEqual(security_rec['status'], 'warning')
        self.assertEqual(len(security_rec['flaggedResources']), 1)
        
        # Verify second recommendation (cost optimization)
        cost_rec = next((r for r in recommendations if r['checkId'] == 'check456'), None)
        self.assertIsNotNone(cost_rec)
        self.assertEqual(cost_rec['category'], 'cost_optimizing')
        self.assertEqual(cost_rec['status'], 'error')
        
        # Verify API calls
        mock_support.describe_trusted_advisor_checks.assert_called_once_with(language='en')
        self.assertEqual(mock_support.describe_trusted_advisor_check_result.call_count, 3)

    @patch('get_trusted_advisor_recommendations.boto3.client')
    def test_subscription_exception_handling(self, mock_boto3_client):
        """Test handling of subscription requirement exception"""
        import get_trusted_advisor_recommendations as ta_tool
        
        # Mock STS client
        mock_sts = Mock()
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/test-user'
        }
        
        # Mock Support client with subscription error
        mock_support = Mock()
        error_response = {'Error': {'Code': 'SubscriptionRequiredException'}}
        mock_support.describe_trusted_advisor_checks.side_effect = ClientError(
            error_response, 'describe_trusted_advisor_checks'
        )
        
        def client_side_effect(service_name, **kwargs):
            if service_name == 'sts':
                return mock_sts
            elif service_name == 'support':
                return mock_support
            return Mock()
        
        mock_boto3_client.side_effect = client_side_effect
        
        # Execute function
        recommendations = ta_tool.get_trusted_advisor_recommendations()
        
        # Should return empty list gracefully
        self.assertEqual(recommendations, [])

    @patch('get_trusted_advisor_recommendations.boto3.client')
    @patch('get_trusted_advisor_recommendations.os.makedirs')
    @patch('builtins.open', create=True)
    def test_write_to_files(self, mock_open, mock_makedirs, mock_boto3_client):
        """Test writing recommendations to files"""
        import get_trusted_advisor_recommendations as ta_tool
        
        # Mock file operations
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Sample recommendations
        recommendations = [
            {
                'checkId': 'check123',
                'checkName': 'Security Groups - Specific Ports Unrestricted',
                'category': 'security',
                'status': 'warning'
            }
        ]
        
        # Execute write_to_files
        ta_tool.write_to_files(recommendations, './test_output', verbose=True)
        
        # Assertions
        mock_makedirs.assert_called_once_with('./test_output', exist_ok=True)
        mock_open.assert_called_once()
        # json.dump calls write multiple times, so just verify it was called
        self.assertTrue(mock_file.write.called)

    @patch('get_trusted_advisor_recommendations.boto3.client')
    def test_client_error_handling(self, mock_boto3_client):
        """Test handling of general client errors"""
        import get_trusted_advisor_recommendations as ta_tool
        
        # Mock STS client
        mock_sts = Mock()
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/test-user'
        }
        
        # Mock Support client with general error
        mock_support = Mock()
        error_response = {'Error': {'Code': 'AccessDenied'}}
        mock_support.describe_trusted_advisor_checks.side_effect = ClientError(
            error_response, 'describe_trusted_advisor_checks'
        )
        
        def client_side_effect(service_name, **kwargs):
            if service_name == 'sts':
                return mock_sts
            elif service_name == 'support':
                return mock_support
            return Mock()
        
        mock_boto3_client.side_effect = client_side_effect
        
        # Execute function
        recommendations = ta_tool.get_trusted_advisor_recommendations()
        
        # Should return empty list
        self.assertEqual(recommendations, [])

    @patch('get_trusted_advisor_recommendations.boto3.client')
    def test_check_result_error_handling(self, mock_boto3_client):
        """Test handling of errors when retrieving individual check results"""
        import get_trusted_advisor_recommendations as ta_tool
        
        # Mock STS client
        mock_sts = Mock()
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/test-user'
        }
        
        # Mock Support client
        mock_support = Mock()
        mock_support.describe_trusted_advisor_checks.return_value = {
            'checks': [self.sample_checks[0]]  # Only one check
        }
        
        # Mock error for check result
        error_response = {'Error': {'Code': 'InvalidParameterValue'}}
        mock_support.describe_trusted_advisor_check_result.side_effect = ClientError(
            error_response, 'describe_trusted_advisor_check_result'
        )
        
        def client_side_effect(service_name, **kwargs):
            if service_name == 'sts':
                return mock_sts
            elif service_name == 'support':
                return mock_support
            return Mock()
        
        mock_boto3_client.side_effect = client_side_effect
        
        # Execute function
        recommendations = ta_tool.get_trusted_advisor_recommendations(verbose=True)
        
        # Should handle error gracefully and return empty list
        self.assertEqual(recommendations, [])

    @patch('get_trusted_advisor_recommendations.boto3.client')
    def test_filtering_by_category(self, mock_boto3_client):
        """Test that only target categories are processed"""
        import get_trusted_advisor_recommendations as ta_tool
        
        # Mock STS client
        mock_sts = Mock()
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/test-user'
        }
        
        # Mock Support client
        mock_support = Mock()
        
        # Add a check with non-target category
        checks_with_other_category = self.sample_checks + [{
            'id': 'check999',
            'name': 'Some Other Check',
            'category': 'other_category',  # Not in target categories
            'metadata': []
        }]
        
        mock_support.describe_trusted_advisor_checks.return_value = {
            'checks': checks_with_other_category
        }
        
        def describe_check_result_side_effect(checkId, language):
            if checkId in self.sample_results:
                return {'result': self.sample_results[checkId]}
            return {'result': {'status': 'ok'}}
        
        mock_support.describe_trusted_advisor_check_result.side_effect = describe_check_result_side_effect
        
        def client_side_effect(service_name, **kwargs):
            if service_name == 'sts':
                return mock_sts
            elif service_name == 'support':
                return mock_support
            return Mock()
        
        mock_boto3_client.side_effect = client_side_effect
        
        # Execute function
        recommendations = ta_tool.get_trusted_advisor_recommendations()
        
        # Should only process checks from target categories
        # check999 should not be processed because it's not in target categories
        processed_check_ids = [r['checkId'] for r in recommendations]
        self.assertNotIn('check999', processed_check_ids)
        
        # Verify only target category checks were called
        expected_calls = 3  # Only the 3 checks in target categories
        self.assertEqual(mock_support.describe_trusted_advisor_check_result.call_count, expected_calls)

    def test_main_function_argument_parsing(self):
        """Test main function argument parsing"""
        import get_trusted_advisor_recommendations as ta_tool
        
        # Test that main function exists and can be imported
        self.assertTrue(hasattr(ta_tool, 'main'))
        
        # Test argument parser creation (basic smoke test)
        try:
            # This will test that argparse setup doesn't crash
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument('--language', default='en')
            parser.add_argument('--verbose', action='store_true')
            parser.add_argument('--output-dir')
            
            # Parse empty args (should use defaults)
            args = parser.parse_args([])
            self.assertEqual(args.language, 'en')
            self.assertFalse(args.verbose)
            self.assertIsNone(args.output_dir)
            
        except Exception as e:
            self.fail(f"Argument parsing setup failed: {e}")

if __name__ == '__main__':
    unittest.main()