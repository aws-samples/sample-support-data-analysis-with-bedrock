"""
MAKI Output Files Cleanup Handler

This Lambda function cleans up temporary output files from S3 buckets to 
maintain storage hygiene and prevent accumulation of intermediate processing 
files between MAKI execution runs.

Purpose:
- Clean up temporary LLM output files from S3 buckets
- Maintain storage hygiene between processing runs
- Prevent accumulation of intermediate processing files
- Prepare clean environment for new processing cycles

Key Features:
- Complete S3 bucket emptying functionality
- Error handling and logging for cleanup operations
- Pass-through event handling for workflow integration
- Configurable target bucket through environment variables

Processing Flow:
1. Retrieve target S3 bucket from environment variables
2. Execute complete bucket emptying operation
3. Log cleanup completion status
4. Return original event for workflow continuation

Environment Variables:
- S3_OUTPUT: S3 bucket containing LLM output files to clean

Input Event Structure:
- Accepts any event structure (pass-through)

Output Structure:
- Returns original input event unchanged

Use Cases:
- Pre-processing cleanup to ensure clean starting state
- Post-processing cleanup to remove temporary files
- Storage cost optimization by removing intermediate files
- Preparation for new analysis cycles

Integration Points:
- Step Functions: Can be called at various workflow stages
- S3 lifecycle: Complements S3 lifecycle policies
- Cost optimization: Reduces storage costs for temporary files

Safety Considerations:
- Only cleans specified output bucket
- Does not affect source data or final reports
- Maintains audit trail through CloudWatch logging
"""

import sys
sys.path.append('/opt')
import logging
import os

from s3 import empty_s3_bucket

logger = logging.getLogger()
logger.setLevel(logging.INFO)

output_s3 = os.environ['S3_OUTPUT'] # llm output folder

def handler(event, context):
    try:
        empty_s3_bucket(output_s3) 
        logger.info(f"Cleaned {output_s3}")
        return event
                    
    except Exception as e:
        logger.warning(f"Could not empty {output_s3}: {str(e)}")
        raise
    
    