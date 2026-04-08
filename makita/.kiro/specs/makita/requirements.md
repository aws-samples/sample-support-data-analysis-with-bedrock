# Requirements Document

## Introduction

MAKITA (Machine Augmented Key Infrastructure Technology Automation) is a technical reference architecture demonstrating the use of Amazon DevOps Agent and Amazon AgentCore in a disaster recovery (DR) scenario. The project provisions a multi-region PostgreSQL cluster across us-east-1 (primary) and us-west-2 (secondary/DR) using AWS CloudFormation. An MCP server, built with the Strands SDK and hosted in Amazon AgentCore, orchestrates automated failover of the PostgreSQL cluster. The MCP server is driven by Amazon DevOps Agent, enabling AI-assisted disaster recovery operations.

## Glossary

- **MAKITA**: Machine Augmented Key Infrastructure Technology Automation — the overall project and system name.
- **MCP_Server**: The Model Context Protocol server built using the Strands SDK, responsible for executing PostgreSQL cluster failover operations. Hosted in Amazon AgentCore.
- **DevOps_Agent**: Amazon DevOps Agent — the AI agent that drives the MCP_Server to perform disaster recovery operations.
- **AgentCore**: Amazon AgentCore — the hosting platform for the MCP_Server.
- **Primary_Region**: The AWS region us-east-1, hosting the primary PostgreSQL cluster.
- **DR_Region**: The AWS region us-west-2, hosting the secondary/disaster recovery PostgreSQL cluster.
- **PostgreSQL_Cluster**: The multi-region PostgreSQL database cluster composed of a primary instance in us-east-1 and a replica instance in us-west-2.
- **Parameter_Store**: AWS Systems Manager Parameter Store — the centralized store for all MAKITA configuration values.
- **CloudFormation_Templates**: AWS CloudFormation templates and Python deployment scripts that define and provision all MAKITA infrastructure resources. CloudFormation stacks handle PostgreSQL and supporting AWS resources; Python scripts (`deploy_agentcore.py`, `deploy_devops_agent.py`, `deploy_kiro_agent.py`) handle AgentCore and DevOps Agent resources.
- **Failover**: The process of promoting the DR_Region PostgreSQL replica to primary and redirecting traffic away from the failed Primary_Region.
- **AgentCore_Policies**: Amazon AgentCore policies — access control policies applied to the AgentCore-hosted MCP_Server that restrict which actions the MCP_Server can perform, including target resource constraints, region constraints, and principal constraints.
- **AgentCore_Identities**: Amazon AgentCore identities — the identity configurations assigned to the MCP_Server within AgentCore that determine the IAM role and permissions used during failover operations.
- **Bedrock_Guardrails**: Amazon Bedrock Guardrails — safety and governance controls applied to the MCP_Server to constrain and govern the actions the MCP_Server can perform during AI-assisted operations.
- **AWS_Support_Stub_Server**: A stub MCP server that simulates the AWS Support API, enabling DevOps_Agent to create and update AWS Support cases without connecting to the real AWS Support service.
- **ServiceNow_Stub_Server**: A stub MCP server that simulates the ServiceNow API, enabling DevOps_Agent to create and update ServiceNow tickets and incidents without connecting to the real ServiceNow service.
- **AWS_Support_Case**: A support case created via the AWS_Support_Stub_Server to track the disaster recovery operation in AWS Support.
- **ServiceNow_Ticket**: A ticket/incident created via the ServiceNow_Stub_Server to track the disaster recovery operation in ServiceNow.
- **Event_Log_File**: A markdown (.md) file that records timestamped events for a specific AWS_Support_Case or ServiceNow_Ticket throughout the disaster recovery process.
- **CloudWatch_Dashboard**: An Amazon CloudWatch dashboard provisioned via CloudFormation that visualizes the PostgreSQL_Cluster failover process across the Primary_Region and DR_Region.
- **Pre_Checks**: The set of verification steps performed by DevOps_Agent on the PostgreSQL_Cluster before initiating a failover, including replication health, primary instance status, and replica readiness.
- **Post_Checks**: The set of verification steps performed by DevOps_Agent on the PostgreSQL_Cluster after completing a failover, including new primary health, endpoint updates, and replication establishment from the new primary.
- **Failover_Sequence**: The ordered series of phases — Pre_Checks, Failover execution, and Post_Checks — that DevOps_Agent orchestrates when performing a disaster recovery operation.
- **Pre_Check_MCP_Server**: A Model Context Protocol server built using the Strands SDK, responsible for performing database pre-check operations before failover. Hosted in Amazon AgentCore. Exposes tools for DevOps_Agent to verify replication health, primary instance status, and replica readiness.
- **Post_Check_MCP_Server**: A Model Context Protocol server built using the Strands SDK, responsible for performing database post-check operations after failover. Hosted in Amazon AgentCore. Exposes tools for DevOps_Agent to verify new primary health, endpoint updates in Parameter_Store, and replication from the new primary.
- **README_File**: The README.md file at the root of the MAKITA project repository that describes the project, its architecture, and provides getting started and operational instructions.
- **Test_Scripts**: Comprehensive testing scripts that validate each functionality of the MAKITA project, including infrastructure provisioning, configuration management, database operations, MCP server functionality, policy enforcement, guardrail governance, failover orchestration, ticketing integration, event logging, dashboard provisioning, and DevOps Agent chat interactions.
- **Mandatory_Resource_Tags**: A set of AWS resource tags that must be applied to every AWS resource created by the CloudFormation_Templates. The mandatory tags are: `auto-delete` with value `no`, and `Env` with value `prod1`.
- **Env_Tag**: The AWS resource tag with key `Env` and value `prod1`, used to identify resources belonging to the MAKITA production environment. AgentCore_Policies use the Env_Tag to enforce that MCP servers only operate on resources tagged with `Env=prod1`.
- **Architectural_Diagram**: A standalone Mermaid-syntax diagram artifact that visualizes the MAKITA system architecture, including all major components, their relationships, and data flows across the Primary_Region and DR_Region.
- **AgentCore_Gateway**: An Amazon AgentCore Gateway (`makita-mcp-gateway`) that provides a unified MCP entry point for all MAKITA tools. DevOps Agent and Kiro agent connect through the gateway to reach individual MCP server runtimes. Each gateway target has an associated Cedar policy.
- **Cedar_Policies**: Cedar authorization policies attached to AgentCore Gateway targets that restrict which tool actions each MCP server can perform. Stored as standalone files in `policies/agentcore/`.
- **Guardrail_Configs**: Standalone JSON configuration files in `policies/guardrails/` that define Bedrock Guardrail settings for each MCP server. Deployed via `deploy_agentcore.py` alongside the AgentCore Runtimes.
- **DevOps_Agent_Space**: The Amazon DevOps Agent Space (`makita-agentspace`) created via `deploy_devops_agent.py`, including an operator IAM role, web app, and log group.
- **Kiro_Agent_Config**: The Kiro agent configuration (`.kiro/agents/makita-ops.json`) and gateway proxy (`mcp-servers/agentcore_gateway_proxy.py`) deployed via `deploy_kiro_agent.py` to enable Kiro IDE-based DR operations through the AgentCore Gateway.
- **Secrets_Manager_Secret**: An AWS Secrets Manager secret (`makita-db-master-secret`) provisioned in the CloudFormation stack to store the PostgreSQL master password securely.

