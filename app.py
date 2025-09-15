#!/usr/bin/env python3
import os

import aws_cdk as cdk

from cdk_nag import AwsSolutionsChecks, NagSuppressions

from maki.maki_stack import MakiFoundations, MakiData

app = cdk.App()
foundations_stack = MakiFoundations(app, "MakiFoundations", description='Machine Augmented Key Insights (MAKI) foundational layer')
data_stack = MakiData(app, "MakiData", description='Machine Augmented Key Insights (MAKI) data layer')

data_stack.add_dependency(foundations_stack)
cdk.Tags.of(app).add("project", "maki")
cdk.Tags.of(app).add("auto-delete", "no")
cdk.Aspects.of(app).add(AwsSolutionsChecks())
NagSuppressions.add_stack_suppressions(foundations_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Wildcard permissions are acceptable for sample code.  Also Bedrock batch inference has no way to make this more granular."},
])
NagSuppressions.add_stack_suppressions(data_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Wildcard permissions are acceptable for sample code."},
    {"id": "AwsSolutions-L1", "reason": "BucketDeployment creates internal Lambda function with CDK-managed runtime version"},
    {"id": "AwsSolutions-IAM4", "reason": "BucketDeployment creates internal Lambda function with CDK-managed runtime version"},
])
app.synth()
