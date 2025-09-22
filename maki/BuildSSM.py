from aws_cdk import (
    aws_ssm as ssm
)
import config
import utils

def buildSSMParameters(self):
    """Build SSM Parameter Store parameters for MAKI configuration"""
    
    # Create MODE parameter
    mode_parameter = ssm.StringParameter(
        self, "MakiModeParameter",
        parameter_name=utils.returnName("maki-mode"),
        string_value="health",
        description="MAKI execution mode: 'cases' for support cases, 'health' for health events"
    )
    
    # Create EVENTS_SINCE parameter
    events_since_parameter = ssm.StringParameter(
        self, "MakiEventsSinceParameter",
        parameter_name=utils.returnName("maki-events-since"),
        string_value="2023-01-01T00:00:00Z",
        description="Start time for retrieving events (both support cases and health events)"
    )
    
    return {
        'mode_parameter': mode_parameter,
        'events_since_parameter': events_since_parameter
    }
