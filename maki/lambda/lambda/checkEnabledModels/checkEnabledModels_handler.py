"""
MAKI Bedrock Model Access Checker

This Lambda function validates that all required Amazon Bedrock models are 
accessible and properly enabled for MAKI operations, preventing execution 
failures due to model access issues.

Purpose:
- Validate access to required Bedrock models before processing
- Prevent workflow failures due to model access restrictions
- Provide clear feedback on model availability status
- Enable pre-flight checks in Step Functions workflow

Key Features:
- Tests actual model access through invoke attempts
- Validates both light and sophisticated models
- Provides detailed status reporting for each model
- Returns boolean status for workflow decision making
- Handles access denied exceptions gracefully

Models Validated:
- BEDROCK_TEXT_MODEL: Light model for individual event processing
- BEDROCK_TEXT_MODEL_AGG: Sophisticated model for aggregation and synthesis

Processing Flow:
1. Retrieve required model IDs from environment variables
2. Test access to each model through Bedrock runtime
3. Handle access denied exceptions to determine availability
4. Generate status report for all models
5. Return overall accessibility status

Environment Variables:
- BEDROCK_TEXT_MODEL: Light model identifier (e.g., Nova Micro)
- BEDROCK_TEXT_MODEL_AGG: Sophisticated model identifier (e.g., Claude Sonnet)

Input Event Structure:
- No specific input required (uses environment variables)

Output Structure:
- enabledModels: Boolean indicating if all required models are accessible

Access Validation Method:
- Attempts to invoke each model with empty body
- AccessDeniedException indicates model not enabled
- Other exceptions indicate model is accessible but request invalid
- This approach validates actual runtime access permissions

Integration Points:
- Step Functions: Pre-flight check before processing begins
- Workflow routing: Stops execution if models not available
- Error prevention: Avoids downstream failures due to access issues
"""

import boto3
import logging
import os


logger = logging.getLogger()
logger.setLevel(logging.INFO)

def check_model_access(model_id):

    session = boto3.Session()
    bedrock_runtime = session.client("bedrock-runtime")

    try:
        bedrock_runtime.invoke_model(modelId=model_id, body="{}")
    except Exception as e:
        if "AccessDeniedException" in str(e):
            return False
        else:
            return True 

def handler(event, context):
    text_model = os.environ['BEDROCK_TEXT_MODEL']
    agg_model = os.environ['BEDROCK_TEXT_MODEL_AGG']
    required_models = [text_model, agg_model]

    
    try:
        
        validation_msg = (
            "MODEL ACCESS STATUS\n"
        )
        for model in required_models:
            status = check_model_access(model)
            if status:
                validation_msg += (
                    f"{model} is accessible\n"
                )
            else:
                validation_msg += f"{model} is not accessible\n"
        print(validation_msg)

        if all([check_model_access(model) for model in required_models]):
            print(
                "All required models are accessible."
            )
            return {'enabledModels': True}
        
        else:
            print(
                "Please enable access to all required models in the AWS Console"
            )  
            return {'enabledModels': False}
                    
    except Exception as e:
        logger.warning(f"Error checking enabled models: {str(e)}")
        raise
    
    