## Requirements

### Requirement 1: Infrastructure Provisioning via CloudFormation Stacks and Deployment Scripts

**User Story:** As a DevOps engineer, I want all infrastructure to be provisioned through CloudFormation stacks and automated deployment scripts, so that the environment is reproducible, version-controlled, and managed consistently.

#### Acceptance Criteria

1. THE CloudFormation_Templates SHALL provision PostgreSQL and supporting AWS resources across two CloudFormation stacks: `makita-postgresql-stack` (us-east-1) for the primary instance, IAM roles, Parameter Store, Secrets Manager, and Bedrock Guardrails; and `makita-postgresql-replica-stack` (us-west-2) for the cross-region read replica. (Updated: originally specified a single stack; implementation uses two stacks under `infrastructure/workloads/postgresql/` plus Python deployment scripts for AgentCore and DevOps Agent resources.)
2. THE CloudFormation_Templates SHALL contain resources for the Primary_Region (us-east-1) in `makita-postgresql-stack` and resources for the DR_Region (us-west-2) in `makita-postgresql-replica-stack`. (Updated: resources are split across two region-specific stacks rather than a single stack.)
3. THE CloudFormation_Templates SHALL include the PostgreSQL_Cluster resources, IAM roles, Parameter_Store parameters, Secrets_Manager_Secret, and Bedrock_Guardrails. AgentCore resources (Runtimes, Gateway, Cedar_Policies, Guardrail_Configs) are deployed via `scripts/deploy_agentcore.py`. DevOps_Agent_Space is deployed via `scripts/deploy_devops_agent.py`. Kiro_Agent_Config is deployed via `scripts/deploy_kiro_agent.py`. (Updated: MCP server registrations, AgentCore policies/identities, and the CloudWatch Dashboard are no longer in the CFN stacks.)
4. WHEN the CloudFormation stacks are deployed, THE CloudFormation_Templates SHALL prefix all resource names with "makita-".
5. IF a CloudFormation stack deployment fails, THEN THE CloudFormation_Templates SHALL roll back all resources created during the failed deployment.
6. THE deployment scripts (`deploy.sh`) SHALL orchestrate deployment of both CloudFormation stacks and all Python deployment scripts in the correct order. (Updated: originally stated no additional stacks required; implementation uses `deploy.sh` with targets `postgresql`, `postgresql-dr`, `agentcore`, `devops-agent`, `kiro-agent`.)

### Requirement 2: Configuration Management via Parameter Store

**User Story:** As a DevOps engineer, I want all configuration values stored in Parameter Store, so that configuration is centralized, auditable, and decoupled from application code.

#### Acceptance Criteria

1. THE CloudFormation_Templates SHALL store all MAKITA configuration values in Parameter_Store.
2. WHEN a configuration value is stored, THE CloudFormation_Templates SHALL prefix the parameter name with "/makita/".
3. THE MCP_Server SHALL read all runtime configuration from Parameter_Store.
4. WHEN the MCP_Server starts, THE MCP_Server SHALL retrieve the current PostgreSQL_Cluster connection endpoints from Parameter_Store.

### Requirement 3: Multi-Region PostgreSQL Cluster

**User Story:** As a DevOps engineer, I want a multi-region PostgreSQL cluster with a primary in us-east-1 and a replica in us-west-2, so that the database can survive a regional outage.

#### Acceptance Criteria

1. THE CloudFormation_Templates SHALL provision a PostgreSQL primary instance in the Primary_Region (us-east-1).
2. THE CloudFormation_Templates SHALL provision a PostgreSQL replica instance in the DR_Region (us-west-2).
3. WHILE the Primary_Region is healthy, THE PostgreSQL_Cluster SHALL replicate data from the primary instance to the replica instance.
4. THE CloudFormation_Templates SHALL store the primary and replica endpoint addresses in Parameter_Store.
5. WHEN the PostgreSQL_Cluster is provisioned, THE CloudFormation_Templates SHALL configure the replica instance for cross-region replication from the primary instance.
6. THE CloudFormation_Templates SHALL provision an `AWS::SecretsManager::Secret` (`makita-db-master-secret`) to store the PostgreSQL master password securely. (Updated: Secrets Manager usage was not in the original spec but is present in the implementation.)

### Requirement 4: MCP Server Implementation

**User Story:** As a DevOps engineer, I want an MCP server built with the Strands SDK, so that failover operations can be exposed as tool calls for the DevOps Agent.

#### Acceptance Criteria

1. THE MCP_Server SHALL be implemented using the Strands SDK.
2. THE MCP_Server SHALL expose failover operations as MCP tool definitions callable by DevOps_Agent.
3. WHEN DevOps_Agent invokes a failover tool, THE MCP_Server SHALL execute the corresponding failover operation on the PostgreSQL_Cluster.
4. THE MCP_Server SHALL return the result of each tool invocation to DevOps_Agent, including success status and any error details.
5. IF the MCP_Server encounters an error during a tool invocation, THEN THE MCP_Server SHALL return a structured error response to DevOps_Agent describing the failure.

### Requirement 5: MCP Server Hosting in AgentCore

**User Story:** As a DevOps engineer, I want the MCP server hosted in Amazon AgentCore, so that it is managed, scalable, and integrated with the DevOps Agent ecosystem.

#### Acceptance Criteria

1. THE MCP_Server SHALL be deployed to and hosted in AgentCore as an AgentCore Runtime, accessible behind the AgentCore_Gateway (`makita-mcp-gateway`). (Updated: each MCP server is a separate AgentCore Runtime behind the gateway, deployed via `deploy_agentcore.py`.)
2. THE deployment scripts SHALL create the AgentCore resources required to host the MCP_Server, including Runtime, Runtime Endpoint, Gateway, and Gateway Targets. (Updated: originally specified CloudFormation; implementation uses `deploy_agentcore.py` Python script.)
3. WHEN the MCP_Server is deployed to AgentCore, THE deployment scripts SHALL configure DevOps_Agent to connect to the MCP_Server through the AgentCore_Gateway.
4. WHILE the MCP_Server is running in AgentCore, THE MCP_Server SHALL be accessible to DevOps_Agent for tool invocations through the AgentCore_Gateway.

### Requirement 6: PostgreSQL Cluster Failover Execution

**User Story:** As a DevOps engineer, I want the MCP server to execute automated failover of the PostgreSQL cluster, so that disaster recovery can be performed quickly and reliably through the DevOps Agent.

#### Acceptance Criteria

