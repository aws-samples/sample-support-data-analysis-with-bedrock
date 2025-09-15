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
    
    