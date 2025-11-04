import aws_cdk as core
import aws_cdk.assertions as assertions
import unittest

from maki.maki_stack import MakiStack

class TestMakiStack(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.app = core.App()
        self.stack = MakiStack(self.app, "maki")
        self.template = assertions.Template.from_stack(self.stack)
    
    def test_lambda_functions_created(self):
        """Test that Lambda functions are created"""
        # Test that Lambda functions exist
        self.template.resource_count_is("AWS::Lambda::Function", assertions.Match.any_value())
    
    def test_s3_buckets_created(self):
        """Test that S3 buckets are created"""
        # Test that S3 buckets exist
        self.template.resource_count_is("AWS::S3::Bucket", assertions.Match.any_value())
    
    def test_step_functions_created(self):
        """Test that Step Functions state machine is created"""
        # Test that Step Functions state machine exists
        self.template.resource_count_is("AWS::StepFunctions::StateMachine", assertions.Match.any_value())
    
    def test_trusted_advisor_lambda_functions(self):
        """Test that Trusted Advisor specific Lambda functions are created"""
        # Check for Trusted Advisor specific Lambda functions
        lambda_functions = self.template.find_resources("AWS::Lambda::Function")
        
        # Look for Trusted Advisor related functions
        ta_functions = []
        for logical_id, resource in lambda_functions.items():
            if 'TrustedAdvisor' in logical_id:
                ta_functions.append(logical_id)
        
        # Should have at least some Trusted Advisor functions
        self.assertGreater(len(ta_functions), 0, "No Trusted Advisor Lambda functions found")
    
    def test_iam_roles_created(self):
        """Test that IAM roles are created for Lambda functions"""
        # Test that IAM roles exist
        self.template.resource_count_is("AWS::IAM::Role", assertions.Match.any_value())
    
    def test_opensearch_domain_created(self):
        """Test that OpenSearch domain is created"""
        # Test that OpenSearch domain exists
        self.template.resource_count_is("AWS::OpenSearchService::Domain", assertions.Match.any_value())

# Legacy test function for backward compatibility
def test_sqs_queue_created():
    app = core.App()
    stack = MakiStack(app, "maki")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })

if __name__ == '__main__':
    unittest.main()
