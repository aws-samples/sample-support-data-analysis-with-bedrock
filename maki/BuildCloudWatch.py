"""
MAKI CloudWatch Components Builder

This module creates CloudWatch logging infrastructure for MAKI, providing centralized 
logging capabilities for all Lambda functions and Step Functions executions.

Purpose:
- Create CloudWatch Log Groups for MAKI operations
- Configure log retention policies for cost optimization
- Provide centralized logging for debugging and monitoring

Components Created:
- CloudWatch Log Group with configurable retention
- Dependency management with VPC resources
- Removal policy for stack cleanup

Key Features:
- Configurable log retention (currently set to 1 day for cost optimization)
- Integration with all MAKI Lambda functions and Step Functions
- Proper dependency ordering to ensure VPC is created first
- Automatic cleanup on stack deletion

Usage:
- Called by MakiFoundations stack during deployment
- Log group is referenced by all Lambda functions and Step Functions
- Provides centralized location for all MAKI operational logs
"""

import aws_cdk as cdk
import aws_cdk.aws_logs as logs
import sys
sys.path.append('..')
import config
sys.path.append('utils')
import utils

# make these configurable
def buildCWLogGroup(self,vpc):
    log_group = logs.LogGroup(
        self, utils.returnName(config.LOG_GROUP_NAME_BASE),
        log_group_name=utils.returnName(config.LOG_GROUP_NAME_BASE),
        #retention=logs.RetentionDays.config.LOG_RETENTION_DAYS # make this configurable
        retention=logs.RetentionDays.ONE_DAY,
        removal_policy=cdk.RemovalPolicy.DESTROY
    )

    log_group.node.add_dependency(vpc) # add dependency
    return log_group