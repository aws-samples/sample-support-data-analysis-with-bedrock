# Sample Support Data Analysis with Bedrock


## What is this?
This is a sample application for educational purposes which processes Amazon Enterprise Support data with Amazon Bedrock.

The sample application, MAKI (Machine Augmented Key Insights), demonstrates how Amazon Bedrock can analyze Amazon Enterprise Support cases and derive insightful information.  This repo can be studied and used to build other AWS Enterprise Support data analysis pipelines.   This repo is meant as an educational reference and not production code.   The implementer of an organization can use MAKI as a reference to build their own application, which should then be reviewed by the necessary oversight teams at the organization.


## What is MAKI composed of?
MAKI's principal AWS services are:

- Amazon Bedrock
- Amazon S3
- AWS Lambda
- AWS Step Functions

![MAKI Architecture](maki-architecture.png)


## What Large Language Models (LLMs) does MAKI use?
MAKI uses two different LLMs of the deployer's choosing.

- A light LLM, such as Amazon Nova Micro, or Anthropic Claude Haiku.
The below line in `config.py` is used to configure the light LLM.  This model is used to process support data at the record level.   

`BEDROCK_TEXT_MODEL = "us.amazon.nova-micro-v1:0"`

- A sophisticated LLM that excels in reasoning, such as Anthropic Claude Sonnet or Opus.
The below line in `config.py` is used to configure the higher end LLM.  This model aggregates output from the above light LLM, and generates aggregated synthesis.

`BEDROCK_TEXT_MODEL_AGG = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"`

Both of the above models must be enabled on Bedrock.  While the two configured models can be the same, we recommend using two separate models for the above two separate scopes.  It is also very much recommended that cross-region profiles are used (below), noting the `us.` in front of the model ids.

https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html


## How do I build MAKI?
### Pre-requisites
In this sample code, MAKI uses AWS Enterprise support cases from the AWS Cloud Intelligence Dashboard (CID) solution.  You can use other sources of AWS Enterprise Support cases.  If you do plan on using CID as the source of AWS Enterprise Support cases, you can deploy it per below.  You only need to deploy the data layer - you do not need to deploy the Amazon QuickSight layer.

https://docs.aws.amazon.com/guidance/latest/cloud-intelligence-dashboards/deployment-in-global-regions.html

For the reference code in this repo, first deploy the AWS Cloud Intelligence Dashboards (CID) data layer per above. This implements a scalable infrastructure that pulls AWS support cases.

MAKI will pull the support cases from the S3 directories created by CID above.

### Building using CDK 
MAKI is built using CDK, and composed of the following CDK stacks.

- MakiFoundations
- MakiData

MakiFoundations builds the base layer of MAKI.  Run this stack first.
This will create:

- VPC
- CloudWatch
- S3 buckets
- Lambda functions
- Step Functions 
- Amazon Bedrock API functions


`cdk synth MakiFoundations`

`cdk deploy MakiFoundations`


MakiData builds the data layer of MAKI.  Run this stack second.
This will add reference data needed to run MAKI.


`cdk synth MakiData`

`cdk deploy MakiData`


## What data does MAKI use?
The code in this reference repo expects CID to have been deployed per above.

This Lambda function pulls the records from CID;

`maki-<ACCOUNT-ID>-<REGION>-GetCasesFromCID`

And puts the raw support cases in the following S3 bucket.

`maki-<ACCOUNT-ID>-<REGION>-east-1-cases-agg`

If CID is not being used, the above Lambda function can be modified to pull the support cases from an alternative source.

For testing and development purposes, the following utility function also generates synthetic support cases and puts them into the above S3 bucket.

`tools/generate_synth_cases.py`

This tool will create a controlled number of synthetic support cases of various support case categories.   

```sample-support-data-analysis-with-bedrock/tools$ python ./generate_synth_cases.py --help
usage: generate_synth_cases.py [-h] [--min-cases MIN_CASES] [--max-cases MAX_CASES]

Generate synthetic cases

options:
  -h, --help            show this help message and exit
  --min-cases MIN_CASES
                        minimum number of cases generated (default: 1)
  --max-cases MAX_CASES
                        max number of cases generated (default: config.SYNTH_CASES_NUMBER_SEED)
```


## How do I run MAKI?
The above CDK actions will deploy the following AWS Step Function.

`maki-<ACCOUNT-ID>-<REGION>-state-machine`

This step function runs MAKI. We suggest scheduling the step function with AWS Event Bridge.

The repo also comes with a utility function, which starts the step function manually.

`tools/runMaki.py`

This script is meant for development and testing, and checks for each AWS Step Function step as they run.   For actual implementation, it is recommended to schedule the aforementioned AWS Step Function.


```
tools$ python3 ./runMaki.py
Executing: 
  arn:aws:states:us-east-1:903312288484:stateMachine:maki-903312288484-us-east-1-state-machine
State machine execution started: arn:aws:states:us-east-1:903312288484:execution:maki-903312288484-us-east-1-state-machine:a91b4fcc-4a95-47bb-b749-77b302afbca7
{
    "Step Name": "check-enabled_models",
    "Function ARN": "arn:aws:lambda:us-east-1:903312288484:function:maki-903312288484-us-east-1-check-enabled_models"
}
...
Execution succeeded!
Output: {"summary": "{\n  \"summary\": \" <summary output text> ... \"\n}"}
```


Once running, MAKI will examine the number of support cases.  Note the following configuration in `config.py`

`BEDROCK_ONDEMAND_BATCH_INFLECTION = 100`

