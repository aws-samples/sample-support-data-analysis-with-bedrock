import os
import json
import sys
from datetime import datetime

sys.path.append('/opt')
from bedrockProcessBatchOutputCases_handler import handler as cases_handler
from bedrockProcessBatchOutputHealth_handler import handler as health_handler

def handler(event, context):
    
    mode = event.get('mode', 'cases')
    
    if mode == 'cases':
        return cases_handler(event, context)
    elif mode == 'health':
        return health_handler(event, context)
    else:
        raise ValueError(f"Unknown mode: {mode}")
