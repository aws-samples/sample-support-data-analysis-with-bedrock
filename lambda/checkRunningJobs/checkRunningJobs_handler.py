import boto3
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    # Get state machine ARN from environment variable
    state_machine_arn = os.environ.get('STATE_MACHINE_ARN')
    logger.info(f"STATE_MACHINE_ARN: {state_machine_arn}")

    if not state_machine_arn:
        error_msg = "STATE_MACHINE_ARN environment variable is not set"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    client = boto3.client('stepfunctions')
    running_count = 0
    
    try:
        # Get running executions for the specific state machine
        paginator = client.get_paginator('list_executions')
        for page in paginator.paginate(
            stateMachineArn=state_machine_arn,
            statusFilter='RUNNING'
        ):
            executions = page['executions']
            running_count += len(executions)
            
            # Log details about running executions
            for execution in executions:
                logger.info(f"Found running execution: {execution['executionArn']}")
                
            # Optional: break early if we found any running executions
            if running_count > 0:
                break
                    
    except Exception as e:
        logger.warning(f"Error checking state machine executions: {str(e)}")
        raise
    
    logger.info(f"Found {running_count} running executions for state machine: {state_machine_arn}")
    
    return {
        'runningExecutions': running_count,
        'stateMachineArn': state_machine_arn,
        'originalPayload': event
    }
