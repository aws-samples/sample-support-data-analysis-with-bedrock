"""
MAKI Bedrock On-Demand Inference Router Handler

This Lambda function serves as a router for on-demand Bedrock inference processing,
directing events to the appropriate handler based on the processing mode (cases or health).

Purpose:
- Route processing requests to mode-specific handlers
- Provide unified interface for on-demand inference operations
- Support both support cases and health events processing modes
- Enable seamless switching between data source types

Key Features:
- Mode-based routing logic with fallback to cases mode
- Unified interface for Step Functions integration
- Support for both support cases and health events processing
- Consistent error handling across processing modes

Processing Modes:
- 'cases': Routes to support cases processing handler
- 'health': Routes to health events processing handler
- Default: Falls back to cases mode for backward compatibility

Input Event Structure:
- mode: Processing mode ('cases' or 'health')
- case: Individual event data for processing
- ondemand_run_datetime: Timestamp for output organization
- Additional mode-specific parameters

Output Structure:
- Passes through the output from the selected mode-specific handler
- Maintains consistent response format across modes
"""

import sys
sys.path.append('/opt')

from bedrockOnDemandInferenceCases_handler import handler as cases_handler
from bedrockOnDemandInferenceHealth_handler import handler as health_handler

def handler(event, context):
    mode = event.get('mode', 'cases')
    
    if mode == 'health':
        return health_handler(event, context)
    else:
        return cases_handler(event, context)