If the number of cases is at this number or greater, MAKI will create AWS Bedrock Batch Inference jobs.   If it is less, it will use on-demand inference.   AWS Bedrock Batch Inference jobs are very cost effective, and do not impact your account throttling limits.  Note that the minimum number of prompts for AWS Bedrock Batch Inference is 100, so this configuration value cannot be less than that value.

You can use the following AWS CloudWatch log group to observe.

`maki-<ACCOUNT-ID>-<REGION>-log-group`

The final outputs are generated in: 

`s3://maki-<ACCOUNT-ID>-<REGION>-report`

These are JSON files.   Consume them with tools such as AWS QuickSight.

MAKI will conduct two levels of analysis.  At the case level, it will create a JSON file for each case, with the following insights:

### Cases
`category`
This categorizes the support case into the common categories.

`category_explanation`
This explains the reasoning behind the categorization.

`case_summary`
This summarizes the case.

`sentiment`
This is the sentiment, based on the case.

`suggested_action`
This gives a suggested action, based on the case.

`suggestion_link`
This is a link to documentation to the suggested action.

The following is an example output of a case analysis for a fictitious customer.

```
{
  "caseId": "case-961341536468-muen-2025-f09f14aa1c569098",
  "displayId": "173983009900080",
  "status": "pending-customer-action",
  "serviceCode": "service-bedrock",
  "timeCreated": "2025-02-17T22:08:19.234Z",
  "submittedBy": "Joe.Cho@makita-nowhere.com",
  "category": "customer-question",
  "category_explanation": "The customer is asking a technical question about how to use DeepSeek models in Bedrock.",
  "case_summary": "The customer is inquiring about the steps to start using DeepSeek models within Amazon Bedrock.",
  "sentiment": "Neutral",
  "suggested_action": "Refer the customer to the Amazon Bedrock documentation for detailed instructions on how to use DeepSeek models. Additionally, provide guidance on setting up the necessary permissions and configurations.",
  "suggestion_link": "https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html"
}
```

### Summary

MAKI will also aggregate all of the above generated case insights, and generate an overall analysis.   This is stated in 

`summary.json`

Below is an example output from `summary.json` of a fictional customer.

```
{"summary": "{\n  \"summary\": \"The customer's experience on AWS reveals significant resilience challenges across their infrastructure. A prominent pattern involves connectivity issues between AWS services and on-premises systems via VPN connections, resulting in frequent timeouts, latency, and service disruptions. These customer dependency issues are causing negative sentiment as they impact application functionality and user experience. Additionally, the customer faces throttling problems due to exceeding service quotas in EC2 and API Gateway services, particularly following software or SDK updates that weren't adequately tested before deployment. There are also capacity constraints with Insufficient Capacity Errors when scaling EC2 instances, and monitoring gaps leading to critical incidents when resources reach capacity thresholds without proper alerting. Other challenges include unexpected downtime from managed service upgrades, deployment issues with AWS CDK, and database failures following deployments. The overall sentiment trends negative, indicating customer frustration with recurring service disruptions and performance degradation across their AWS environment.\",\n  \"plan\": \"To improve the customer's resilience on AWS, we should implement a comprehensive approach: 1) Conduct a thorough assessment of the VPN connectivity between AWS and on-premises systems, considering Direct Connect for critical workloads to provide more stable and predictable network performance; 2) Establish proactive quota management with Service Quotas monitoring and CloudWatch alarms to prevent throttling issues, and implement proper testing protocols for SDK updates before production deployment; 3) Develop a capacity management strategy including reserved instances and capacity reservations across multiple Availability Zones to mitigate ICE errors; 4) Implement comprehensive monitoring with CloudWatch for all critical resources, especially volume capacity thresholds and network connectivity metrics; 5) Create a change management process for deployments and upgrades with proper testing environments; 6) Architect for resilience by implementing circuit breakers, retries with exponential backoff, and fallback mechanisms for external dependencies; 7) Schedule a Well-Architected Framework review focusing on the reliability pillar to identify and address resilience gaps; and 8) Provide targeted training for the customer's team on AWS best practices for high availability, disaster recovery, and managing hybrid cloud environments.\"\n}"}
```

## How does MAKI work?
MAKI uses reference data to augment the prompt.

The reference data is in the following S3 bucket.

`maki-<ACCOUNT-ID>-<REGION>-examples` 

These can be enabled by placing them in the following array in `config.py` 

```
###
# Support Case Categories
CATEGORIES = [
    'limit-reached', 
    'customer-release',
    'development-issue',
    'customer-networking',
    'throttling',
    'ice-error',
    'feature-request',
    'customer-dependency',
    'aws-release',
    'customer-question',
    'exceeding-capability',
    'lack-monitoring',
    'security-issue',
    'service-event',
    'transient-issues',
    'upgrade-management'
]
```

This reference data can be further fine-tuned and modified, adapting to the use case.

MAKI takes each record to be processed, and determines which of the above categories it belongs to, and derives insights at the record level.  The aggregate analysis then follows, using all of the individual processed outputs, to derive a comprehensive view of all the records.


## What's in development for MAKI?

### Amazon S3 Vectors
With MAKI's Amazon S3-based data architecture, implementing vector support using Amazon S3 Vectors aligns well.  This additional stack is actively being developed! 

https://aws.amazon.com/blogs/aws/introducing-amazon-s3-vectors-first-cloud-storage-with-native-vector-support-at-scale/

### Agents for MAKI
While using traditional tools such as Business Intelligence systems can consume the JSON files generated by MAKI, MCP servers allow for an agentic interface to this data.   This is actively being developed!