1. WHEN DevOps_Agent triggers a failover, THE MCP_Server SHALL promote the replica instance in the DR_Region to become the new primary instance.
2. WHEN a failover is completed, THE MCP_Server SHALL update the PostgreSQL_Cluster endpoint values in Parameter_Store to reflect the new primary instance.
3. WHEN a failover is initiated, THE MCP_Server SHALL verify the replication status of the replica instance before promoting the replica.
4. IF the replica instance is not in a healthy replication state, THEN THE MCP_Server SHALL report the replication status to DevOps_Agent and halt the failover operation.
5. WHEN a failover is completed, THE MCP_Server SHALL return a summary to DevOps_Agent containing the new primary endpoint, the previous primary endpoint, and the failover duration.

### Requirement 7: Resource Naming Convention

**User Story:** As a DevOps engineer, I want all AWS resources to follow a consistent naming convention with the "makita-" prefix, so that resources are easily identifiable and isolated from other workloads.

#### Acceptance Criteria

1. THE CloudFormation_Templates SHALL prefix all AWS resource names with "makita-".
2. THE CloudFormation_Templates SHALL prefix all AWS resource tags with "makita-" for the project tag key.
3. WHEN a Parameter_Store parameter is created, THE CloudFormation_Templates SHALL use the path prefix "/makita/" for the parameter name.

### Requirement 8: DevOps Agent Integration

**User Story:** As a DevOps engineer, I want the DevOps Agent to drive the MCP server for disaster recovery operations, so that failover can be initiated and monitored through natural language interactions.

#### Acceptance Criteria

1. THE DevOps_Agent SHALL connect to the MCP_Server hosted in AgentCore.
2. WHEN a user requests a disaster recovery operation through DevOps_Agent, THE DevOps_Agent SHALL invoke the appropriate MCP tool on the MCP_Server.
3. WHEN the MCP_Server returns a tool result, THE DevOps_Agent SHALL present the result to the user.
4. THE MCP_Server SHALL expose a health-check tool that DevOps_Agent can invoke to verify the status of the PostgreSQL_Cluster.

### Requirement 9: AgentCore Policies and Identities for MCP Server Governance

**User Story:** As a DevOps engineer, I want AgentCore policies and identities to govern the MCP server's failover actions, so that the MCP server is restricted to operating only on authorized resources, regions, and principals.

#### Acceptance Criteria

1. THE Cedar_Policies SHALL restrict the MCP_Server to performing failover operations only on PostgreSQL_Cluster instances whose names begin with "makita-". (Updated: governance is enforced via Cedar policies in `policies/agentcore/` attached to AgentCore Gateway targets, not via CloudFormation-defined AgentCore_Policies.)
2. THE Cedar_Policies SHALL restrict the MCP_Server to performing failover operations only from the Primary_Region (us-east-1) to the DR_Region (us-west-2).
3. THE Cedar_Policies SHALL restrict the IAM role used by the MCP_Server during failover to a principal whose name begins with "makita-".
4. THE deployment scripts SHALL create AgentCore Workload Identities that assign the authorized IAM role to the MCP_Server within AgentCore. (Updated: uses `create_workload_identity` via `deploy_agentcore.py`.)
5. IF the MCP_Server attempts a failover operation on a resource that does not begin with "makita-", THEN THE Cedar_Policies SHALL deny the operation.
6. IF the MCP_Server attempts a failover operation targeting a region other than the DR_Region (us-west-2), THEN THE Cedar_Policies SHALL deny the operation.
7. IF the MCP_Server attempts a failover operation using a principal that does not begin with "makita-", THEN THE Cedar_Policies SHALL deny the operation.

### Requirement 10: Bedrock Guardrails for MCP Server Governance

**User Story:** As a DevOps engineer, I want Bedrock Guardrails applied to the MCP server, so that AI-assisted disaster recovery operations are governed by safety and compliance controls.

#### Acceptance Criteria

1. THE CloudFormation_Templates and Guardrail_Configs SHALL define Bedrock_Guardrails that govern the actions of the MCP_Server. Guardrails for the three workload servers are defined in the CloudFormation stack; guardrails for all five servers (including stub servers) are also defined as standalone JSON files in `policies/guardrails/` and deployed via `deploy_agentcore.py`. (Updated: guardrail configs are externalized to JSON files in addition to CloudFormation definitions; stub servers also have guardrails.)
2. WHEN DevOps_Agent invokes a tool on the MCP_Server, THE Bedrock_Guardrails SHALL evaluate the request before the MCP_Server executes the operation.
3. IF a tool invocation violates a Bedrock_Guardrails policy, THEN THE MCP_Server SHALL deny the operation and return a structured error response to DevOps_Agent describing the policy violation.
4. THE Bedrock_Guardrails SHALL be configured to restrict MCP_Server operations to disaster recovery actions on the PostgreSQL_Cluster.
5. WHEN DevOps_Agent sends a prompt to the MCP_Server, THE Bedrock_Guardrails SHALL inspect the prompt content for malicious attempts before the MCP_Server processes the request.
6. WHEN DevOps_Agent sends a prompt to the MCP_Server, THE Bedrock_Guardrails SHALL detect and block prompt injection attacks contained within the prompt content.

### Requirement 11: AWS Support Stub Server

**User Story:** As a DevOps engineer, I want a stub MCP server that simulates the AWS Support API, so that DevOps Agent can create and update AWS Support cases during disaster recovery without depending on the real AWS Support service.

#### Acceptance Criteria

1. THE AWS_Support_Stub_Server SHALL be implemented as an MCP server that simulates the AWS Support API.
2. THE AWS_Support_Stub_Server SHALL expose a tool that allows DevOps_Agent to create a new AWS_Support_Case.
3. THE AWS_Support_Stub_Server SHALL expose a tool that allows DevOps_Agent to update an existing AWS_Support_Case with new status information.
4. WHEN DevOps_Agent creates an AWS_Support_Case, THE AWS_Support_Stub_Server SHALL return a unique case identifier for the created case.
5. WHEN DevOps_Agent updates an AWS_Support_Case, THE AWS_Support_Stub_Server SHALL return a confirmation containing the case identifier and the updated status.
6. IF DevOps_Agent attempts to update an AWS_Support_Case that does not exist, THEN THE AWS_Support_Stub_Server SHALL return a structured error response indicating the case was not found.
7. THE DevOps_Agent SHALL connect to the AWS_Support_Stub_Server as an MCP server.

### Requirement 12: ServiceNow Stub Server

**User Story:** As a DevOps engineer, I want a stub MCP server that simulates the ServiceNow API, so that DevOps Agent can create and update ServiceNow tickets during disaster recovery without depending on the real ServiceNow service.

#### Acceptance Criteria

