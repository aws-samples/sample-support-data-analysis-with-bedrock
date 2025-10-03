#!/usr/bin/env python3
"""
MAKI Step Function Execution Driver

This tool serves as the primary interface for executing MAKI outside the AWS Lambda console. 
It starts the Step Function state machine, monitors execution progress in real-time, and 
provides comprehensive output including both summary analysis and example event data.

Purpose:
- Execute MAKI Step Function state machine with real-time monitoring
- Display current processing mode and AWS identity information
- Show detailed step-by-step progress with timing information
- Provide combined JSON output with summary and example event data

Execution Flow:
1. Retrieves current mode from SSM Parameter Store
2. Starts Step Function execution with mode configuration
3. Monitors execution progress with step-level detail
4. Displays real-time timing and function information
5. Outputs combined results including summary and example events

Usage:
    python tools/runMaki.py

Output Format:
- Real-time progress display with step names and durations
- Final JSON output combining summary analysis and example event
- Comprehensive error reporting with step-level failure details

Key Features:
- Real-time Step Function execution monitoring
- Automatic mode detection from SSM Parameter Store
- Step-level progress tracking with timing information
- Combined output generation from S3 results
- Integration with both support cases and health events processing
- Used by test scenarios and manual MAKI execution
"""

import boto3
import json
from time import sleep
from datetime import datetime, timedelta

def get_example_event_file():
    """Get an example individual event JSON file from S3"""
    s3_client = boto3.client('s3')
    bucket_name = f'maki-{account_id}-{region}-report'
    
    try:
        # Try ondemand first, then batch
        for prefix in ['ondemand/', 'batch/']:
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix,
                MaxKeys=100
            )
            
            if 'Contents' not in response:
                continue
                
            # Find a case or health event JSON file (not summary.json)
            for obj in response['Contents']:
                key = obj['Key']
                if (key.endswith('.json') and 
                    ('case-' in key or 'case-gen-' in key or 'health-' in key or '/events/' in key) and 
                    'summary.json' not in key and 'health_summary.json' not in key):
                    # Get the file content
                    file_response = s3_client.get_object(Bucket=bucket_name, Key=key)
                    content = file_response['Body'].read().decode('utf-8')
                    return f"s3://{bucket_name}/{key}", content
                
        return None
    except Exception as e:
        print(f"⚠️  Could not retrieve example event file: {e}")
        return None

# Create clients
sfn_client = boto3.client('stepfunctions')
ssm_client = boto3.client('ssm')

# Get account and region info
sts_client = boto3.client("sts")
account_id = sts_client.get_caller_identity()["Account"]
region = boto3.session.Session().region_name
state_machine_arn = 'arn:aws:states:' + region + ':' + account_id + ':stateMachine:maki-' + account_id + '-' + region + '-state-machine' 

# Get MODE from SSM Parameter Store
def get_mode_from_ssm():
    try:
        response = ssm_client.get_parameter(Name=f"maki-{account_id}-{region}-maki-mode")
        return response['Parameter']['Value']
    except Exception as e:
        print(f"⚠️  Warning: Could not get MODE from SSM: {e}")
        return "unknown"

current_mode = get_mode_from_ssm()

print("🚀 MAKI State Machine Execution")
print("=" * 50)
print(f"📍 State Machine: {state_machine_arn}")
print(f"🎯 MODE: {current_mode}")
print("=" * 50)

# Define the input data for the state machine execution
input_data = {
    "mode": current_mode
}

