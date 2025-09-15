import aws_cdk as cdk
import aws_cdk.aws_lambda as lambda_
import aws_cdk.aws_stepfunctions as sfn
import aws_cdk.aws_stepfunctions_tasks as tasks
import aws_cdk.aws_iam as iam

import config
import sys
sys.path.append('utils')
import utils

def buildStateMachine(self, functions, log_group):
    start_state = sfn.Pass(self,"Begin MAKI operations")

    # why can't the makiRole be used here?
    # it creates a circular dependency
    exec_role = iam.Role(self, "MakiRole", assumed_by=iam.ServicePrincipal("states.amazonaws.com"))

    lambdaCheckEnabledModels = functions[config.CHECK_ENABLED_MODELS_NAME_BASE]
    lambdaCheckRunningJobs = functions[config.CHECK_RUNNING_JOBS_NAME_BASE]
    lambdaCheckBatchInferenceJobs = functions[config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE]
    lambdaGetCasesFromCID = functions[config.GET_CID_CASES_NAME_BASE]
    lambdaBedrockOnDemandInference = functions[config.BEDROCK_ONDEMAND_INF_NAME_BASE]
    lambdaBedrockBatchInference = functions[config.BEDROCK_BATCH_INF_JOB_NAME_BASE]

    stepCheckEnabledModels = tasks.LambdaInvoke(
        self, config.CHECK_ENABLED_MODELS_NAME_BASE,
        lambda_function=lambdaCheckEnabledModels,
        payload_response_only=True,
        output_path = "$"
    )

    stepCheckRunningJobs = tasks.LambdaInvoke(
        self, config.CHECK_RUNNING_JOBS_NAME_BASE,
        lambda_function=lambdaCheckRunningJobs,
        payload_response_only=True,
        output_path = "$"
    )

    stepCheckBatchInferenceJobs = tasks.LambdaInvoke(
        self, f"pre-{config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE}",
        lambda_function=lambdaCheckBatchInferenceJobs,
        payload_response_only=True,
        output_path = "$"
    )

    stepGetCases = tasks.LambdaInvoke(
        self, config.GET_CID_CASES_NAME_BASE,
        lambda_function=lambdaGetCasesFromCID,
        payload_response_only=True,
        output_path = "$"
    )

    stepBedrockOnDemandInference = tasks.LambdaInvoke(
        self, config.BEDROCK_ONDEMAND_INF_NAME_BASE,
        lambda_function=lambdaBedrockOnDemandInference,
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )

    stepBedrockBatchInference = tasks.LambdaInvoke(
        self, config.BEDROCK_BATCH_INF_JOB_NAME_BASE,
        lambda_function=lambdaBedrockBatchInference,
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )

    stepPostCheckBatchInferenceJobs = tasks.LambdaInvoke(
        self, f"post-{config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE}",
        lambda_function=lambdaCheckBatchInferenceJobs,
        payload_response_only=True,
        output_path = "$"
    )

    stepProcessBatchOutput = tasks.LambdaInvoke(
        self, config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE,
        lambda_function=functions[config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE],
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )
    
    # Wait state for batch inference job completion check
    waitForBatchCompletion = sfn.Wait(
        self,
        "WaitForBatchCompletion",
        time=sfn.WaitTime.duration(cdk.Duration.minutes(config.POST_BATCH_CHECK_INTERVAL_MIN))
    )
    
    stepProcessOnDemandOutput = tasks.LambdaInvoke(
        self, config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_NAME_BASE,
        lambda_function=functions[config.BEDROCK_PROCESS_ONDEMAND_OUTPUT_NAME_BASE],
        payload_response_only=True,
        input_path="$",
        output_path = "$",
        payload=sfn.TaskInput.from_object({
            "ondemand_run_datetime.$": "$.ondemand_run_datetime"
        })
    )

    end_state = sfn.Pass(self, "End MAKI operations")

    not_enabled = sfn.Pass(
        self, 
        "NotEnabled",
        result=sfn.Result.from_object({
            "status": "Execution stopped: Bedrock models not enabled"
        }),
        result_path="$.status"
    ).next(end_state)

    already_running = sfn.Pass(
        self, 
        "AlreadyRunning",
        result=sfn.Result.from_object({
            "status": "Execution stopped: maki jobs already running"
        }),
        result_path="$.status"
    ).next(end_state)

    batch_jobs_running = sfn.Pass(
        self,
        "BatchJobsRunning",
        result=sfn.Result.from_object({
            "status": "Execution stopped: maki batch inference jobs in progress"
        }),
        result_path="$.status"
    ).next(end_state)

    no_cases_to_process = sfn.Pass(
        self,
        "NoCasesToProcess",
        result=sfn.Result.from_object({
            "status": "Execution stopped: no cases were found to process"
        }),
        result_path="$.status"
    ).next(end_state)

    routerCheckJobs = config.CHECK_RUNNING_JOBS_NAME_BASE + ':router'
    routerCheckBatchJobs = config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE + ':router'
    routerEnabledModels = "EnabledModelsRouter"  # New unique ID
    router = utils.returnName(config.BEDROCK_INF_METHOD_ROUTER_NAME_BASE)


    # Modified definition to include the enabled models check and execution check
    definition = start_state \
        .next(stepCheckEnabledModels) \
        .next(
            sfn.Choice(self, routerEnabledModels)
            .when(
                sfn.Condition.boolean_equals("$.enabledModels", False),
                not_enabled
            )
            .otherwise(
                stepCheckRunningJobs
                .next(
                    sfn.Choice(self, routerCheckJobs)
                    .when(
                        sfn.Condition.number_greater_than("$.runningExecutions", 1),
                        already_running
                    )
                    .otherwise(
                        stepCheckBatchInferenceJobs
                        .next(
                            sfn.Choice(self, routerCheckBatchJobs)
                            .when(
                                sfn.Condition.number_greater_than("$.incompleteJobsCount", 0),
                                batch_jobs_running
                            )
                            .otherwise(
                                stepGetCases
                                .next(
                                    sfn.Choice(self, router)
                                    .when(
                                        sfn.Condition.number_equals("$.casesTotal", 0),
                                        no_cases_to_process
                                    )
                                    .when(
                                        sfn.Condition.number_less_than("$.casesTotal", config.BEDROCK_ONDEMAND_BATCH_INFLECTION),
                                        sfn.Map(
                                            self,
                                            config.CASE_ITERATOR,
                                            max_concurrency=config.CASE_ITERATOR_MAX_PARALLEL,
                                            items_path="$.cases",
                                            result_path="$.mapResults",
                                            parameters={
                                                "case.$": "$$.Map.Item.Value",
                                                "casesTotal.$": "$.casesTotal",
                                                "ondemand_run_datetime.$": "$.ondemand_run_datetime"
                                            }
                                        ).iterator(
                                            stepBedrockOnDemandInference
                                        )
                                        .next(stepProcessOnDemandOutput)
                                        .next(end_state)
                                    )
                                    .otherwise(
                                        stepBedrockBatchInference
                                        .next(stepPostCheckBatchInferenceJobs)
                                        .next(
                                            sfn.Choice(self, "CheckBatchJobsCompletion")
                                            .when(
                                                sfn.Condition.number_greater_than("$.incompleteJobsCount", 0),
                                                waitForBatchCompletion
                                                .next(stepPostCheckBatchInferenceJobs)
                                            )
                                            .otherwise(
                                                stepProcessBatchOutput
                                                .next(end_state)
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )
        

    state_machine = sfn.StateMachine(
        self, 
        #utils.returnName(config.STATE_MACHINE_NAME_BASE), # this creates a duplicate?  check 
        config.STATE_MACHINE_NAME_BASE, 
        definition=definition,
        role=exec_role,
        state_machine_name=utils.returnName(config.STATE_MACHINE_NAME_BASE),
        timeout=cdk.Duration.seconds(config.STATE_MACHINE_TIMEOUT),
        logs=sfn.LogOptions(
            destination=log_group,
            level=sfn.LogLevel.ALL
        ),
        # Enable X-Ray tracing for AwsSolutions-SF2 compliance
        tracing_enabled=True
    )
    start_state.node.add_dependency(log_group) # add dependency
    state_machine.node.add_dependency(lambdaGetCasesFromCID) # add dependency
    state_machine.node.add_dependency(lambdaBedrockOnDemandInference) # add dependency
    state_machine.node.add_dependency(lambdaBedrockBatchInference) # add dependency
    state_machine.node.add_dependency(lambdaCheckBatchInferenceJobs)
    state_machine.node.add_dependency(lambdaCheckEnabledModels) # add dependency for the new step

    return state_machine