1. THE ServiceNow_Stub_Server SHALL be implemented as an MCP server that simulates the ServiceNow API.
2. THE ServiceNow_Stub_Server SHALL expose a tool that allows DevOps_Agent to create a new ServiceNow_Ticket.
3. THE ServiceNow_Stub_Server SHALL expose a tool that allows DevOps_Agent to update an existing ServiceNow_Ticket with new status information.
4. WHEN DevOps_Agent creates a ServiceNow_Ticket, THE ServiceNow_Stub_Server SHALL return a unique ticket identifier for the created ticket.
5. WHEN DevOps_Agent updates a ServiceNow_Ticket, THE ServiceNow_Stub_Server SHALL return a confirmation containing the ticket identifier and the updated status.
6. IF DevOps_Agent attempts to update a ServiceNow_Ticket that does not exist, THEN THE ServiceNow_Stub_Server SHALL return a structured error response indicating the ticket was not found.
7. THE DevOps_Agent SHALL connect to the ServiceNow_Stub_Server as an MCP server.

### Requirement 13: Ticketing Integration During Failover

**User Story:** As a DevOps engineer, I want DevOps Agent to create and update both an AWS Support case and a ServiceNow ticket throughout the failover process, so that disaster recovery operations are tracked in both ticketing systems.

#### Acceptance Criteria

1. WHEN DevOps_Agent initiates a failover, THE DevOps_Agent SHALL create an AWS_Support_Case via the AWS_Support_Stub_Server before beginning failover operations.
2. WHEN DevOps_Agent initiates a failover, THE DevOps_Agent SHALL create a ServiceNow_Ticket via the ServiceNow_Stub_Server before beginning failover operations.
3. WHEN the MCP_Server initiates the failover operation, THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the status "failover initiated".
4. WHEN the MCP_Server verifies the replication status, THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the status "replication verified".
5. WHEN the MCP_Server begins promoting the replica instance, THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the status "promotion started".
6. WHEN the MCP_Server completes promoting the replica instance, THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the status "promotion completed".
7. WHEN the MCP_Server updates the PostgreSQL_Cluster endpoints in Parameter_Store, THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the status "endpoints updated".
8. WHEN the failover operation is fully complete, THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the status "failover complete".
9. IF any Pre_Check fails, THEN THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the Pre_Check failure details, including which specific Pre_Check failed and the reason for the failure.
10. IF the failover execution fails, THEN THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the failover failure details, including the error returned by the MCP_Server.
11. IF any Post_Check fails, THEN THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the Post_Check failure details, including which specific Post_Check failed and the reason for the failure.
12. IF the Failover_Sequence is restarted or retried, THEN THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket indicating a restart of the Failover_Sequence, including the reason for the restart.
13. IF a corrective action is taken during the Failover_Sequence, THEN THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket with the corrective action details, including a description of the action taken and the phase in which the correction occurred.
14. THE DevOps_Agent SHALL update the AWS_Support_Case and the ServiceNow_Ticket for every state change in the Failover_Sequence, including error states, restart states, and corrective action states.
15. WHEN DevOps_Agent updates the AWS_Support_Case or the ServiceNow_Ticket, THE DevOps_Agent SHALL include all relevant AWS resource names in the update, including PostgreSQL_Cluster instance names, Parameter_Store parameter paths, and AgentCore resource names.
16. WHEN DevOps_Agent updates the AWS_Support_Case or the ServiceNow_Ticket, THE DevOps_Agent SHALL include the Primary_Region (us-east-1) and the DR_Region (us-west-2) in the update.
17. WHEN DevOps_Agent updates the AWS_Support_Case or the ServiceNow_Ticket, THE DevOps_Agent SHALL include contextual information in the update, including the current phase of the Failover_Sequence, the MCP server involved, endpoint addresses, replication status details, IAM role names, and any error codes or messages.

### Requirement 14: Event Logging to Markdown Files

**User Story:** As a DevOps engineer, I want each AWS Support case and ServiceNow ticket to have a corresponding markdown file that logs all events with timestamps, so that there is a persistent, human-readable record of the disaster recovery process.

#### Acceptance Criteria

1. WHEN an AWS_Support_Case is created, THE DevOps_Agent SHALL create an Event_Log_File in markdown format for that AWS_Support_Case.
2. WHEN a ServiceNow_Ticket is created, THE DevOps_Agent SHALL create an Event_Log_File in markdown format for that ServiceNow_Ticket.
3. WHEN the AWS_Support_Case is updated with a new status, THE DevOps_Agent SHALL append an entry to the corresponding Event_Log_File containing a timestamp and a description of the event.
4. WHEN the ServiceNow_Ticket is updated with a new status, THE DevOps_Agent SHALL append an entry to the corresponding Event_Log_File containing a timestamp and a description of the event.
5. THE Event_Log_File SHALL include the case or ticket identifier in the file name.
6. THE Event_Log_File SHALL format each event entry with an ISO 8601 timestamp followed by the event description.

### Requirement 15: DevOps Agent Chat Step Listing

**User Story:** As a DevOps engineer, I want each step of the disaster recovery process to be displayed in the DevOps Agent chat as it happens, so that I can monitor the real-time progression of the failover operation.

#### Acceptance Criteria

1. WHEN DevOps_Agent creates an AWS_Support_Case, THE DevOps_Agent SHALL display a message in the chat indicating the AWS Support case is being created.
2. WHEN DevOps_Agent creates a ServiceNow_Ticket, THE DevOps_Agent SHALL display a message in the chat indicating the ServiceNow ticket is being created.
3. WHEN the MCP_Server verifies the replication status, THE DevOps_Agent SHALL display a message in the chat indicating the replication status is being verified.
4. WHEN the MCP_Server promotes the replica instance, THE DevOps_Agent SHALL display a message in the chat indicating the replica is being promoted.
5. WHEN the MCP_Server updates the PostgreSQL_Cluster endpoints, THE DevOps_Agent SHALL display a message in the chat indicating the endpoints are being updated.
6. WHEN DevOps_Agent updates the AWS_Support_Case and ServiceNow_Ticket, THE DevOps_Agent SHALL display a message in the chat indicating the tickets are being updated.
7. WHEN the failover operation is fully complete, THE DevOps_Agent SHALL display a message in the chat indicating the failover is complete.
8. THE DevOps_Agent SHALL display each step message before or at the time the corresponding operation begins.

### Requirement 16: CloudWatch Dashboard for Failover Visualization

**User Story:** As a DevOps engineer, I want a CloudWatch dashboard that visualizes the database failover from one region to another, so that I can monitor and observe the PostgreSQL cluster failover process across us-east-1 and us-west-2.

#### Acceptance Criteria

1. THE CloudFormation_Templates SHALL provision a CloudWatch_Dashboard that visualizes the PostgreSQL_Cluster failover process across the Primary_Region (us-east-1) and the DR_Region (us-west-2). (Updated: the `makita-failover-dashboard` was removed from the CloudFormation stack during implementation. This requirement is not currently provisioned.)
2. WHEN the CloudWatch_Dashboard is provisioned, THE CloudFormation_Templates SHALL prefix the dashboard name with "makita-". (Updated: dashboard not currently provisioned.)
3. THE CloudWatch_Dashboard SHALL display metrics from both the Primary_Region (us-east-1) and the DR_Region (us-west-2) for the PostgreSQL_Cluster. (Updated: dashboard not currently provisioned.)
4. WHEN a failover is initiated, THE CloudWatch_Dashboard SHALL reflect the change in primary and replica roles of the PostgreSQL_Cluster instances. (Updated: dashboard not currently provisioned.)
5. THE CloudWatch_Dashboard SHALL display the replication status between the Primary_Region and the DR_Region for the PostgreSQL_Cluster. (Updated: dashboard not currently provisioned.)
6. THE CloudWatch_Dashboard SHALL display the health and availability status of the PostgreSQL_Cluster instances in both the Primary_Region and the DR_Region. (Updated: dashboard not currently provisioned.)