def format_duration(start_time, current_time):
    """Format duration as MM:SS"""
    duration = current_time - start_time
    total_seconds = int(duration.total_seconds())
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def get_running_function(state_machine_arn): 
    # Get running executions
    executions = sfn_client.list_executions(
        stateMachineArn=state_machine_arn,
        statusFilter="RUNNING"
    )
    
    if not executions['executions']:
        return "No running executions found."
   
    execution_arn = executions['executions'][0]['executionArn']  # Get the latest running execution

    #Get execution history to find the current running step
    history = sfn_client.get_execution_history(executionArn=execution_arn, reverseOrder=True)
    
    for event in history['events']:
        if event['type'] == 'TaskStateEntered':  # Look for the latest entered task state
            running_step_name = event['stateEnteredEventDetails']['name']
            break
    else:
        return "No running task found in history."

    #Get state machine definition
    response = sfn_client.describe_state_machine(stateMachineArn=state_machine_arn)
    definition = json.loads(response['definition'])

    #Get the function ARN associated with the running step
    state_details = definition['States'].get(running_step_name, {})

    if state_details == {}:
        # Check in ItemProcessor for new Map syntax
        event_iterator = definition['States'].get('event-iterator', {})
        if 'ItemProcessor' in event_iterator:
            state_details = event_iterator['ItemProcessor']['States'].get(running_step_name, {})
    
    function_arn = state_details.get('Resource', '')
    
    # Determine what type of step this is if no function
    if not function_arn:
        step_type = state_details.get('Type', '')
        if step_type == 'Map':
            function_arn = 'Map State (parallel processing)'
        elif step_type == 'Choice':
            function_arn = 'Choice State (conditional routing)'
        elif step_type == 'Pass':
            function_arn = 'Pass State (data transformation)'
        elif step_type == 'Wait':
            function_arn = 'Wait State (delay)'
        elif step_type == 'Parallel':
            function_arn = 'Parallel State (concurrent execution)'
        else:
            function_arn = f'{step_type} State' if step_type else 'State machine step'

    function_data = {"Step Name": running_step_name, "Function ARN": function_arn}
    return function_data

try:
    # Start the state machine execution
    start_time = datetime.now()
    print(f"⏰ Started at: {start_time.strftime('%H:%M:%S')}")
    print()
    
    response = sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(input_data)
    )

    # Get the execution ARN
    execution_arn = response['executionArn']
    print(f"🎯 Execution ARN: {execution_arn}")
    print()

    # Wait for the execution to complete
    execution_count = 0
    last_step = None
    step_start_time = datetime.now()
    
    while True:
        current_time = datetime.now()
        execution_info = sfn_client.describe_execution(executionArn=execution_arn)
        status = execution_info['status']
        
        if status == 'RUNNING':
            current_process_info = get_running_function(execution_info['stateMachineArn'])
            current_step = current_process_info.get("Step Name", "Unknown")
            
            # Check if we moved to a new step
            if current_step != last_step:
                if last_step:
                    step_duration = format_duration(step_start_time, current_time)
                    print(f"✅ Completed: {last_step} ({step_duration})")
                
                print(f"🔄 Running: {current_step}")
                print(f"   Function: {current_process_info.get('Function ARN', 'N/A')}")
                last_step = current_step
                step_start_time = current_time
                execution_count = 0
            
            # Show progress indicator
            total_duration = format_duration(start_time, current_time)
            step_duration = format_duration(step_start_time, current_time)
            progress_dots = "." * (execution_count % 4)
            print(f"\r   ⏱️  Total: {total_duration} {progress_dots:<3}", end="", flush=True)
            
            execution_count += 1
            sleep(2)  # Check every 2 seconds
            
        elif status == 'SUCCEEDED':
            if last_step:
                step_duration = format_duration(step_start_time, current_time)
                print(f"\r✅ Completed: {last_step} ({step_duration})")
            
            total_duration = format_duration(start_time, current_time)
            print()
            print("🎉 EXECUTION SUCCEEDED!")
            print(f"⏰ Total Duration: {total_duration}")
            print("=" * 50)
            
            output = execution_info['output']
            
            # Create combined JSON output
            combined_output = {}
            
            # Add summary
            try:
                parsed_output = json.loads(output)
                combined_output["Summary"] = parsed_output
            except:
                combined_output["Summary"] = output
            
            # Add example event file
            example_result = get_example_event_file()
            if example_result:
                file_path, file_content = example_result
                try:
                    parsed_content = json.loads(file_content)
                    combined_output["Event_Example"] = parsed_content
                except:
                    combined_output["Event_Example"] = file_content
            else:
                combined_output["Event_Example"] = "No individual event files found"
            
            # Output as JSON
            print(json.dumps(combined_output, indent=2))
            
            break
            
        elif status == 'FAILED':
            if last_step:
                step_duration = format_duration(step_start_time, current_time)
                print(f"\r❌ Failed at: {last_step} ({step_duration})")
            
            total_duration = format_duration(start_time, current_time)
            print()
            print("💥 EXECUTION FAILED!")
            print(f"⏰ Total Duration: {total_duration}")
            print("=" * 50)
            
            if 'error' in execution_info:
                print(f"❌ Error: {execution_info['error']}")
            if 'cause' in execution_info:
                print(f"🔍 Cause: {execution_info['cause']}")
            break
            
        else:
            print(f"\r⚠️  Unexpected status: {status}")
            break

except Exception as e:
    print(f"💥 Error: {e}")
