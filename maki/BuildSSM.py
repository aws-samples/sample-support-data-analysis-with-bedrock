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
    
    # Create OPENSEARCH_ENDPOINT parameter
    opensearch_endpoint_parameter = ssm.StringParameter(
        self, "MakiOpenSearchEndpointParameter",
        parameter_name=utils.returnName("opensearch-endpoint"),
        string_value="placeholder-please-update-with-your-endpoint",
        description="OpenSearch endpoint URL for health events storage (updated by MakiEmbeddings)"
    )
    
    # Create OPENSEARCH_QUERY_SIZE parameter
    opensearch_query_size_parameter = ssm.StringParameter(
        self, "MakiOpenSearchQuerySizeParameter",
        parameter_name=utils.returnName("opensearch-query-size"),
        string_value="10000",
        description="Maximum number of events to retrieve per OpenSearch query"
    )
    
    return {
        'mode_parameter': mode_parameter,
        'events_since_parameter': events_since_parameter,
        'opensearch_endpoint_parameter': opensearch_endpoint_parameter,
        'opensearch_query_size_parameter': opensearch_query_size_parameter
    }