### Requirement 17: Failover Sequence Orchestration

**User Story:** As a DevOps engineer, I want the failover process to follow a strict ordered sequence of pre-checks, failover execution, and post-checks, so that failover is only performed when the database is in a safe state and any post-failover issues are detected and reported.

#### Acceptance Criteria

1. WHEN a user requests a failover through DevOps_Agent chat, THE DevOps_Agent SHALL initiate the Failover_Sequence.
2. WHEN the Failover_Sequence is initiated, THE DevOps_Agent SHALL invoke the Pre_Check_MCP_Server to execute Pre_Checks on the PostgreSQL_Cluster before invoking the MCP_Server to perform the Failover.
3. WHEN Pre_Checks are executed, THE DevOps_Agent SHALL invoke the Pre_Check_MCP_Server to verify the replication health between the primary instance and the replica instance.
4. WHEN Pre_Checks are executed, THE DevOps_Agent SHALL invoke the Pre_Check_MCP_Server to verify the primary instance in the Primary_Region is in a known status.
5. WHEN Pre_Checks are executed, THE DevOps_Agent SHALL invoke the Pre_Check_MCP_Server to verify the replica instance in the DR_Region is ready for promotion.
6. IF any Pre_Checks verification fails, THEN THE DevOps_Agent SHALL report the failure details to the user and halt the Failover_Sequence without invoking the MCP_Server.
7. WHEN all Pre_Checks pass, THE DevOps_Agent SHALL invoke the MCP_Server to execute the Failover on the PostgreSQL_Cluster.
8. WHEN the MCP_Server completes the Failover, THE DevOps_Agent SHALL invoke the Post_Check_MCP_Server to execute Post_Checks on the PostgreSQL_Cluster.
9. WHEN Post_Checks are executed, THE DevOps_Agent SHALL invoke the Post_Check_MCP_Server to verify the new primary instance in the DR_Region is healthy.
10. WHEN Post_Checks are executed, THE DevOps_Agent SHALL invoke the Post_Check_MCP_Server to verify the PostgreSQL_Cluster endpoint values in Parameter_Store reflect the new primary instance.
11. WHEN Post_Checks are executed, THE DevOps_Agent SHALL invoke the Post_Check_MCP_Server to verify that replication from the new primary instance is established.
12. IF any Post_Checks verification fails, THEN THE DevOps_Agent SHALL report the Post_Checks failure details to the user, including which specific verifications failed.
13. THE DevOps_Agent SHALL enforce the Failover_Sequence phase order: Pre_Checks before Failover, and Failover before Post_Checks.
14. THE DevOps_Agent SHALL not invoke the MCP_Server to execute the Failover until all Pre_Checks from the Pre_Check_MCP_Server have passed.
15. THE DevOps_Agent SHALL not invoke the Post_Check_MCP_Server to execute Post_Checks until the MCP_Server confirms the Failover is complete.

### Requirement 18: Pre-Check MCP Server

**User Story:** As a DevOps engineer, I want a separate MCP server dedicated to database pre-checks, so that pre-check operations are isolated from failover execution and can be independently governed and scaled.

#### Acceptance Criteria

1. THE Pre_Check_MCP_Server SHALL be implemented using the Strands SDK.
2. THE Pre_Check_MCP_Server SHALL be deployed to and hosted in AgentCore.
3. THE Pre_Check_MCP_Server SHALL expose a tool that allows DevOps_Agent to verify the replication health between the primary instance and the replica instance of the PostgreSQL_Cluster.
4. THE Pre_Check_MCP_Server SHALL expose a tool that allows DevOps_Agent to verify the primary instance status in the Primary_Region.
5. THE Pre_Check_MCP_Server SHALL expose a tool that allows DevOps_Agent to verify the replica instance readiness for promotion in the DR_Region.
6. WHEN DevOps_Agent invokes a pre-check tool, THE Pre_Check_MCP_Server SHALL execute the corresponding verification on the PostgreSQL_Cluster and return the result to DevOps_Agent.
7. THE Pre_Check_MCP_Server SHALL return the result of each tool invocation to DevOps_Agent, including verification status and any error details.
8. IF the Pre_Check_MCP_Server encounters an error during a tool invocation, THEN THE Pre_Check_MCP_Server SHALL return a structured error response to DevOps_Agent describing the failure.
9. THE DevOps_Agent SHALL connect to the Pre_Check_MCP_Server during the Pre_Checks phase of the Failover_Sequence.
10. THE deployment scripts SHALL create the AgentCore Runtime and Gateway Target required to host the Pre_Check_MCP_Server (`makita_postgresql_precheck_mcp`). (Updated: originally specified CloudFormation; implementation uses `deploy_agentcore.py`.)

### Requirement 19: Post-Check MCP Server

**User Story:** As a DevOps engineer, I want a separate MCP server dedicated to database post-checks, so that post-check operations are isolated from failover execution and can be independently governed and scaled.

#### Acceptance Criteria

1. THE Post_Check_MCP_Server SHALL be implemented using the Strands SDK.
2. THE Post_Check_MCP_Server SHALL be deployed to and hosted in AgentCore.
3. THE Post_Check_MCP_Server SHALL expose a tool that allows DevOps_Agent to verify the health of the new primary instance in the DR_Region.
4. THE Post_Check_MCP_Server SHALL expose a tool that allows DevOps_Agent to verify the PostgreSQL_Cluster endpoint values in Parameter_Store reflect the new primary instance.
5. THE Post_Check_MCP_Server SHALL expose a tool that allows DevOps_Agent to verify that replication from the new primary instance is established.
6. WHEN DevOps_Agent invokes a post-check tool, THE Post_Check_MCP_Server SHALL execute the corresponding verification on the PostgreSQL_Cluster and return the result to DevOps_Agent.
7. THE Post_Check_MCP_Server SHALL return the result of each tool invocation to DevOps_Agent, including verification status and any error details.
8. IF the Post_Check_MCP_Server encounters an error during a tool invocation, THEN THE Post_Check_MCP_Server SHALL return a structured error response to DevOps_Agent describing the failure.
9. THE DevOps_Agent SHALL connect to the Post_Check_MCP_Server during the Post_Checks phase of the Failover_Sequence.
10. THE deployment scripts SHALL create the AgentCore Runtime and Gateway Target required to host the Post_Check_MCP_Server (`makita_postgresql_postcheck_mcp`). (Updated: originally specified CloudFormation; implementation uses `deploy_agentcore.py`.)

