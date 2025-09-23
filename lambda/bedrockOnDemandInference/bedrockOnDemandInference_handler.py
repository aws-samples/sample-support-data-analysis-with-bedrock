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