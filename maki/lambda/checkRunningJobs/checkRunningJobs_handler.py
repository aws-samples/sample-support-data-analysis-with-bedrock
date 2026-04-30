"""
MAKI Step Functions Running Jobs Checker

This Lambda function monitors running Step Functions executions for the MAKI 
state machine to prevent concurrent executions and ensure proper resource 
management and workflow coordination.

Purpose:
- Check for currently running MAKI Step Functions executions
- Prevent concurrent executions that could cause resource conflicts
- Provide execution count information for workflow decisions
- Enable proper resource management and coordination

Key Features:
- Monitors specific MAKI state machine for running executions
- Pagination support for large numbers of executions
- Detailed logging of running execution ARNs
- Early termination when running executions are found
- Comprehensive error handling and validation

Processing Flow:
1. Retrieve state machine ARN from environment variables
2. Query Step Functions for running executions
3. Paginate through results to count all running executions
4. Log details about each running execution
5. Return count and state machine information

Environment Variables:
- STATE_MACHINE_ARN: ARN of the MAKI Step Functions state machine

Input Event Structure:
- No specific input required (uses environment variables)
- Passes through original event payload for reference

Output Structure:
- runningExecutions: Count of currently running executions
- stateMachineArn: State machine ARN being monitored
- originalPayload: Original input event for reference

Workflow Integration:
- Step Functions: Pre-execution check to prevent conflicts
- Resource management: Ensures single execution at a time
- Error prevention: Avoids resource contention issues

Execution States Monitored:
- RUNNING: Actively executing state machines
- Does not include SUCCEEDED, FAILED, TIMED_OUT, or ABORTED states

Use Cases:
- Preventing duplicate analysis runs
- Ensuring data consistency during processing
- Managing Bedrock API rate limits
- Coordinating batch inference job scheduling
"""

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
