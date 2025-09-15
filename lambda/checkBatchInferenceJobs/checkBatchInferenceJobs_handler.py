import sys
sys.path.append('/opt')
import boto3
import logging
import json
import os
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_batch_jobs_status(bedrock, status_filter=None):
    """Get batch inference jobs with optional status filter."""
    try:
        jobs = []
        paginator = bedrock.get_paginator('list_model_invocation_jobs')
        
        # Set up parameters
        params = {
            'sortOrder': 'Descending'  # Most recent first
        }
        if status_filter:
            params['statusEquals'] = status_filter
        
        # Paginate through results
        for page in paginator.paginate(**params):
            for job in page.get('invocationJobSummaries', []):
                job_info = {
                    'roleArn': job.get('roleArn'),
                    'jobName': job.get('name'),
                    'jobId': job.get('jobIdentifier'),
                    'status': job.get('status'),
                    'modelId': job.get('modelId'),
                    'submitTime': job.get('submitTime').isoformat() if job.get('submitTime') else None,
                    'endTime': job.get('endTime').isoformat() if job.get('endTime') else None
                }
                jobs.append(job_info)
                
                logger.info(f"Found job: {job_info['jobName']} with status: {job_info['status']}")
                
        return jobs
        
    except ClientError as e:
        logger.warning(f"Error listing batch jobs: {str(e)}")
        raise

def group_jobs_by_status(jobs):
    """Group jobs by their status."""
    status_groups = {
        'Submitted': [],
        'Validating': [],
        'Scheduled': [],
        'InProgress': [],
        'Completed': [],
        'Failed': [],
        'Stopping': [],
        'Stopped': []
    }
    
    for job in jobs:
        status = job['status']
        if status in status_groups:
            status_groups[status].append(job)
    
    return status_groups

def handler(event, context):
    """Lambda handler to check Bedrock batch inference jobs status."""
    try:
        bedrock = boto3.client('bedrock')
        
        # Check if this is an EventBridge event for a job completion
        is_job_completion_event = False
        job_detail = {}
        
        if event and 'detail' in event and 'status' in event['detail']:
            is_job_completion_event = True
            job_detail = event['detail']
            logger.info(f"Received job completion event: {job_detail}")
        
        # Get status filter from event if provided
        status_filter = event.get('statusFilter') if not is_job_completion_event else None
        
        # Get all jobs or filtered by status
        jobs = get_batch_jobs_status(bedrock, status_filter)
        
        # Group jobs by status
        status_groups = group_jobs_by_status(jobs)
        
        # Calculate counts
        status_counts = {status: len(jobs) for status, jobs in status_groups.items()}
        
        incomplete_jobs = []
        for status, jobs in status_groups.items():
            if status not in ['Completed', 'Stopped', 'Failed']:
                incomplete_jobs.extend(jobs)
        
        response = {
            'statusCounts': status_counts,
            'totalJobs': len(jobs),
            'incompleteJobsCount': len(incomplete_jobs),
            'incompleteJobs': incomplete_jobs,
            'allJobs': jobs,
        }
        
        # Log summary
        logger.info(f"Job Status Summary: {status_counts}")
        logger.info(f"Total Incomplete Jobs: {len(incomplete_jobs)}")

        return response
        
    except Exception as e:
        logger.warning(f"Error processing batch job status: {str(e)}")
        raise

def get_specific_job_status(job_id):
    """Get detailed status for a specific job ID."""
    try:
        bedrock = boto3.client('bedrock')
        response = bedrock.get_model_invocation_job(
            jobIdentifier=job_id
        )
        
        return {
            'jobId': job_id,
            'status': response.get('status'),
            'statusMessage': response.get('statusMessage'),
            'submitTime': response.get('submitTime').isoformat() if response.get('submitTime') else None,
            'endTime': response.get('endTime').isoformat() if response.get('endTime') else None,
            'inputConfig': response.get('inputConfig'),
            'outputConfig': response.get('outputConfig')
        }
        
    except ClientError as e:
        logger.warning(f"Error getting status for job {job_id}: {str(e)}")
        raise
