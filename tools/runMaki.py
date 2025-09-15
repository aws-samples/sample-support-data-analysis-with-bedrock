# simple driver script to develop lambda outside AWS lambda console
import boto3
import json
from time import sleep

# Create a Step Functions client
sfn_client = boto3.client('stepfunctions')

# Define the state machine ARN
sts_client = boto3.client("sts")
account_id = sts_client.get_caller_identity()["Account"]
region = boto3.session.Session().region_name
state_machine_arn = 'arn:aws:states:' + region + ':' + account_id + ':stateMachine:maki-' + account_id + '-' + region + '-state-machine' 
print("Executing: \n ", state_machine_arn)

# Define the input data for the state machine execution
input_data = {
    "key1": "value1",
    "key2": "value2"
}
PROCESSING_STRING = '.'

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
        state_details = definition['States']['case-iterator']['Iterator']['States'].get(running_step_name, {})
    
    function_arn = state_details.get('Resource', 'No function associated')

    function_data = {"Step Name": running_step_name, "Function ARN": function_arn}
    return function_data

try:
    # Start the state machine execution
    response = sfn_client.start_execution(
        stateMachineArn=state_machine_arn,
     #   input=str(input_data)
    )

    # Get the execution ARN
    execution_arn = response['executionArn']
    print(f"State machine execution started: {execution_arn}")

    # Wait for the execution to complete
    execution_count = 0
    while True:
        execution_info = sfn_client.describe_execution(executionArn=execution_arn) # getting throttled here at times.
        status = execution_info['status']
        
        if status == 'RUNNING':
            current_process_info = get_running_function(execution_info['stateMachineArn'])
            print(json.dumps(current_process_info, indent=4))
            # print processing string by incrementing with count to enable user to see the processing
            if (execution_count > 0):
                print(PROCESSING_STRING*execution_count)
            execution_count += 2 # increment by 2 to make it visible
            sleep(20/1000) # sleep for 20 milliseconds before checking the status again
        elif status == 'SUCCEEDED':
            print("Execution succeeded!")
            output = execution_info['output']
            print(f"Output: {output}")
            break
        elif status == 'FAILED':
            print("Execution failed!")
            break
        else:
            print(f"Unexpected status: {status}")
            break

except Exception as e:
    print(f"Error: {e}")
