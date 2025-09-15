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

MAKI uses different LLMs of the deployer's choosing.

- A light LLM, such as Amazon Nova Micro, or Anthropic Claude Haiku.
- A sophisticated LLM that excels in reasoning, such as Anthropic Claude Sonnet or Opus.

## What data does MAKI use?
- In this sample code, MAKI uses AWS Enterprise Support cases from the AWS Cloud Intelligence Dashboard (CID) solution.  You can use other sources of AWS Enterprise Support cases.  If you do plan on using CID as the source of AWS Enterprise Support cases, you can deploy it per below.  You only need to deploy the data layer - you do not need to deploy the Amazon QuickSight layer.
https://docs.aws.amazon.com/guidance/latest/cloud-intelligence-dashboards/deployment-in-global-regions.html

## How do I build MAKI?
For this code example, first deploy the AWS Cloud Intelligence Dashboards (CID) per above. This implements a scalable infrastructure that pulls AWS Support Cases.

MAKI will pull the support cases from the S3 directories created by CID above.

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

## How do I run MAKI?

The above CDK actions will deploy the following AWS Step Function.
`maki-<ACCOUNT-ID>-<REGION>-state-machine`

This step function runs MAKI. We suggest scheduling the step function with AWS Event Bridge.

The repo also comes with a utility function below, which starts the step function manually.

`tools/runMaki.py`

Once running, MAKI will examine the number of support cases.  Note the following configuration in `config.py`

`BEDROCK_ONDEMAND_BATCH_INFLECTION`

If the number of cases is at this number or greater, MAKI will create AWS Bedrock Batch Inference jobs.   If it is less, it will use on-demand inference.   AWS Bedrock Batch Inference jobs are very cost effective, and do not impact your account throttling limits.  Note that the minimum number of prompts for AWS Bedrock Batch Inference is 100, so this configuration value cannot be less than that value.

The final outputs are generated in: 

`s3://maki-<ACCOUNT-ID>-<REGION>-report`

These are JSON files.   Consume them with tools such as AWS QuickSight.

MAKI will conduct two levels of analysis.  At the case level, it will create a json file for each case, with the following insights:

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

### Summary

MAKI will also aggregate all of the above generated case insights, and generate an overall analysis.   This is stated in 

`summary.json`


