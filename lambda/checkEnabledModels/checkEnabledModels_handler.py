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
    
    
