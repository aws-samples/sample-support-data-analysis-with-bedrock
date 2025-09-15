import aws_cdk.aws_events_targets as targets
import aws_cdk.aws_events as events

import config
import sys
sys.path.append('utils')
import utils

# cron job for running the main state machine
def buildMainCronJob(self, state_machine):
    cron_job = events.Rule(
        self, utils.returnName(config.CRON_MAIN_JOB_NAME_BASE),
        rule_name = utils.returnName(config.CRON_MAIN_JOB_NAME_BASE),
        targets=[targets.SfnStateMachine(state_machine)],
        schedule=events.Schedule.cron(
            minute=config.CRON_MAIN_MINUTE,
            hour=config.CRON_MAIN_HOUR,
            day=config.CRON_MAIN_DAY,
            month=config.CRON_MAIN_MONTH,
            year=config.CRON_MAIN_YEAR
        ) 
    )
    cron_job.node.add_dependency(state_machine) # add dependency

    return cron_job

# cron job for reporting
def buildReportCronJob(self, report_function):
    cron_job = events.Rule(
        self, utils.returnName(config.CRON_REPORT_JOB_NAME_BASE),
        rule_name = utils.returnName(config.CRON_REPORT_JOB_NAME_BASE),
        targets=[targets.LambdaFunction(report_function)],
        schedule=events.Schedule.cron(
            minute=config.CRON_REPORT_MINUTE,
            hour=config.CRON_REPORT_HOUR,
            day=config.CRON_REPORT_DAY,
            month=config.CRON_REPORT_MONTH,
            year=config.CRON_REPORT_YEAR
        ) 
    )
    cron_job.node.add_dependency(report_function) # add dependency

    return cron_job