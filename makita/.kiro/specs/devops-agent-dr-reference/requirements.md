# Requirements Document

## Introduction

This document defines the requirements for a reference architecture demonstrating Amazon DevOps Agent in a Disaster Recovery (DR) scenario. The architecture showcases multi-region RDS Postgres failover with pre/post validation checks, incident management workflows integrating ServiceNow, Slack, and AWS Support, and a custom MCP server running on Amazon Bedrock AgentCore with Guardrails, Policy, and Identity features. All code is written in Python using Boto3 for AWS service interactions.

## Glossary

- **DevOps_Agent**: The Amazon DevOps Agent that orchestrates DR workflows, executes failover operations, and coordinates incident management actions.
- **RDS_Primary_Instance**: The Amazon RDS PostgreSQL database instance in the Primary_Region serving as the active read-write database.
- **RDS_Read_Replica**: The Amazon RDS PostgreSQL cross-region read replica in the DR_Region that can be promoted during failover.
- **Primary_Region**: The AWS region us-east-1 where the RDS Postgres instance normally operates under steady-state conditions.
- **DR_Region**: The AWS region us-east-2 hosting the cross-region read replica designated to be promoted during a disaster recovery event.
- **Pre_Check_Engine**: The component responsible for running validation checks before initiating RDS Postgres failover.
- **Post_Check_Engine**: The component responsible for running validation checks after RDS Postgres failover completes.
- **Incident_Manager**: The component responsible for creating and coordinating incident management artifacts across ServiceNow, Slack, and AWS Support.
- **MCP_Server**: A custom Model Context Protocol server running on Amazon Bedrock AgentCore that exposes tools for the DevOps Agent.
- **AgentCore**: Amazon Bedrock AgentCore, the managed runtime environment hosting the custom MCP server.
- **Guardrails**: Amazon Bedrock Guardrails applied to the MCP server to enforce content and action safety policies.
- **AgentCore_Policy**: The authorization policy configured in AgentCore that governs which actions the MCP server can perform.
- **AgentCore_Identity**: The identity configuration in AgentCore that authenticates callers using AWS Cognito as the identity provider.
- **Lambda_Script**: An AWS Lambda function invoked by the MCP server to generate a comprehensive summary of the DR failover event from start to finish.
- **ServiceNow_Ticket**: An incident ticket created via the official ServiceNow SDK APIs against a stub server to demonstrate the ITSM integration pattern.
- **Slack_Channel**: A Slack channel named "makita-dr-YYYYMMDD" (where YYYYMMDD is the current date) created for real-time incident coordination and action logging during the DR exercise.
- **AWS_Support_Ticket**: A support case created via the actual Boto3 Support SDK APIs against a stub to demonstrate the AWS Support integration pattern without filing real cases.
- **Parameter_Store**: AWS Systems Manager Parameter Store, the service used to store and retrieve all configurable items for the DR workflow.
- **Resource_Prefix**: The naming prefix "makita-dr-" applied to all created components and resources in the reference architecture.
- **Cognito_User_Pool**: The AWS Cognito User Pool used as the identity provider for AgentCore_Identity, authenticating callers of the MCP_Server.

## Requirements

### Requirement 1: RDS Postgres Multi-Region Failover

**User Story:** As a DevOps engineer, I want the DevOps Agent to failover my RDS Postgres database from the primary region to the DR region, so that database availability is maintained during a disaster.

#### Acceptance Criteria

1. WHEN a DR failover is initiated, THE DevOps_Agent SHALL identify the RDS_Primary_Instance in the Primary_Region and the corresponding RDS_Read_Replica in the DR_Region.
2. WHEN the failover process begins, THE DevOps_Agent SHALL promote the RDS_Read_Replica in the DR_Region to a standalone read-write instance.
3. WHEN the RDS_Read_Replica is promoted, THE DevOps_Agent SHALL update application connection strings or DNS records to point to the promoted instance in the DR_Region.
4. WHEN the promoted instance is accepting connections, THE DevOps_Agent SHALL verify that the promoted instance is operating in read-write mode.
5. IF the failover process encounters an error at any step, THEN THE DevOps_Agent SHALL log the error details and halt the failover sequence.

### Requirement 2: Pre-Failover Validation Checks

**User Story:** As a DevOps engineer, I want pre-checks to run before failover begins, so that I can confirm the DR environment is ready to receive database traffic.

#### Acceptance Criteria

1. WHEN a DR failover is initiated, THE Pre_Check_Engine SHALL execute all registered pre-check validations before the failover process starts.
2. THE Pre_Check_Engine SHALL verify that the RDS_Read_Replica in the DR_Region is reachable and in a healthy replication state.
3. THE Pre_Check_Engine SHALL verify that the replication lag between the RDS_Primary_Instance and the RDS_Read_Replica is within an acceptable threshold.
4. THE Pre_Check_Engine SHALL verify that the DR_Region network configuration (VPC, security groups, subnets) permits database connectivity.
5. IF any pre-check validation fails, THEN THE Pre_Check_Engine SHALL report the failure details and prevent the failover from proceeding.
6. WHEN all pre-checks pass, THE Pre_Check_Engine SHALL return a success status to the DevOps_Agent to authorize failover.

