import sys
sys.path.append('/opt')

import boto3
from botocore.exceptions import ClientError
import os
import uuid

sys.path.append('/opt')
from s3 import empty_s3_bucket, extract_bucket_name, move_s3_object

# create the singular batch job
def create_batch_job(bedrock, model_id, input_s3_uri, batches_s3_uri, output_s3_uri, role, name, batch_num, batch_files):

    # create unique batch job name (max 63 chars)
    # Extract account and region for shorter name
    account_id = boto3.client('sts').get_caller_identity()['Account']
    region = boto3.Session().region_name
    base_name = f"maki-{account_id}-{region}"  # Use full account ID to match bucket naming
    batch_job_name = f"{base_name}-b{batch_num}-{str(uuid.uuid4())[:8]}"
    print(f"create new batch inf job: {batch_job_name} (length: {len(batch_job_name)})")

    input_s3_bucket = extract_bucket_name(input_s3_uri)
    batches_s3_bucket = extract_bucket_name(batches_s3_uri)
    prefix = batch_job_name

    for file in batch_files:
        old_key = file
        new_key = f"{prefix}/{old_key}"
        move_s3_object(input_s3_bucket, old_key, batches_s3_bucket, new_key)

    # configs for batch inference
    input_config = {
        "s3InputDataConfig": {
            "s3Uri": f"{batches_s3_uri}{prefix}/" 
        }
    }
    
    output_config = {
        "s3OutputDataConfig": {
            "s3Uri": f"{output_s3_uri}{prefix}/"
        }
    }

    try:
        response = bedrock.create_model_invocation_job(
            modelId=model_id,
            jobName=batch_job_name,
            inputDataConfig=input_config,
            outputDataConfig=output_config,
            roleArn=role,
            timeoutDurationInHours=168  # parameterize
        )
        
        job_arn = response.get('jobArn')
        print(f"Created batch inference job: {job_arn}")
        return job_arn, batch_job_name
        
    except Exception as e:
        print(f"Error creating batch inference job: {str(e)}")
        raise

# see records, and create batch jobs
def handler(event, context):
    events_total = event.get('eventsTotal')
    events = event.get('events')

    # Handle case when there are no events to process
    if not events or events_total == 0:
        print("No events to process for batch inference")
        return {
            'eventsTotal': 0,
            'events': [],
            'batch_jobs': [],
            'remaining_files': 0
        }

    input_s3_uri = os.environ['S3_INPUT']
    batches_s3_uri = os.environ['S3_BATCHES']
    output_s3_uri = os.environ['S3_OUTPUT']
    model_id = os.environ['MODEL_ID']
    role = os.environ['ROLE']
    name = os.environ['NAME']
    batch_file_count_size = int(os.environ['BEDROCK_ONDEMAND_BATCH_INFLECTION'])

    # Get mode and execution ARN from event context
    mode = event.get('mode', 'unknown')
    execution_name = event.get('executionName', str(uuid.uuid4())[:8])
    # Extract just the execution ID from the full ARN if it's a full ARN
    if ':execution:' in execution_name:
        execution_id = execution_name.split(':')[-1]
    else:
        execution_id = execution_name
    
    # Create temporary directory name
    temp_dir = f"maki-batch-{mode}-{execution_id}"
    print(f"Using temporary directory: {temp_dir}")

    # Create Bedrock client
    bedrock = boto3.client('bedrock')

    batch_jobs = []
    
    remaining_files = 0
    
    # Break events into chunks of batch_file_count_size
    for i in range(0, len(events), batch_file_count_size):
        batch_chunk = events[i:i + batch_file_count_size]
        
        # Skip if chunk is smaller than batch_file_count_size
        if len(batch_chunk) < batch_file_count_size:
            remaining_files = len(batch_chunk)
            print(f"Skipping batch with {remaining_files} files (smaller than batch_file_count_size)")
            continue
            
        batch_num = i // batch_file_count_size + 1
        
        print(f"Processing batch {batch_num} with {len(batch_chunk)} files")
        
        # Use temp directory as the output prefix
        job_arn, batch_job_name = create_batch_job(
            bedrock=bedrock,
            model_id=model_id,
            input_s3_uri=input_s3_uri,
            batches_s3_uri=batches_s3_uri,
            output_s3_uri=f"{output_s3_uri}{temp_dir}/",
            role=role, 
            name=name,
            batch_num=batch_num,
            batch_files=batch_chunk
        )

        print(f"Batch job {batch_num} created: {job_arn}")

        # Record batch job details
        batch_jobs.append({
            'batch_num': batch_num,
            'model_id': model_id,
            'input_s3_uri': f"{batches_s3_uri}{batch_job_name}/",
            'output_s3_uri': f"{output_s3_uri}{temp_dir}/{batch_job_name}/",
            'name': name,
            'job_arn': job_arn,
            'batch_files': len(batch_chunk),
            'temp_dir': temp_dir
        })


    # for the remaining files that aren't batched, the on-demand jobs will pick them up
    return {
        'batch_jobs': batch_jobs,
        'remaining_files': remaining_files,
        'temp_dir': temp_dir
    }

        