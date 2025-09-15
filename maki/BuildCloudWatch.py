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