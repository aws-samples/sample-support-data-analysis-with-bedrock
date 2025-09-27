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
    
    # Get both data source functions - both will be deployed
    lambdaGetCasesFromCID = functions[config.GET_CID_CASES_NAME_BASE]
    lambdaGetHealthFromOpenSearch = functions[config.GET_HEALTH_FROM_OPENSEARCH_NAME_BASE]
    
    lambdaBedrockOnDemandInference = functions[config.BEDROCK_ONDEMAND_INF_NAME_BASE]
    lambdaBedrockHealthOnDemandInference = functions[config.BEDROCK_HEALTH_ONDEMAND_INF_NAME_BASE]
    lambdaBedrockBatchInference = functions[config.BEDROCK_BATCH_INF_JOB_NAME_BASE]
    lambdaBedrockBatchInferenceHealth = functions["health-" + config.BEDROCK_BATCH_INF_JOB_NAME_BASE]

    stepCheckEnabledModels = tasks.LambdaInvoke(
        self, config.CHECK_ENABLED_MODELS_NAME_BASE,
        lambda_function=lambdaCheckEnabledModels,
        payload_response_only=True,
        result_path="$.enabledModelsCheck"
    )

    stepCheckRunningJobs = tasks.LambdaInvoke(
        self, config.CHECK_RUNNING_JOBS_NAME_BASE,
        lambda_function=lambdaCheckRunningJobs,
        payload_response_only=True,
        result_path="$.runningJobsCheck"
    )

    stepCheckBatchInferenceJobs = tasks.LambdaInvoke(
        self, f"pre-{config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE}",
        lambda_function=lambdaCheckBatchInferenceJobs,
        payload_response_only=True,
        result_path="$.batchJobsCheck"
    )

    # Create both data source steps
    stepGetCasesFromCID = tasks.LambdaInvoke(
        self, config.GET_CID_CASES_NAME_BASE,
        lambda_function=lambdaGetCasesFromCID,
        payload_response_only=True,
        output_path = "$"
    )

    stepGetHealthFromOpenSearch = tasks.LambdaInvoke(
        self, config.GET_HEALTH_FROM_OPENSEARCH_NAME_BASE,
        lambda_function=lambdaGetHealthFromOpenSearch,
        payload_response_only=True,
        output_path = "$"
    )

    # Create a Pass state that preserves the existing mode
    stepInjectMode = sfn.Pass(
        self, "inject-mode",
        result_path="$.modeConfig",
        parameters={
            "Parameter": {
                "Value.$": "$.mode"
            }
        }
    )

    stepBedrockOnDemandInferenceCase = tasks.LambdaInvoke(
        self, config.BEDROCK_ONDEMAND_INF_NAME_BASE,
        lambda_function=lambdaBedrockOnDemandInference,
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )

    stepBedrockOnDemandInferenceHealth = tasks.LambdaInvoke(
        self, config.BEDROCK_HEALTH_ONDEMAND_INF_NAME_BASE,
        lambda_function=lambdaBedrockHealthOnDemandInference,
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )

    stepBedrockBatchInferenceCase = tasks.LambdaInvoke(
        self, config.BEDROCK_BATCH_INF_JOB_NAME_BASE,
        lambda_function=lambdaBedrockBatchInference,
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )

    stepBedrockBatchInferenceHealth = tasks.LambdaInvoke(
        self, "health-" + config.BEDROCK_BATCH_INF_JOB_NAME_BASE,
        lambda_function=lambdaBedrockBatchInferenceHealth,
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )

    stepPostCheckBatchInferenceJobsCase = tasks.LambdaInvoke(
        self, f"post-{config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE}",
        lambda_function=lambdaCheckBatchInferenceJobs,
        payload_response_only=True,
        result_path="$.batchJobsCheck"
    )

    stepPostCheckBatchInferenceJobsHealth = tasks.LambdaInvoke(
        self, f"health-post-{config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE}",
        lambda_function=lambdaCheckBatchInferenceJobs,
        payload_response_only=True,
        result_path="$.batchJobsCheck"
    )

    stepProcessBatchOutputCase = tasks.LambdaInvoke(
        self, config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE,
        lambda_function=functions[config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE],
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )

    stepProcessBatchOutputHealth = tasks.LambdaInvoke(
        self, "health-" + config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE,
        lambda_function=functions[config.BEDROCK_PROCESS_BATCH_OUTPUT_NAME_BASE],
        payload_response_only=True,
        input_path="$",
        output_path = "$"
    )
    
    # Wait state for batch inference job completion check
    waitForBatchCompletionCase = sfn.Wait(
        self,
        "WaitForBatchCompletion",
        time=sfn.WaitTime.duration(cdk.Duration.minutes(config.POST_BATCH_CHECK_INTERVAL_MIN))
    )

    waitForBatchCompletionHealth = sfn.Wait(
        self,
        "WaitForBatchCompletionHealth",
        time=sfn.WaitTime.duration(cdk.Duration.minutes(config.POST_BATCH_CHECK_INTERVAL_MIN))
    )
    
    stepProcessOnDemandOutputCase = tasks.LambdaInvoke(
        self, config.BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_NAME_BASE,
        lambda_function=functions[config.BEDROCK_PROCESS_CASES_ONDEMAND_OUTPUT_NAME_BASE],
        payload_response_only=True,
        input_path="$",
        output_path = "$",
        payload=sfn.TaskInput.from_object({
            "ondemand_run_datetime.$": "$.ondemand_run_datetime"
        })
    )

    stepProcessOnDemandOutputHealth = tasks.LambdaInvoke(
        self, config.BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_NAME_BASE,
        lambda_function=functions[config.BEDROCK_PROCESS_HEALTH_ONDEMAND_OUTPUT_NAME_BASE],
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

    no_events_to_process = sfn.Pass(
        self,
        "NoEventsToProcess",
        result=sfn.Result.from_object({
            "status": "Execution stopped: no events were found to process"
        }),
        result_path="$.status"
    ).next(end_state)

    routerCheckJobs = config.CHECK_RUNNING_JOBS_NAME_BASE + ':router'
    routerCheckBatchJobs = config.CHECK_BATCH_INFERENCE_JOBS_NAME_BASE + ':router'
    routerEnabledModels = "EnabledModelsRouter"  # New unique ID
    router = utils.returnName(config.BEDROCK_INF_METHOD_ROUTER_NAME_BASE)


    # Modified definition to include the enabled models check and execution check
    definition = start_state.next(stepCheckEnabledModels).next(
        sfn.Choice(self, routerEnabledModels)
        .when(
            sfn.Condition.boolean_equals("$.enabledModelsCheck.enabledModels", False),
            not_enabled
        )
        .otherwise(
            stepCheckRunningJobs
            .next(
                sfn.Choice(self, routerCheckJobs)
                    .when(
                        sfn.Condition.number_greater_than("$.runningJobsCheck.runningExecutions", 1),
                        already_running
                    )
                    .otherwise(
                        stepCheckBatchInferenceJobs
                        .next(
                            sfn.Choice(self, routerCheckBatchJobs)
                            .when(
                                sfn.Condition.number_greater_than("$.batchJobsCheck.incompleteJobsCount", 0),
                                batch_jobs_running
                            )
                            .otherwise(
                                stepInjectMode
                                .next(
                                    sfn.Choice(self, "data-source-router")
                                    .when(
                                        sfn.Condition.string_equals("$.modeConfig.Parameter.Value", "cases"),
                                        stepGetCasesFromCID
                                        .next(
                                            sfn.Choice(self, router)
                                            .when(
                                                sfn.Condition.number_equals("$.eventsTotal", 0),
                                                no_events_to_process
                                            )
                                            .when(
                                                sfn.Condition.number_less_than("$.eventsTotal", config.BEDROCK_ONDEMAND_BATCH_INFLECTION),
                                                sfn.Map(
                                                    self,
                                                    "case-event-iterator",
                                                    max_concurrency=config.EVENT_ITERATOR_MAX_PARALLEL,
                                                    items_path="$.events",
                                                    result_path="$.mapResults",
                                                    item_selector={
                                                        "case.$": "$$.Map.Item.Value",
                                                        "eventsTotal.$": "$.eventsTotal",
                                                        "ondemand_run_datetime.$": "$.ondemand_run_datetime"
                                                    }
                                                ).item_processor(stepBedrockOnDemandInferenceCase)
                                                .next(stepProcessOnDemandOutputCase)
                                                .next(end_state)
                                            )
                                            .otherwise(
                                                stepBedrockBatchInferenceCase
                                                .next(stepPostCheckBatchInferenceJobsCase)
                                                .next(
                                                    sfn.Choice(self, "CheckBatchJobsCompletion")
                                                    .when(
                                                        sfn.Condition.number_greater_than("$.batchJobsCheck.incompleteJobsCount", 0),
                                                        waitForBatchCompletionCase
                                                        .next(stepPostCheckBatchInferenceJobsCase)
                                                    )
                                                    .otherwise(
                                                        stepProcessBatchOutputCase
                                                        .next(end_state)
                                                    )
                                                )
                                            )
                                        )
                                    )
                                    .otherwise(
                                        stepGetHealthFromOpenSearch
                                        .next(
                                            sfn.Choice(self, "health-router")
                                            .when(
                                                sfn.Condition.number_equals("$.eventsTotal", 0),
                                                no_events_to_process
                                            )
                                            .when(
                                                sfn.Condition.number_less_than("$.eventsTotal", config.BEDROCK_ONDEMAND_BATCH_INFLECTION),
                                                sfn.Map(
                                                    self,
                                                    "health-event-iterator",
                                                    max_concurrency=config.EVENT_ITERATOR_MAX_PARALLEL,
                                                    items_path="$.events",
                                                    result_path="$.mapResults",
                                                    item_selector={
                                                        "case.$": "$$.Map.Item.Value",
                                                        "eventsTotal.$": "$.eventsTotal",
                                                        "ondemand_run_datetime.$": "$.ondemand_run_datetime"
                                                    }
                                                ).item_processor(stepBedrockOnDemandInferenceHealth)
                                                .next(stepProcessOnDemandOutputHealth)
                                                .next(end_state)
                                            )
                                            .otherwise(
                                                stepBedrockBatchInferenceHealth
                                                .next(stepPostCheckBatchInferenceJobsHealth)
                                                .next(
                                                    sfn.Choice(self, "CheckHealthBatchJobsCompletion")
                                                    .when(
                                                        sfn.Condition.number_greater_than("$.batchJobsCheck.incompleteJobsCount", 0),
                                                        waitForBatchCompletionHealth
                                                        .next(stepPostCheckBatchInferenceJobsHealth)
                                                    )
                                                    .otherwise(
                                                        stepProcessBatchOutputHealth
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
            )
        )

    state_machine = sfn.StateMachine(
        self, 
        #utils.returnName(config.STATE_MACHINE_NAME_BASE), # this creates a duplicate?  check 
        config.STATE_MACHINE_NAME_BASE, 
        definition_body=sfn.DefinitionBody.from_chainable(definition),
        role=exec_role,
        state_machine_name=utils.returnName(config.STATE_MACHINE_NAME_BASE),
        timeout=cdk.Duration.seconds(config.STATE_MACHINE_TIMEOUT),
        logs=sfn.LogOptions(
            destination=log_group,
            level=sfn.LogLevel.ALL
        ),
        # Enable X-Ray tracing for AwsSolutions-SF2 compliance
        tracing_enabled=True,
        comment="MAKI State Machine - Updated Map syntax"
    )
    start_state.node.add_dependency(log_group) # add dependency
    state_machine.node.add_dependency(lambdaGetCasesFromCID) # add dependency
    state_machine.node.add_dependency(lambdaGetHealthFromOpenSearch) # add dependency
    state_machine.node.add_dependency(lambdaBedrockOnDemandInference) # add dependency
    state_machine.node.add_dependency(lambdaBedrockHealthOnDemandInference) # add dependency
    state_machine.node.add_dependency(lambdaBedrockBatchInference) # add dependency
    state_machine.node.add_dependency(lambdaBedrockBatchInferenceHealth) # add dependency
    state_machine.node.add_dependency(lambdaCheckBatchInferenceJobs)
    state_machine.node.add_dependency(lambdaCheckEnabledModels) # add dependency for the new step

    return state_machine