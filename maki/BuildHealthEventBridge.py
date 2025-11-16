import aws_cdk.aws_events as events
import aws_cdk.aws_events_targets as targets
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_iam as iam
from aws_cdk import Duration

import config
import sys
sys.path.append('utils')
import utils

def build_health_eventbridge_rule(self, health_event_processor_function):
    """
    Create EventBridge rule to capture AWS Health events in real-time
    
    This rule listens for all AWS Health events and triggers immediate processing,
    replacing the polling-based approach with event-driven ingestion.
    """
    
    # EventBridge rule for AWS Health events
    health_event_rule = events.Rule(
        self, 
        utils.returnName("health-eventbridge-rule"),
        rule_name=utils.returnName("health-eventbridge-rule"),
        description="Capture AWS Health events for real-time MAKI processing",
        event_pattern=events.EventPattern(
            source=["aws.health", "custom.health.test"],
            detail_type=["AWS Health Event"],
            detail={
                # Filter for relevant event types based on MAKI configuration
                "eventTypeCategory": [
                    "issue",
                    "scheduledChange", 
                    "accountNotification"
                ]
            }
        ),
        targets=[targets.LambdaFunction(health_event_processor_function)]
    )
    
    # Add dependency
    health_event_rule.node.add_dependency(health_event_processor_function)
    
    return health_event_rule

def build_health_event_processor_lambda(self, maki_role, log_group, opensearch_utils_layer, s3_utils_layer, prompt_gen_layer):
    """
    Create Lambda function to process AWS Health events from EventBridge
    
    This function receives health events in real-time, enriches them with embeddings,
    and stores them in OpenSearch for MAKI analysis.
    """
    
    # Lambda function for processing health events
    health_processor_function = lambda_.Function(
        self,
        utils.returnName("health-eventbridge-processor"),
        function_name=utils.returnName("health-eventbridge-processor"),
        description="Process AWS Health events from EventBridge in real-time",
        runtime=lambda_.Runtime.PYTHON_3_12,
        handler="healthEventBridgeProcessor_handler.handler",
        code=lambda_.Code.from_asset("lambda/healthEventBridgeProcessor"),
        timeout=Duration.seconds(300),  # 5 minutes for processing
        memory_size=1024,
        role=maki_role,
        layers=[opensearch_utils_layer, s3_utils_layer, prompt_gen_layer],
        log_group=log_group,
        environment={
            "OPENSEARCH_INDEX": config.OPENSEARCH_INDEX,
            "BEDROCK_EMBEDDING_MODEL": config.BEDROCK_EMBEDDING_MODEL,
            "REGION": config.REGION,
            "STATE_MACHINE_ARN": f"arn:aws:states:{config.REGION}:{config.account_id}:stateMachine:{utils.returnName(config.STATE_MACHINE_NAME_BASE)}",
            "IMMEDIATE_PROCESSING": str(config.EVENTBRIDGE_IMMEDIATE_PROCESSING).lower(),
            "CRITICAL_SERVICES": ",".join(config.EVENTBRIDGE_CRITICAL_SERVICES),
            "LOG_LEVEL": "INFO"
        }
    )
    
    return health_processor_function

def build_health_eventbridge_integration(self, maki_role, log_group, opensearch_utils_layer, s3_utils_layer, prompt_gen_layer):
    """
    Build complete EventBridge integration for AWS Health events
    
    Creates both the EventBridge rule and Lambda processor for real-time
    health event ingestion and processing.
    """
    
    # Create the health event processor Lambda
    health_processor_function = build_health_event_processor_lambda(
        self, maki_role, log_group, opensearch_utils_layer, s3_utils_layer, prompt_gen_layer
    )
    
    # Create the EventBridge rule
    health_event_rule = build_health_eventbridge_rule(
        self, health_processor_function
    )
    
    # Grant EventBridge permission to invoke the Lambda (without source ARN to avoid circular dependency)
    health_processor_function.add_permission(
        "AllowEventBridgeInvoke",
        principal=iam.ServicePrincipal("events.amazonaws.com")
    )
    
    return {
        "health_processor_function": health_processor_function,
        "health_event_rule": health_event_rule
    }