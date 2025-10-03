"""
MAKI Systems Manager Parameter Store Builder

This module creates AWS Systems Manager Parameter Store parameters for MAKI 
configuration management, enabling runtime configuration and mode switching.

Purpose:
- Create centralized configuration parameters for MAKI operations
- Enable runtime mode switching between support cases and health events
- Configure data source endpoints and query parameters
- Provide persistent storage for operational settings

Parameters Created:
- maki-mode: Controls processing mode ('cases' or 'health')
- maki-events-since: Start time for event retrieval operations
- opensearch-endpoint: OpenSearch Serverless collection endpoint URL
- opensearch-query-size: Maximum events per OpenSearch query

Key Features:
- Account and region-specific parameter naming
- Default values for immediate operation
- Runtime modification support through tools and APIs
- Integration with Lambda functions for dynamic configuration
- Persistent storage across deployments

Parameter Usage:
- Mode switching: flip_mode.py tool and Lambda functions
- OpenSearch configuration: opensearch_client.py tool
- Event filtering: Date range controls for data retrieval
- Query optimization: Configurable result set sizes

Configuration Management:
- Parameters are created with sensible defaults
- Can be modified through AWS CLI, Console, or MAKI tools
- Lambda functions retrieve values at runtime
- Supports both manual and automated configuration updates
"""

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
