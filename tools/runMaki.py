# simple driver script to develop lambda outside AWS lambda console
import boto3
import json
from time import sleep
from datetime import datetime, timedelta

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
    "key1": "value1",
    "key2": "value2"
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
        #Iterator invokes the task
        state_details = definition['States']['event-iterator']['Iterator']['States'].get(running_step_name, {})
    
    function_arn = state_details.get('Resource', 'No function associated')

    function_data = {"Step Name": running_step_name, "Function ARN": function_arn}
    return function_data

try:
    # Start the state machine execution
    start_time = datetime.now()
    print(f"⏰ Started at: {start_time.strftime('%H:%M:%S')}")
    print()
    
    response = sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
     #   input=str(input_data)
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
            print(f"\r   ⏱️  Total: {total_duration} | Step: {step_duration} {progress_dots:<3}", end="", flush=True)
            
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
            print("📋 Output:")
            try:
                parsed_output = json.loads(output)
                print(json.dumps(parsed_output, indent=2))
            except:
                print(output)
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