### Requirement 3: Post-Failover Validation Checks

**User Story:** As a DevOps engineer, I want post-checks to run after failover completes, so that I can confirm the promoted database is functioning correctly.

#### Acceptance Criteria

1. WHEN the RDS Postgres failover completes, THE Post_Check_Engine SHALL execute all registered post-check validations.
2. THE Post_Check_Engine SHALL verify that the promoted RDS instance in the DR_Region is accepting read-write connections.
3. THE Post_Check_Engine SHALL verify that application endpoints can successfully query the promoted database.
4. THE Post_Check_Engine SHALL verify that DNS or connection string routing directs database traffic to the promoted instance in the DR_Region.
5. IF any post-check validation fails, THEN THE Post_Check_Engine SHALL report the failure details to the DevOps_Agent for remediation.
6. WHEN all post-checks pass, THE Post_Check_Engine SHALL return a success status confirming the DR failover is complete.

### Requirement 4: Incident Management - ServiceNow Integration

**User Story:** As a DevOps engineer, I want the DevOps Agent to create ServiceNow incident tickets using the official SDK APIs against a stub server, so that the reference architecture demonstrates the ServiceNow integration pattern without requiring a live ServiceNow instance.

#### Acceptance Criteria

1. THE reference architecture SHALL include a ServiceNow stub server that accepts and displays incoming API requests.
2. THE Incident_Manager SHALL use the official ServiceNow SDK APIs to communicate with the ServiceNow stub server.
3. WHEN a DR failover is initiated, THE Incident_Manager SHALL create a ServiceNow_Ticket with the DR event summary, affected database resources, and timestamp via the official SDK APIs.
4. THE Incident_Manager SHALL populate the ServiceNow_Ticket with the failover status (in-progress, completed, failed).
5. WHEN the failover status changes, THE Incident_Manager SHALL update the ServiceNow_Ticket with the current status and relevant details via the official SDK APIs.
6. THE ServiceNow stub server SHALL log and display all received requests for demonstration and verification purposes.
7. IF the ServiceNow stub server is unreachable, THEN THE Incident_Manager SHALL retry the request with exponential backoff and log the connectivity failure.

### Requirement 5: Incident Management - Slack Integration

**User Story:** As a DevOps engineer, I want Slack to be the primary interface for communicating with the DevOps Agent during DR, so that I can ask questions, get status updates, and coordinate the DR exercise in real time.

#### Acceptance Criteria

1. WHEN a DR failover exercise begins, THE Incident_Manager SHALL create a Slack_Channel named "makita-dr-YYYYMMDD" where YYYYMMDD is the current date.
2. THE Incident_Manager SHALL post an initial message to the Slack_Channel containing the DR event summary, affected database resources, and current status before the DR exercise starts.
3. WHEN the DevOps_Agent performs any action during the DR workflow, THE Incident_Manager SHALL log that action as a message in the Slack_Channel.
4. WHEN the failover status changes, THE Incident_Manager SHALL post a status update message to the Slack_Channel.
5. WHEN a user mentions "makita" in the Slack_Channel with a question, THE DevOps_Agent SHALL respond in the Slack_Channel with the requested information about the DR event.
6. WHEN a user asks about the status of the DR event in the Slack_Channel, THE DevOps_Agent SHALL respond with the current failover status, completed steps, and pending actions.
7. IF the Slack API is unreachable, THEN THE Incident_Manager SHALL retry the request with exponential backoff and log the connectivity failure.

### Requirement 6: Incident Management - AWS Support Integration

**User Story:** As a DevOps engineer, I want the DevOps Agent to create AWS Support tickets using the actual Boto3 SDK APIs against a stub, so that the reference architecture demonstrates the AWS Support integration pattern without filing actual support cases.

#### Acceptance Criteria

1. THE reference architecture SHALL include an AWS Support stub that intercepts Boto3 Support API calls and logs the requests.
2. THE Incident_Manager SHALL use the actual Boto3 Support SDK APIs to create and update support cases.
3. WHEN a DR failover is initiated, THE Incident_Manager SHALL create an AWS_Support_Ticket with the DR event summary, affected AWS resources, and severity level via the Boto3 Support APIs.
4. THE Incident_Manager SHALL include the Primary_Region and DR_Region identifiers in the AWS_Support_Ticket.
5. WHEN the failover completes or fails, THE Incident_Manager SHALL update the AWS_Support_Ticket with the final status via the Boto3 Support APIs.
6. THE AWS Support stub SHALL log and display all received API calls for demonstration and verification purposes.
7. IF the AWS Support stub is unreachable, THEN THE Incident_Manager SHALL retry the request with exponential backoff and log the connectivity failure.

### Requirement 7: Custom MCP Server on AgentCore