### Requirement 20: AgentCore Policies and Identities for Pre-Check and Post-Check MCP Servers

**User Story:** As a DevOps engineer, I want AgentCore policies and identities to govern the Pre-Check and Post-Check MCP servers, so that both servers are restricted to operating only on authorized resources, regions, and principals.

#### Acceptance Criteria

1. THE Cedar_Policies SHALL restrict the Pre_Check_MCP_Server to performing pre-check operations only on PostgreSQL_Cluster instances whose names begin with "makita-". (Updated: governance is enforced via Cedar policies in `policies/agentcore/postgresql-precheck.cedar` attached to the gateway target.)
2. THE Cedar_Policies SHALL restrict the Post_Check_MCP_Server to performing post-check operations only on PostgreSQL_Cluster instances whose names begin with "makita-". (Updated: governance is enforced via Cedar policies in `policies/agentcore/postgresql-postcheck.cedar`.)
3. THE Cedar_Policies SHALL restrict the Pre_Check_MCP_Server to performing pre-check operations only from the Primary_Region (us-east-1) to the DR_Region (us-west-2).
4. THE Cedar_Policies SHALL restrict the Post_Check_MCP_Server to performing post-check operations only from the Primary_Region (us-east-1) to the DR_Region (us-west-2).
5. THE Cedar_Policies SHALL restrict the IAM role used by the Pre_Check_MCP_Server to a principal whose name begins with "makita-".
6. THE Cedar_Policies SHALL restrict the IAM role used by the Post_Check_MCP_Server to a principal whose name begins with "makita-".
7. THE deployment scripts SHALL create AgentCore Workload Identities that assign the authorized IAM role to the Pre_Check_MCP_Server within AgentCore. (Updated: uses `create_workload_identity` via `deploy_agentcore.py`.)
8. THE deployment scripts SHALL create AgentCore Workload Identities that assign the authorized IAM role to the Post_Check_MCP_Server within AgentCore. (Updated: uses `create_workload_identity` via `deploy_agentcore.py`.)
9. IF the Pre_Check_MCP_Server attempts an operation on a resource that does not begin with "makita-", THEN THE Cedar_Policies SHALL deny the operation.
10. IF the Post_Check_MCP_Server attempts an operation on a resource that does not begin with "makita-", THEN THE Cedar_Policies SHALL deny the operation.
11. IF the Pre_Check_MCP_Server attempts an operation targeting a region other than the Primary_Region (us-east-1) or the DR_Region (us-west-2), THEN THE Cedar_Policies SHALL deny the operation.
12. IF the Post_Check_MCP_Server attempts an operation targeting a region other than the Primary_Region (us-east-1) or the DR_Region (us-west-2), THEN THE Cedar_Policies SHALL deny the operation.
13. IF the Pre_Check_MCP_Server attempts an operation using a principal that does not begin with "makita-", THEN THE Cedar_Policies SHALL deny the operation.
14. IF the Post_Check_MCP_Server attempts an operation using a principal that does not begin with "makita-", THEN THE Cedar_Policies SHALL deny the operation.

### Requirement 21: Bedrock Guardrails for Pre-Check and Post-Check MCP Servers

**User Story:** As a DevOps engineer, I want Bedrock Guardrails applied to the Pre-Check and Post-Check MCP servers, so that AI-assisted pre-check and post-check operations are governed by safety and compliance controls.

#### Acceptance Criteria

1. THE CloudFormation_Templates and Guardrail_Configs SHALL define Bedrock_Guardrails that govern the actions of the Pre_Check_MCP_Server. (Updated: guardrails are also defined as standalone JSON in `policies/guardrails/postgresql-precheck-guardrail.json`.)
2. THE CloudFormation_Templates and Guardrail_Configs SHALL define Bedrock_Guardrails that govern the actions of the Post_Check_MCP_Server. (Updated: guardrails are also defined as standalone JSON in `policies/guardrails/postgresql-postcheck-guardrail.json`.)
3. WHEN DevOps_Agent invokes a tool on the Pre_Check_MCP_Server, THE Bedrock_Guardrails SHALL evaluate the request before the Pre_Check_MCP_Server executes the operation.
4. WHEN DevOps_Agent invokes a tool on the Post_Check_MCP_Server, THE Bedrock_Guardrails SHALL evaluate the request before the Post_Check_MCP_Server executes the operation.
5. IF a tool invocation on the Pre_Check_MCP_Server violates a Bedrock_Guardrails policy, THEN THE Pre_Check_MCP_Server SHALL deny the operation and return a structured error response to DevOps_Agent describing the policy violation.
6. IF a tool invocation on the Post_Check_MCP_Server violates a Bedrock_Guardrails policy, THEN THE Post_Check_MCP_Server SHALL deny the operation and return a structured error response to DevOps_Agent describing the policy violation.
7. THE Bedrock_Guardrails SHALL be configured to restrict Pre_Check_MCP_Server operations to disaster recovery pre-check actions on the PostgreSQL_Cluster.
8. THE Bedrock_Guardrails SHALL be configured to restrict Post_Check_MCP_Server operations to disaster recovery post-check actions on the PostgreSQL_Cluster.
9. WHEN DevOps_Agent sends a prompt to the Pre_Check_MCP_Server, THE Bedrock_Guardrails SHALL inspect the prompt content for malicious attempts before the Pre_Check_MCP_Server processes the request.
10. WHEN DevOps_Agent sends a prompt to the Post_Check_MCP_Server, THE Bedrock_Guardrails SHALL inspect the prompt content for malicious attempts before the Post_Check_MCP_Server processes the request.
11. WHEN DevOps_Agent sends a prompt to the Pre_Check_MCP_Server, THE Bedrock_Guardrails SHALL detect and block prompt injection attacks contained within the prompt content.
12. WHEN DevOps_Agent sends a prompt to the Post_Check_MCP_Server, THE Bedrock_Guardrails SHALL detect and block prompt injection attacks contained within the prompt content.

### Requirement 22: Project README Documentation

**User Story:** As a DevOps engineer, I want a README.md file that describes the entire MAKITA project, so that new team members and stakeholders can understand the system architecture, set up the environment, and operate the disaster recovery workflow.

#### Acceptance Criteria

