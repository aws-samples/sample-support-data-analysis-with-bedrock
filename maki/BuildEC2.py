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
    
    sg.add_ingress_rule(
        peer=ec2.Peer.ipv4("192.168.0.0/24"),
        connection=ec2.Port.tcp(22),
        description="Allow SSH access from trusted network",
    )

    sg.node.add_dependency(vpc)
    return sg