**User Story:** As a DevOps engineer, I want a custom MCP server running on AgentCore that exposes a failover summary tool to the DevOps Agent, so that the agent can generate a comprehensive summary of the entire DR failover event.

#### Acceptance Criteria

1. THE MCP_Server SHALL run on AgentCore as a managed service.
2. THE MCP_Server SHALL expose tool definitions that the DevOps_Agent can discover and invoke.
3. WHEN the DevOps_Agent invokes the summary tool on the MCP_Server, THE MCP_Server SHALL execute the Lambda_Script to generate a summary of the overall failover event from start to finish.
4. THE Lambda_Script SHALL collect failover event data including pre-check results, failover steps, post-check results, and incident management actions taken.
5. THE MCP_Server SHALL return the generated failover summary to the DevOps_Agent.
6. IF the Lambda_Script execution fails, THEN THE MCP_Server SHALL return an error response with failure details to the DevOps_Agent.

### Requirement 8: Bedrock Guardrails Integration

**User Story:** As a DevOps engineer, I want Guardrails applied to the MCP server, so that the DevOps Agent actions are constrained to safe and approved operations.

#### Acceptance Criteria

1. THE MCP_Server SHALL enforce Guardrails on all incoming tool invocation requests.
2. WHEN a tool invocation request violates a Guardrail policy, THE MCP_Server SHALL reject the request and return a policy violation response.
3. THE MCP_Server SHALL log all Guardrail evaluation results for audit purposes.

### Requirement 9: AgentCore Policy and Identity

**User Story:** As a DevOps engineer, I want AgentCore Policy and Identity configured with AWS Cognito for the MCP server, so that only authorized agents and users can invoke DR tools.

#### Acceptance Criteria

1. THE MCP_Server SHALL authenticate callers using AgentCore_Identity backed by the Cognito_User_Pool before processing tool invocation requests.
2. WHEN an unauthenticated caller attempts to invoke a tool, THE MCP_Server SHALL reject the request with an authentication error.
3. THE MCP_Server SHALL authorize tool invocations against AgentCore_Policy rules.
4. THE AgentCore_Policy SHALL restrict invocation of the Lambda_Script that generates the failover event summary to only the identity authenticated through the Cognito_User_Pool.
5. WHEN an authenticated caller lacks the required policy permissions, THE MCP_Server SHALL reject the request with an authorization error.
6. THE MCP_Server SHALL log all authentication and authorization decisions for audit purposes.

### Requirement 10: Configuration Management via Parameter Store

**User Story:** As a DevOps engineer, I want all configurable items stored in AWS Systems Manager Parameter Store, so that DR workflow configuration is centralized, versioned, and securely managed.

#### Acceptance Criteria

1. THE DevOps_Agent SHALL retrieve all configurable items from Parameter_Store at the start of the DR workflow.
2. THE Parameter_Store SHALL contain configuration for RDS instance identifiers, region mappings, replication lag thresholds, and DNS record details.
3. THE Parameter_Store SHALL contain configuration for ServiceNow API endpoint, Slack channel identifier, and AWS Support case parameters.
4. THE Parameter_Store SHALL contain configuration for MCP_Server endpoint, Lambda_Script ARN, and Guardrails identifiers.
5. WHEN a configuration value is missing from Parameter_Store, THE DevOps_Agent SHALL report the missing parameter and halt the DR workflow.
6. THE DevOps_Agent SHALL use SecureString parameter type in Parameter_Store for sensitive configuration values such as API keys and credentials.

### Requirement 11: Resource Naming Convention

**User Story:** As a DevOps engineer, I want all created components to follow a consistent naming convention, so that DR resources are easily identifiable and organized.

#### Acceptance Criteria

1. THE DevOps_Agent SHALL prefix all created AWS resources and components with the Resource_Prefix "makita-dr-".
2. THE Parameter_Store parameters SHALL use the Resource_Prefix "makita-dr-" as a path prefix for all DR configuration parameters.
3. THE Lambda_Script SHALL be named with the Resource_Prefix "makita-dr-" followed by a descriptive function name.

### Requirement 12: CloudWatch Dashboard for DR Monitoring

**User Story:** As a DevOps engineer, I want a CloudWatch Dashboard that shows the RDS cluster metrics, so that I can visually monitor and demonstrate the region failover.

#### Acceptance Criteria

1. THE DevOps_Agent SHALL create a CloudWatch Dashboard named with the Resource_Prefix "makita-dr-" followed by "dashboard".
2. THE CloudWatch Dashboard SHALL display RDS metrics for the RDS_Primary_Instance in the Primary_Region including connection count, CPU utilization, and database connections.
3. THE CloudWatch Dashboard SHALL display RDS metrics for the RDS_Read_Replica in the DR_Region including replication lag, connection count, and CPU utilization.
4. THE CloudWatch Dashboard SHALL display cross-region comparison widgets that visually demonstrate the failover transition from Primary_Region to DR_Region.
5. WHEN the failover completes, THE CloudWatch Dashboard SHALL reflect the shift in active database traffic from the Primary_Region to the DR_Region.
