# Sample Support Data Analysis with Bedrock

## What is this?
This is a sample application for educational purposes which processes Amazon Enterprise Support data with Amazon Bedrock.

The sample application, MAKI (Machine Augmented Key Insights), demonstrates how Amazon Bedrock can analyze Amazon Enterprise Support cases and derive insightful information.  This repo can be studied and used to build other AWS Enterprise Support data analysis pipelines.   This repo is meant as an educational reference and not production code.   The implementor of an organization can use MAKI as reference to build their own application, which should then be reviewed by the necessary oversight teams at the organization.

## What is MAKI composed of?

MAKI's principal AWS services would be:

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
MAKI is built using CDK, and composed of the below CDK stacks.

- MakiFoundations
- MakiData

MakiFoundations builds the base layer of Maki.  Run this stack first.
This will create:

- VPC
- CloudWatch
- S3 buckets
- Lambda functions
- Step Functions 
- Amazon Bedrock API functions

`cdk synth MakiFoundations`

`cdk deploy MakiFoundations`

MakiData builds the data layer of Maki.  Run this stack second.
This will add reference data needed to run Maki.

`cdk synth MakiData`

`cdk deploy MakiData`

Additional stacks are in the midst of development.