import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import sys
from botocore.exceptions import ClientError

# Add lambda paths for testing
sys.path.append(os.path.join(os.path.dirname(__file__), '../../lambda/getTrustedAdvisorFromAPI'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../lambda/bedrockOnDemandInference'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../lambda/bedrockProcessBatchOutput'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../lambda/layers/prompt_agg_trusted_advisor'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../lambda/layers/s3_utils'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../lambda/layers/prompt_gen_input'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../lambda/layers/json_utils'))

class TestTrustedAdvisorHandlers(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.sample_ta_check = {
            'id': 'check123',
            'name': 'Security Groups - Specific Ports Unrestricted',
            'category': 'security',
            'metadata': ['Port', 'Protocol', 'Source IP']
        }
        
        self.sample_ta_result = {
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
        }

    @patch.dict(os.environ, {
        'S3_INPUT': 'test-input-bucket',
        'BEDROCK_TEXT_MODEL': 'anthropic.claude-3-sonnet-20240229-v1:0',
        'BEDROCK_CATEGORIZE_TEMPERATURE': '0.1'
    })
    @patch('s3.store_data')
    @patch('boto3.client')
    def test_get_trusted_advisor_from_api_success(self, mock_boto3_client, mock_store_data):
        """Test successful Trusted Advisor data retrieval"""
        # Import after setting environment variables and mocking
        import getTrustedAdvisorFromAPI_handler as handler
        
        # Mock Support client
        mock_support = Mock()
        mock_boto3_client.return_value = mock_support
        
        # Mock API responses
        mock_support.describe_trusted_advisor_checks.return_value = {
            'checks': [self.sample_ta_check]
        }
        mock_support.describe_trusted_advisor_check_result.return_value = {
            'result': self.sample_ta_result
        }
        
        # Test event
        event = {'language': 'en'}
        context = {}
        
        # Execute handler
        result = handler.handler(event, context)
        
        # Assertions
        self.assertEqual(result['eventsTotal'], 1)
        self.assertEqual(len(result['events']), 1)
        self.assertIn('ondemand_run_datetime', result)
        self.assertEqual(result['mode'], 'trusted_advisor')
        
        # Verify API calls
        mock_support.describe_trusted_advisor_checks.assert_called_once_with(language='en')
        mock_support.describe_trusted_advisor_check_result.assert_called_once_with(
            checkId='check123', language='en'
        )
        
        # Verify data storage
        mock_store_data.assert_called_once()

    @patch.dict(os.environ, {
        'S3_INPUT': 'test-input-bucket',
        'BEDROCK_TEXT_MODEL': 'anthropic.claude-3-sonnet-20240229-v1:0',
        'BEDROCK_CATEGORIZE_TEMPERATURE': '0.1'
    })
    @patch('s3.store_data')
    @patch('boto3.client')
    def test_get_trusted_advisor_subscription_error(self, mock_boto3_client, mock_store_data):
        """Test handling of subscription requirement error"""
        import getTrustedAdvisorFromAPI_handler as handler
        
        # Mock Support client with subscription error
        mock_support = Mock()
        mock_boto3_client.return_value = mock_support
        
        error_response = {'Error': {'Code': 'SubscriptionRequiredException'}}
        mock_support.describe_trusted_advisor_checks.side_effect = ClientError(
            error_response, 'describe_trusted_advisor_checks'
        )
        
        event = {'language': 'en'}
        context = {}
        
        result = handler.handler(event, context)
        
        # Should handle gracefully
        self.assertEqual(result['eventsTotal'], 0)
        self.assertEqual(result['events'], [])
        self.assertIn('error', result)

    @patch.dict(os.environ, {
        'S3_INPUT': 'test-input-bucket',
        'S3_OUTPUT': 'test-output-bucket',
        'BEDROCK_TEXT_MODEL': 'anthropic.claude-3-sonnet-20240229-v1:0'
    })
    @patch('prompt_gen_input.generate_conversation')
    @patch('s3.get_s3_obj_body')
    @patch('s3.store_data')
    def test_bedrock_ondemand_inference_trusted_advisor(self, mock_store_data, mock_get_s3_obj_body, mock_generate_conversation):
        """Test Bedrock on-demand inference for Trusted Advisor"""
        import bedrockOnDemandInferenceTrustedAdvisor_handler as handler
        
        # Mock S3 data
        mock_bedrock_input = {
            'modelInput': {
                'system': 'You are an AWS expert',
                'messages': [{'role': 'user', 'content': [{'text': 'Analyze this recommendation'}]}],
                'inferenceConfig': {'temperature': 0.1}
            }
        }
        mock_get_s3_obj_body.return_value = json.dumps(mock_bedrock_input)
        
        # Mock Bedrock response
        mock_generate_conversation.return_value = {
            'output': {
                'message': {
                    'role': 'assistant',
                    'content': [{'text': '{"analysis": "recommendation analysis"}'}]
                }
            }
        }
        
        # Test event
        event = {
            'case': 'trusted_advisor_check123_1.jsonl',
            'ondemand_run_datetime': '20240101-120000'
        }
        context = {}
        
        result = handler.handler(event, context)
        
        # Assertions
        self.assertEqual(result['event_file'], 'trusted_advisor_check123_1.jsonl')
        mock_get_s3_obj_body.assert_called_once()
        mock_generate_conversation.assert_called_once()
        mock_store_data.assert_called_once()

    @patch.dict(os.environ, {
        'S3_BATCH_OUTPUT': 'test-batch-output',
        'S3_REPORT': 'test-report-bucket',
        'S3_ARCHIVE': 'test-archive-bucket',
        'S3_BATCHES': 'test-batches-bucket',
        'MODEL_ID': 'anthropic.claude-3-sonnet-20240229-v1:0',
        'BEDROCK_MAX_TOKENS': '4000',
        'BEDROCK_SUMMARY_TEMPERATURE': '0.1',
        'SUMMARY_OUTPUT_FORMAT': '{"Summary": "", "Plan": ""}'
    })
    @patch('validate_jsonl.is_valid_json')
    @patch('s3.list_bucket_object_keys')
    @patch('s3.get_s3_obj_body')
    @patch('prompt_agg_trusted_advisor.aggregate_prompt')
    @patch('s3.store_data')
    @patch('s3.empty_s3_bucket')
    @patch('boto3.client')
    def test_bedrock_process_batch_output_trusted_advisor(self, mock_boto3_client,
                                                         mock_empty_s3_bucket, mock_store_data,
                                                         mock_aggregate_prompt, mock_get_s3_obj_body,
                                                         mock_list_bucket_object_keys, mock_is_valid_json):
        """Test Bedrock batch output processing for Trusted Advisor"""
        import bedrockProcessBatchOutputTrustedAdvisor_handler as handler
        
        # Mock validation function
        mock_is_valid_json.return_value = True
        
        # Mock S3 operations
        mock_list_bucket_object_keys.return_value = ['batch/output1.jsonl.out']
        
        # Mock batch output data
        mock_batch_output = {
            'modelOutput': {
                'output': {
                    'message': {
                        'content': [{
                            'text': '{"checkId": "check123", "status": "warning", "recommendation_summary": "Fix security group"}'
                        }]
                    }
                }
            }
        }
        mock_get_s3_obj_body.return_value = json.dumps(mock_batch_output)
        
        # Mock aggregation result
        mock_aggregate_prompt.return_value = '{"Summary": "Overall optimization summary", "Plan": "Action plan"}'
        
        # Mock S3 client
        mock_s3_client = Mock()
        mock_boto3_client.return_value = mock_s3_client
        
        # Test event
        event = {
            'batchInferenceResult': {
                'batch_jobs': [{
                    'output_s3_uri': 's3://test-batch-output/batch-job-1/'
                }]
            }
        }
        context = {}
        
        result = handler.handler(event, context)
        
        # Assertions
        self.assertIn('summary', result)
        mock_list_bucket_object_keys.assert_called_once()
        mock_get_s3_obj_body.assert_called_once()
        mock_aggregate_prompt.assert_called_once()
        mock_store_data.assert_called_once()
        mock_empty_s3_bucket.assert_called_once()

    @patch('prompt_agg_trusted_advisor.boto3.client')
    def test_trusted_advisor_aggregation_prompt(self, mock_boto3_client):
        """Test Trusted Advisor aggregation prompt functionality"""
        import prompt_agg_trusted_advisor as agg_module
        
        # Mock Bedrock client
        mock_bedrock = Mock()
        mock_boto3_client.return_value = mock_bedrock
        
        # Mock Bedrock response
        mock_bedrock.converse.return_value = {
            'output': {
                'message': {
                    'role': 'assistant',
                    'content': [{
                        'text': '{"Summary": "Customer has multiple optimization opportunities", "Plan": "Implement security and cost optimizations"}'
                    }]
                }
            }
        }
        
        # Test aggregation
        events = """trusted_advisor_recommendation: check123:
status: warning
Fix security groups with unrestricted access

trusted_advisor_recommendation: check456:
status: error
Optimize underutilized EC2 instances
"""
        
        result = agg_module.aggregate_prompt(
            model_id_input='anthropic.claude-3-sonnet-20240229-v1:0',
            events=events,
            temperature='0.1',
            summary_output_format={"Summary": "", "Plan": ""},
            max_tokens='4000'
        )
        
        # Assertions
        self.assertIn('Summary', result)
        self.assertIn('Plan', result)
        mock_bedrock.converse.assert_called_once()

    @patch('s3.store_data')
    def test_trusted_advisor_system_prompt_generation(self, mock_store_data):
        """Test system prompt generation for Trusted Advisor"""
        import getTrustedAdvisorFromAPI_handler as handler
        
        system_prompt = handler.generate_trusted_advisor_system_prompt()
        
        # Verify key elements in system prompt
        self.assertIn('technical account manager', system_prompt)
        self.assertIn('optimization', system_prompt)
        self.assertIn('actionable', system_prompt)
        self.assertIn('business value', system_prompt)

    @patch('s3.store_data')
    def test_trusted_advisor_user_prompt_generation(self, mock_store_data):
        """Test user prompt generation for specific Trusted Advisor recommendation"""
        import getTrustedAdvisorFromAPI_handler as handler
        
        recommendation = {
            'checkName': 'Security Groups - Specific Ports Unrestricted',
            'category': 'security',
            'status': 'warning',
            'resourcesSummary': {'resourcesFlagged': 3},
            'flaggedResources': [
                {'resourceId': 'sg-123456', 'metadata': ['22', 'tcp', '0.0.0.0/0']}
            ]
        }
        
        user_prompt = handler.generate_trusted_advisor_user_prompt(recommendation)
        
        # Verify key elements in user prompt
        self.assertIn('Security Groups - Specific Ports Unrestricted', user_prompt)
        self.assertIn('security', user_prompt)
        self.assertIn('warning', user_prompt)
        self.assertIn('JSON format', user_prompt)
        self.assertIn('checkId', user_prompt)

    @patch('prompt_gen_input.generate_conversation')
    @patch('time.sleep')
    def test_exponential_backoff_retry_success(self, mock_sleep, mock_generate_conversation):
        """Test exponential backoff retry mechanism"""
        import bedrockOnDemandInferenceTrustedAdvisor_handler as handler
        
        # Mock successful function
        mock_func = Mock(return_value={'success': True})
        
        result = handler.exponential_backoff_retry(mock_func)
        
        self.assertEqual(result, {'success': True})

    @patch('prompt_gen_input.generate_conversation')
    @patch('time.sleep')
    def test_exponential_backoff_retry_with_failures(self, mock_sleep, mock_generate_conversation):
        """Test exponential backoff retry with initial failures"""
        import bedrockOnDemandInferenceTrustedAdvisor_handler as handler
        
        # Mock function that fails twice then succeeds
        mock_func = Mock()
        mock_func.side_effect = [
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test'),
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test'),
            {'success': True}
        ]
        
        result = handler.exponential_backoff_retry(mock_func, max_retries=5, initial_delay=1)
        
        self.assertEqual(result, {'success': True})
        self.assertEqual(mock_func.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

if __name__ == '__main__':
    unittest.main()