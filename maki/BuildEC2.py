"""
MAKI EC2 and VPC Components Builder

This module creates the foundational networking infrastructure for MAKI, including VPC, 
subnets, security groups, and VPC Flow Logs for comprehensive network monitoring.

Purpose:
- Establish secure networking foundation for MAKI components
- Create VPC with public and private subnets across multiple AZs
- Configure security groups with least-privilege access
- Enable VPC Flow Logs for network monitoring and compliance

Components Created:
- VPC with 3 Availability Zones (required for OpenSearch Serverless)
- Public and private subnets with appropriate routing
- Security group with restricted SSH access
- VPC Flow Logs with CloudWatch integration

Key Features:
- Multi-AZ deployment for high availability
- Private subnets with NAT Gateway for secure outbound access
- VPC Flow Logs for network traffic monitoring
- Security group with restricted access from trusted networks only
- Proper tagging for resource identification

Usage:
- Called by MakiFoundations stack during deployment
- VPC is used by OpenSearch Serverless, Lambda functions, and SageMaker
- Security group provides controlled access for development resources
"""

import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_logs as logs
import sys
sys.path.append('..')

def buildVPC(self, makiRole):
    # Create CloudWatch Log Group for VPC Flow Logs
    flow_log_group = logs.LogGroup(
        self, "maki-vpc-flow-logs",
        log_group_name="/aws/vpc/flowlogs",
        retention=logs.RetentionDays.ONE_WEEK,
        removal_policy=cdk.RemovalPolicy.DESTROY
    )
    
    vpc = ec2.Vpc(self, "maki-vpc",
        # make this configurable
        # we need at leats 3 AZs for OpenSearch
        availability_zones=['us-east-1a','us-east-1b','us-east-1c'],
        subnet_configuration=[
            ec2.SubnetConfiguration(
                cidr_mask=24,
                name="private",
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            ec2.SubnetConfiguration(
                cidr_mask=24,
                name="public",
                subnet_type=ec2.SubnetType.PUBLIC
            )
        ],
        # Enable VPC Flow Logs
        flow_logs={
            "CloudWatchFlowLog": ec2.FlowLogOptions(
                destination=ec2.FlowLogDestination.to_cloud_watch_logs(flow_log_group),
                traffic_type=ec2.FlowLogTrafficType.ALL
            )
        }
    )

    vpc.node.add_dependency(makiRole)
    return vpc

def buildSecurityGroup(self, vpc):
    sg = ec2.SecurityGroup(self, "maki-sg",
        vpc=vpc,
        description="maki-sg",
        allow_all_outbound=True
    )        
    
    cdk.Tags.of(sg).add("Name", "maki-sg")
    
    sg.add_ingress_rule(
        peer=ec2.Peer.ipv4("192.168.0.0/24"),
        connection=ec2.Port.tcp(22),
        description="Allow SSH access from trusted network",
    )

    sg.node.add_dependency(vpc)
    return sg