1. THE README_File SHALL begin with a summary of the MAKITA project, including the project purpose, the technologies used, and the disaster recovery scenario addressed.
2. THE README_File SHALL include an architectural diagram using Mermaid or ASCII art that shows the overall system architecture, including DevOps_Agent, AgentCore Gateway, the MCP_Server, the Pre_Check_MCP_Server, the Post_Check_MCP_Server, the AWS_Support_Stub_Server, the ServiceNow_Stub_Server, the PostgreSQL_Cluster across the Primary_Region and the DR_Region, Parameter_Store, Bedrock_Guardrails, and Cedar_Policies. (Updated: removed CloudWatch_Dashboard, AgentCore_Policies, AgentCore_Identities; added AgentCore Gateway and Cedar_Policies.)
3. THE README_File SHALL include a Getting Started guide that lists prerequisites, setup instructions, and deployment steps required to run the MAKITA project.
4. THE README_File SHALL include instructions for deploying the CloudFormation stacks and running the deployment scripts. (Updated: originally referenced a single CloudFormation stack; implementation uses two stacks plus Python deployment scripts.)
5. THE README_File SHALL include instructions for configuring the MCP_Server, the Pre_Check_MCP_Server, and the Post_Check_MCP_Server.
6. THE README_File SHALL include instructions for initiating a failover through DevOps_Agent.
7. THE README_File SHALL include instructions for monitoring the failover process via the CloudWatch_Dashboard.
8. THE README_File SHALL include instructions for reviewing the Event_Log_File entries and the AWS_Support_Case and ServiceNow_Ticket records generated during a failover.

### Requirement 23: Comprehensive Testing Scripts

**User Story:** As a DevOps engineer, I want comprehensive testing scripts for each functionality in the MAKITA project, so that every component can be validated independently and regressions are caught before deployment.

#### Acceptance Criteria

1. THE Test_Scripts SHALL include tests that validate the CloudFormation stack deployment and verify all provisioned resources are created with the "makita-" prefix in the correct regions (Primary_Region us-east-1 and DR_Region us-west-2).
2. THE Test_Scripts SHALL include tests that validate all Parameter_Store parameters are created with the "/makita/" prefix and contain the expected configuration values.
3. THE Test_Scripts SHALL include tests that validate the PostgreSQL_Cluster provisioning, including verification that the primary instance is running in the Primary_Region (us-east-1), the replica instance is running in the DR_Region (us-west-2), and replication health between the primary and replica is confirmed.
4. THE Test_Scripts SHALL include tests that validate the MCP_Server failover functionality, including tool invocations for failover execution, failover completion verification, and error handling for failed failover operations.
5. THE Test_Scripts SHALL include tests that validate the Pre_Check_MCP_Server functionality, including replication health check tool invocation, primary instance status check tool invocation, and replica readiness check tool invocation.
6. THE Test_Scripts SHALL include tests that validate the Post_Check_MCP_Server functionality, including new primary health verification tool invocation, endpoint verification in Parameter_Store tool invocation, and replication from the new primary verification tool invocation.
7. THE Test_Scripts SHALL include tests that validate the AWS_Support_Stub_Server functionality, including creating a new AWS_Support_Case, updating an existing AWS_Support_Case, and error handling when attempting to update a non-existent AWS_Support_Case.
8. THE Test_Scripts SHALL include tests that validate the ServiceNow_Stub_Server functionality, including creating a new ServiceNow_Ticket, updating an existing ServiceNow_Ticket, and error handling when attempting to update a non-existent ServiceNow_Ticket.
9. THE Test_Scripts SHALL include tests that validate AgentCore_Policies enforcement, including verification that operations on resources without the "makita-" prefix are denied, operations targeting regions other than the Primary_Region (us-east-1) and the DR_Region (us-west-2) are denied, and operations using principals without the "makita-" prefix are denied.
10. THE Test_Scripts SHALL include tests that validate Bedrock_Guardrails enforcement, including verification that prompt injection attempts are detected and blocked, malicious prompts are blocked, and policy violations return structured error responses.
11. THE Test_Scripts SHALL include tests that validate the Failover_Sequence orchestration end-to-end, including the ordered execution of Pre_Checks followed by Failover followed by Post_Checks, and verification that failure scenarios at each phase halt or report correctly.
12. THE Test_Scripts SHALL include tests that validate ticketing integration during the Failover_Sequence, including verification that AWS_Support_Case and ServiceNow_Ticket are created and updated at each phase, and that failure, restart, and corrective action states are recorded in both ticketing systems.
13. THE Test_Scripts SHALL include tests that validate Event_Log_File creation and updates, including verification that markdown files are created for each AWS_Support_Case and ServiceNow_Ticket and that entries contain ISO 8601 timestamps and event descriptions.
14. THE Test_Scripts SHALL include tests that validate the CloudWatch_Dashboard provisioning, including verification that the dashboard is created with the "makita-" prefix and displays metrics from both the Primary_Region (us-east-1) and the DR_Region (us-west-2) for the PostgreSQL_Cluster.
15. THE Test_Scripts SHALL include tests that validate DevOps_Agent chat step listing, including verification that each step of the Failover_Sequence is displayed as a message in the DevOps_Agent chat at the time the corresponding operation begins.

### Requirement 24: Mandatory Resource Tagging

**User Story:** As a DevOps engineer, I want every AWS resource created by the CloudFormation template to include mandatory tags, so that resources are properly classified for lifecycle management and environment identification.

#### Acceptance Criteria

1. THE CloudFormation_Templates SHALL apply the tag `auto-delete` with value `no` to every AWS resource created within the CloudFormation stacks. (Updated: applies to both `makita-postgresql-stack` and `makita-postgresql-replica-stack`.)
2. THE CloudFormation_Templates SHALL apply the tag `Env` with value `prod1` to every AWS resource created within the CloudFormation stacks.
3. THE CloudFormation_Templates SHALL apply the Mandatory_Resource_Tags to all PostgreSQL_Cluster resources (primary instance and replica instance).
4. THE CloudFormation_Templates SHALL apply the Mandatory_Resource_Tags to all IAM roles defined within the CloudFormation stacks.
5. THE CloudFormation_Templates SHALL apply the Mandatory_Resource_Tags to all Parameter_Store parameters defined within the CloudFormation stacks.
6. THE deployment scripts SHALL apply the Mandatory_Resource_Tags to all AgentCore resources (Runtimes, Gateway, Gateway Targets) created via `deploy_agentcore.py`. (Updated: AgentCore resources are deployed via Python script, not CloudFormation.)
7. THE CloudFormation_Templates SHALL apply the Mandatory_Resource_Tags to all Bedrock_Guardrails defined within the CloudFormation stacks.
8. THE CloudWatch_Dashboard is not currently provisioned. (Updated: the `makita-failover-dashboard` was removed from the CloudFormation stack.)
9. THE deployment scripts SHALL apply the Mandatory_Resource_Tags to all AgentCore Runtime resources for the MCP servers (Failover, Pre-Check, Post-Check, AWS Support Stub, ServiceNow Stub) created via `deploy_agentcore.py`. (Updated: MCP server registrations are deployed via Python script, not CloudFormation.)
10. IF an AWS resource does not support tagging, THEN THE CloudFormation_Templates SHALL document the resource type as a tagging exception in a comment within the template.

### Requirement 25: AgentCore Policy Enforcement Based on Env Tag

**User Story:** As a DevOps engineer, I want AgentCore policies to enforce that MCP servers only operate on AWS resources tagged with `Env=prod1`, so that MCP servers are prevented from affecting resources outside the designated production environment.

#### Acceptance Criteria

