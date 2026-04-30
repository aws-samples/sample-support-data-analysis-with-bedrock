"""
MAKI Bedrock Batch Output Processing Router Handler

This Lambda function serves as a router for processing Bedrock batch inference 
outputs, directing processing to the appropriate handler based on the data mode 
(cases or health events).

Purpose:
- Route batch output processing to mode-specific handlers
- Provide unified interface for batch output processing operations
- Support both support cases and health events batch processing
- Enable seamless switching between data source types

Key Features:
- Mode-based routing logic with explicit mode validation
- Unified interface for Step Functions integration
- Support for both support cases and health events batch processing
- Consistent error handling across processing modes

Processing Modes:
- 'cases': Routes to support cases batch output processing
- 'health': Routes to health events batch output processing
- Error handling for unknown modes

Input Event Structure:
- mode: Processing mode ('cases' or 'health')
- batchInferenceResult: Batch job details and output locations
- Additional mode-specific parameters

Output Structure:
- Passes through the output from the selected mode-specific handler
- Maintains consistent response format across modes
- Returns summary analysis and processing statistics
"""

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