1. THE Cedar_Policies SHALL restrict the MCP_Server (Failover) to performing operations only on AWS resources that have the tag `Env` with value `prod1`. (Updated: enforcement is via Cedar policies attached to AgentCore Gateway targets.)
2. THE Cedar_Policies SHALL restrict the Pre_Check_MCP_Server to performing operations only on AWS resources that have the tag `Env` with value `prod1`.
3. THE Cedar_Policies SHALL restrict the Post_Check_MCP_Server to performing operations only on AWS resources that have the tag `Env` with value `prod1`.
4. IF the MCP_Server attempts to operate on an AWS resource that does not have the tag `Env` with value `prod1`, THEN THE Cedar_Policies SHALL deny the operation.
5. IF the Pre_Check_MCP_Server attempts to operate on an AWS resource that does not have the tag `Env` with value `prod1`, THEN THE Cedar_Policies SHALL deny the operation.
6. IF the Post_Check_MCP_Server attempts to operate on an AWS resource that does not have the tag `Env` with value `prod1`, THEN THE Cedar_Policies SHALL deny the operation.

### Requirement 26: Architectural Diagram

**User Story:** As a DevOps engineer, I want a standalone architectural diagram of the MAKITA system, so that the system architecture, component relationships, and data flows are clearly documented and easy to review independently of the README.

#### Acceptance Criteria

1. THE Architectural_Diagram SHALL be created as a standalone artifact separate from the README_File.
2. THE Architectural_Diagram SHALL be authored using Mermaid syntax for easy rendering and version control.
3. THE Architectural_Diagram SHALL include the PostgreSQL_Cluster primary instance in the Primary_Region (us-east-1) and the PostgreSQL_Cluster replica instance in the DR_Region (us-west-2), with the replication relationship between the primary and replica shown.
4. THE Architectural_Diagram SHALL include the AgentCore_Gateway (`makita-mcp-gateway`) component. (Updated: CloudWatch_Dashboard was removed; AgentCore Gateway was added.)
5. THE Architectural_Diagram SHALL include the MCP_Server (Failover), the Pre_Check_MCP_Server, and the Post_Check_MCP_Server as AgentCore Runtimes.
6. THE Architectural_Diagram SHALL include the AgentCore governance components: Cedar_Policies and Bedrock_Guardrails. (Updated: replaced AgentCore_Policies and AgentCore_Identities with Cedar_Policies.)
7. THE Architectural_Diagram SHALL include the AWS_Support_Stub_Server.
8. THE Architectural_Diagram SHALL include the ServiceNow_Stub_Server.
9. THE Architectural_Diagram SHALL include DevOps_Agent and show the connections from DevOps_Agent through the AgentCore_Gateway to the MCP_Server (Failover), the Pre_Check_MCP_Server, the Post_Check_MCP_Server, the AWS_Support_Stub_Server, and the ServiceNow_Stub_Server. (Updated: connections go through the gateway, not directly to MCP servers.)
10. THE Architectural_Diagram SHALL include Parameter_Store.
11. THE Architectural_Diagram SHALL show the relationships and data flows between all included components.

### Requirement 27: AgentCore Runtime for MCP Server Hosting

**User Story:** As a DevOps engineer, I want the MCP servers hosted in AgentCore Runtime, so that they are managed, scalable, and accessible via AgentCore Runtime endpoints.

#### Acceptance Criteria

1. THE `deploy_agentcore.py` script SHALL create 5 separate AgentCore Runtimes (one per MCP server) with underscored names: `makita_postgresql_failover_mcp`, `makita_postgresql_precheck_mcp`, `makita_postgresql_postcheck_mcp`, `makita_aws_support_stub`, `makita_servicenow_stub`. (Updated: originally specified a single `makita-mcp-runtime` in a CFN stack; implementation uses 5 separate runtimes with underscored names deployed via Python script.)
2. EACH AgentCore Runtime SHALL use the `codeConfiguration` artifact type with Python 3.11 runtime and the MCP server code packaged as an S3 code artifact.
3. EACH AgentCore Runtime SHALL use the `makita-failover-role` IAM role for execution permissions.
4. EACH AgentCore Runtime SHALL use PUBLIC network mode for accessibility.
5. EACH AgentCore Runtime SHALL use the MCP server protocol (`serverProtocol: MCP`).
6. THE `deploy_agentcore.py` script SHALL create an AgentCore Runtime Endpoint for each Runtime.
7. EACH AgentCore Runtime Endpoint SHALL reference its corresponding Runtime.

### Requirement 28: AgentCore Gateway for MCP Tool Access

**User Story:** As a DevOps engineer, I want an AgentCore Gateway that provides a unified MCP entry point for all MAKITA tools, so that DevOps Agent can discover and invoke tools through a single gateway endpoint.

#### Acceptance Criteria

1. THE `deploy_agentcore.py` script SHALL create an AgentCore Gateway named `makita-mcp-gateway` with MCP protocol type. (Updated: originally specified a CFN stack; implementation uses `deploy_agentcore.py`.)
2. THE AgentCore Gateway SHALL use IAM authorization (`authorizerType: AWS_IAM`).
3. THE AgentCore Gateway SHALL use the `makita-failover-role` IAM role for gateway service permissions.
4. THE `deploy_agentcore.py` script SHALL create Gateway Targets for each MCP server, each referencing the corresponding Runtime Endpoint.
5. EACH Gateway Target SHALL have a Cedar policy from `policies/agentcore/` attached to restrict allowed tool actions. (Updated: Cedar policies are standalone files, not defined in CloudFormation.)
6. EACH Gateway Target SHALL have a Bedrock Guardrail from `policies/guardrails/` associated for content safety. (Updated: guardrail configs are standalone JSON files.)

### Requirement 29: AgentCore Workload Identities

**User Story:** As a DevOps engineer, I want AgentCore Workload Identities assigned to each MCP server, so that each server operates with its own dedicated IAM role and permissions.

#### Acceptance Criteria

1. THE `deploy_agentcore.py` script SHALL create Workload Identities for each MCP server. (Updated: originally specified a CFN stack; implementation uses `deploy_agentcore.py`.)
2. EACH Workload Identity SHALL be mapped to its corresponding IAM role exported from the primary stack.
3. THE Workload Identities SHALL use the `bedrock-agentcore-control` API `create_workload_identity` method.

### Requirement 30: MCP Server Code Packaging

**User Story:** As a DevOps engineer, I want the MCP server code packaged and uploaded to S3, so that AgentCore Runtime can deploy and execute the servers.

#### Acceptance Criteria

1. THE `deploy_agentcore.py` script SHALL package each MCP server's code into a ZIP artifact and upload it to S3. (Updated: packaging is handled within `deploy_agentcore.py`, not a separate shell script.)
2. THE deploy script SHALL upload the ZIP artifacts to an S3 bucket (`makita-artifacts-{account_id}`) in us-east-1 before creating the AgentCore Runtimes.
3. THE S3 bucket and key SHALL be used by the Runtime code configuration for each AgentCore Runtime.
