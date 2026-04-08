# Implementation Plan: MAKITA

## Overview

MAKITA (Machine Augmented Key Infrastructure Technology Automation) implementation follows a bottom-up approach: project scaffolding, infrastructure-as-code, MCP server implementations, governance configuration, integration logic, monitoring, documentation, and testing. All MCP servers are implemented in Python using the Strands SDK. Infrastructure is defined in two CloudFormation templates under `infrastructure/workloads/postgresql/`, with AgentCore resources deployed via Python scripts (`deploy_agentcore.py`, `deploy_devops_agent.py`, `deploy_kiro_agent.py`).

## Tasks

- [x] 1. Project scaffolding and directory structure
  - [x] 1.1 Create the MAKITA project directory structure
    - Create top-level directories: `infrastructure/workloads/postgresql/`, `mcp-servers/workloads/postgresql/failover/`, `mcp-servers/workloads/postgresql/precheck/`, `mcp-servers/workloads/postgresql/postcheck/`, `mcp-servers/aws-support-stub/`, `mcp-servers/servicenow-stub/`, `event-logs/`, `tests/`, `policies/agentcore/`, `policies/guardrails/`, `scripts/`, `orchestrator/`
    - Create `requirements.txt` or `pyproject.toml` with dependencies (strands-sdk, boto3, pytest)
    - Create placeholder `__init__.py` files in each Python package directory
    - _Requirements: 1.1, 1.3, 7.1_

- [x] 2. CloudFormation templates — two stacks plus Python deployment scripts
  - [x] 2.1 Create the base CloudFormation templates with PostgreSQL cluster resources
    - Create `infrastructure/workloads/postgresql/makita-postgresql-stack.yaml` with `AWSTemplateFormatVersion` and `Description` (Updated: originally `infrastructure/makita-stack.yaml`; now under `infrastructure/workloads/postgresql/`)
    - Define `makita-pg-primary` RDS PostgreSQL instance in us-east-1
    - Create `infrastructure/workloads/postgresql/makita-postgresql-replica-stack.yaml` for the replica
    - Define `makita-pg-replica` RDS Read Replica in us-west-2 with cross-region replication from primary (Updated: replica is in a separate stack deployed to us-west-2)
    - Define `AWS::SecretsManager::Secret` (`makita-db-master-secret`) for the PostgreSQL master password (Updated: Secrets Manager was not in original spec)
    - Ensure all resource names use the `makita-` prefix
    - Apply mandatory tags (`auto-delete=no`, `Env=prod1`) to both PostgreSQL instances
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 3.3, 3.4, 3.5, 7.1, 24.1, 24.2, 24.3_

  - [x] 2.2 Add Parameter Store resources to the CloudFormation template
    - Define SSM Parameters: `/makita/db/primary-endpoint`, `/makita/db/replica-endpoint`, `/makita/db/primary-region`, `/makita/db/dr-region`, `/makita/db/cluster-name`, `/makita/db/replication-status`, `/makita/db/port`
    - Define MCP server ARN parameters: `/makita/mcp/failover-server-arn`, `/makita/mcp/precheck-server-arn`, `/makita/mcp/postcheck-server-arn`
    - All parameter names prefixed with `/makita/`
    - Apply mandatory tags (`auto-delete=no`, `Env=prod1`) to all SSM Parameter resources
    - _Requirements: 1.3, 2.1, 2.2, 3.4, 7.3, 24.1, 24.2, 24.5_

  - [x] 2.3 Add IAM roles to the CloudFormation template
    - Define `makita-failover-role` with permissions for RDS failover operations and SSM parameter updates
    - Define `makita-precheck-role` with read-only permissions for RDS describe and SSM get
    - Define `makita-postcheck-role` with read-only permissions for RDS describe and SSM get
    - All role names prefixed with `makita-`
    - Apply mandatory tags (`auto-delete=no`, `Env=prod1`) to all IAM role resources
    - _Requirements: 1.3, 7.1, 9.3, 9.4, 20.5, 20.6, 20.7, 20.8, 24.1, 24.2, 24.4_

  - [x] 2.4 Add AgentCore MCP Server registrations (Updated: moved to `deploy_agentcore.py`)
    - MCP servers are deployed as individual AgentCore Runtimes via `scripts/deploy_agentcore.py`, not in CloudFormation
    - Define 5 runtimes with underscored names: `makita_postgresql_failover_mcp`, `makita_postgresql_precheck_mcp`, `makita_postgresql_postcheck_mcp`, `makita_aws_support_stub`, `makita_servicenow_stub`
    - Configure AgentCore Gateway (`makita-mcp-gateway`) with gateway targets for each runtime
    - Apply mandatory tags (`auto-delete=no`, `Env=prod1`) to all AgentCore resources
    - _Requirements: 1.3, 5.1, 5.2, 5.3, 5.4, 18.2, 18.10, 19.2, 19.10, 24.1, 24.2, 24.9_

  - [x] 2.5 Add Cedar policies for AgentCore Gateway targets (Updated: moved from CloudFormation to standalone Cedar files)
    - Create `policies/agentcore/postgresql-failover.cedar` restricting failover operations to `makita-*` resources, us-east-1 → us-west-2 regions, and `makita-*` principals
    - Create `policies/agentcore/postgresql-precheck.cedar` restricting pre-check operations
    - Create `policies/agentcore/postgresql-postcheck.cedar` restricting post-check operations
    - Create `policies/agentcore/aws-support-stub.cedar` restricting stub server operations (Updated: stub servers also have Cedar policies)
    - Create `policies/agentcore/servicenow-stub.cedar` restricting stub server operations (Updated: stub servers also have Cedar policies)
    - Add `Env=prod1` tag-based constraint to all policies: deny operations on resources that do not carry the `Env=prod1` tag
    - Cedar policies are attached to gateway targets during deployment via `deploy_agentcore.py`
    - _Requirements: 1.3, 9.1, 9.2, 9.3, 9.5, 9.6, 9.7, 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.9, 20.10, 20.11, 20.12, 20.13, 20.14, 24.1, 24.2, 24.6, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6_

  - [x] 2.6 Add AgentCore Workload Identities (Updated: moved to `deploy_agentcore.py`)
    - Create workload identities via `create_workload_identity` API in `deploy_agentcore.py`
    - Define `makita-failover-identity` mapped to `makita-failover-role`
    - Define `makita-precheck-identity` mapped to `makita-precheck-role`
    - Define `makita-postcheck-identity` mapped to `makita-postcheck-role`
    - _Requirements: 1.3, 9.4, 20.7, 20.8, 24.1, 24.2, 24.6_

  - [x] 2.7 Add Bedrock Guardrails to the CloudFormation template and standalone JSON configs
    - Define `makita-postgresql-failover-guardrail` with content filtering, topic restriction to DR operations, and prompt injection detection (Updated: guardrail names use `makita-postgresql-*` prefix)
    - Define `makita-postgresql-precheck-guardrail` with content filtering, topic restriction to pre-check operations, and prompt injection detection
    - Define `makita-postgresql-postcheck-guardrail` with content filtering, topic restriction to post-check operations, and prompt injection detection
    - Create standalone JSON guardrail configs in `policies/guardrails/` for all 5 servers (Updated: guardrail configs externalized to JSON files; stub servers also have guardrails)
    - Configure blocked input/output messaging for policy violations
    - Apply mandatory tags (`auto-delete=no`, `Env=prod1`) to all Bedrock Guardrail resources
    - _Requirements: 1.3, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9, 21.10, 21.11, 21.12, 24.1, 24.2, 24.7_

  - [x] 2.8 CloudWatch Dashboard (Updated: removed from CloudFormation stack)
    - The `makita-failover-dashboard` was removed from the CFN stack during implementation
    - Dashboard is not currently provisioned
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6 (not currently met)_

  - [x] 2.9 Add CloudFormation Outputs and resource tagging
    - Define outputs for PrimaryEndpoint, PrimaryInstanceArn in the primary stack
    - Define outputs for ReplicaEndpoint in the replica stack
    - Add `makita-` prefixed project tags to all resources
    - Verify all taggable resources carry mandatory tags (`auto-delete=no`, `Env=prod1`); document any resource types that do not support tagging as exceptions via inline comments
    - _Requirements: 1.4, 1.5, 1.6, 7.1, 7.2, 24.1, 24.2, 24.10_

- [x] 3. Checkpoint — Validate CloudFormation template
  - Ensure the CloudFormation template is syntactically valid and all resource references are correct. Ask the user if questions arise.

- [x] 4. Failover MCP Server implementation
  - [x] 4.1 Implement the Failover MCP Server core module
    - Create `mcp-servers/workloads/postgresql/failover/server.py` using the Strands SDK
    - Implement `execute_failover` tool: verify replication status, promote replica, update Parameter Store endpoints, return `FailoverResult` with new/previous endpoints and duration
    - Implement `health_check` tool: return `HealthCheckResult` with primary/replica status and replication lag
    - Read runtime configuration from Parameter Store on startup
    - Return structured error responses on failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 6.1, 6.2, 6.3, 6.4, 6.5, 2.3, 2.4, 8.4_

  - [x] 4.2 Implement FailoverResult and HealthCheckResult data models
    - Create `mcp-servers/workloads/postgresql/failover/models.py` with `FailoverResult`, `HealthCheckResult`, and `FailoverState` dataclasses
    - Match response schemas from the design document
    - _Requirements: 4.4, 6.5_

  - [ ]* 4.3 Write unit tests for Failover MCP Server
    - Test `execute_failover` success path, replication verification failure, and error handling
    - Test `health_check` tool response structure
    - Test structured error responses
    - _Requirements: 4.4, 4.5, 6.4, 23.4_

- [x] 5. Pre-Check MCP Server implementation
  - [x] 5.1 Implement the Pre-Check MCP Server core module
    - Create `mcp-servers/workloads/postgresql/precheck/server.py` using the Strands SDK
    - Implement `verify_replication_health` tool: check replication lag, state, and data consistency
    - Implement `verify_primary_status` tool: verify primary instance status in us-east-1
    - Implement `verify_replica_readiness` tool: verify replica readiness for promotion in us-west-2
    - Return `VerificationResult` with check_name, passed status, details, and error fields
    - Return structured error responses on failure
    - _Requirements: 18.1, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8_

  - [x] 5.2 Implement VerificationResult data model for Pre-Check
    - Create `mcp-servers/workloads/postgresql/precheck/models.py` with `VerificationResult` dataclass
    - _Requirements: 18.7_

  - [ ]* 5.3 Write unit tests for Pre-Check MCP Server
    - Test each pre-check tool for success and failure scenarios
    - Test structured error response format
    - _Requirements: 18.7, 18.8, 23.5_

- [x] 6. Post-Check MCP Server implementation
  - [x] 6.1 Implement the Post-Check MCP Server core module
    - Create `mcp-servers/workloads/postgresql/postcheck/server.py` using the Strands SDK
    - Implement `verify_new_primary_health` tool: verify promoted instance health in us-west-2
    - Implement `verify_endpoints` tool: verify Parameter Store endpoint values reflect new primary
    - Implement `verify_replication_established` tool: verify replication from new primary is established
    - Return `VerificationResult` with check_name, passed status, details, and error fields
    - Return structured error responses on failure
    - _Requirements: 19.1, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8_

  - [x] 6.2 Implement VerificationResult data model for Post-Check
    - Create `mcp-servers/workloads/postgresql/postcheck/models.py` with `VerificationResult` dataclass
    - _Requirements: 19.7_

  - [ ]* 6.3 Write unit tests for Post-Check MCP Server
    - Test each post-check tool for success and failure scenarios
    - Test structured error response format
    - _Requirements: 19.7, 19.8, 23.6_

- [x] 7. Checkpoint — Validate MCP server implementations
  - Ensure all three MCP servers (Failover, Pre-Check, Post-Check) have correct tool definitions and response schemas. Ask the user if questions arise.

- [x] 8. AWS Support Stub Server implementation
  - [x] 8.1 Implement the AWS Support Stub Server
    - Create `mcp-servers/aws-support-stub/server.py` as an MCP server
    - Implement in-memory `support_cases` store with `SupportCase` and `CaseUpdate` dataclasses
    - Implement `create_support_case` tool: create case with unique ID (`makita-case-{date}-{seq}`), return `CreateCaseResult`
    - Implement `update_support_case` tool: update existing case status, return `UpdateCaseResult`; return structured error if case not found
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [ ]* 8.2 Write unit tests for AWS Support Stub Server
    - Test case creation, case update, and not-found error handling
    - _Requirements: 11.4, 11.5, 11.6, 23.7_

- [x] 9. ServiceNow Stub Server implementation
  - [x] 9.1 Implement the ServiceNow Stub Server
    - Create `mcp-servers/servicenow-stub/server.py` as an MCP server
    - Implement in-memory `tickets` store with `ServiceNowTicket` and `WorkNote` dataclasses
    - Implement `create_ticket` tool: create ticket with unique ID (`INC{seq:07d}`), return `CreateTicketResult`
    - Implement `update_ticket` tool: update existing ticket status, return `UpdateTicketResult`; return structured error if ticket not found
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 9.2 Write unit tests for ServiceNow Stub Server
    - Test ticket creation, ticket update, and not-found error handling
    - _Requirements: 12.4, 12.5, 12.6, 23.8_

- [x] 10. Checkpoint — Validate all MCP and stub server implementations
  - Ensure all five servers (Failover, Pre-Check, Post-Check, AWS Support Stub, ServiceNow Stub) are implemented and pass basic validation. Ask the user if questions arise.

- [x] 11. Event logging to markdown files
  - [x] 11.1 Implement the event logging module
    - Create `event-logs/event_logger.py` with functions to create and append to event log markdown files
    - File naming: `event-log-{case_id_or_ticket_id}.md`
    - Format: markdown header with case/ticket ID, followed by timestamped event entries using ISO 8601 format
    - Support creating a new event log file when a case/ticket is created
    - Support appending entries with timestamp and event description
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

  - [ ]* 11.2 Write unit tests for event logging
    - Test file creation, entry appending, ISO 8601 timestamp format, and file naming convention
    - _Requirements: 14.5, 14.6, 23.13_

- [x] 12. Failover sequence orchestration and DevOps Agent integration
  - [x] 12.1 Implement the failover sequence orchestrator
    - Create `orchestrator/failover_sequence.py` that coordinates the full failover sequence
    - Implement Phase 1 (Pre-Checks): invoke Pre-Check MCP Server tools (`verify_replication_health`, `verify_primary_status`, `verify_replica_readiness`); halt if any check fails
    - Implement Phase 2 (Failover): invoke Failover MCP Server `execute_failover` tool only after all pre-checks pass
    - Implement Phase 3 (Post-Checks): invoke Post-Check MCP Server tools (`verify_new_primary_health`, `verify_endpoints`, `verify_replication_established`) only after failover completes
    - Enforce strict phase ordering: Pre-Checks → Failover → Post-Checks
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.10, 17.11, 17.12, 17.13, 17.14, 17.15_

  - [x] 12.2 Implement ticketing integration during failover
    - Create `orchestrator/ticketing.py` with `TicketUpdateContext` dataclass
    - Create AWS Support case and ServiceNow ticket before failover begins
    - Update both tickets at each phase transition: "failover initiated", "replication verified", "promotion started", "promotion completed", "endpoints updated", "failover complete"
    - Update tickets on pre-check failure, failover failure, post-check failure, restart, and corrective actions
    - Include contextual information in every update: phase, resource names, parameter paths, AgentCore resources, regions, endpoints, replication status, IAM roles, error codes/messages, MCP server involved
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 13.11, 13.12, 13.13, 13.14, 13.15, 13.16, 13.17_

  - [x] 12.3 Implement DevOps Agent chat step display
    - Integrate chat messages into the orchestrator for each step: case/ticket creation, replication verification, replica promotion, endpoint update, ticket updates, failover completion
    - Display each step message before or at the time the corresponding operation begins
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8_

  - [x] 12.4 Wire event logging into the failover orchestrator
    - Create event log files when AWS Support case and ServiceNow ticket are created
    - Append event entries at each phase transition and status update
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x] 12.5 Implement DevOps Agent connection configuration
    - Configure DevOps Agent to connect to all five MCP servers: Failover, Pre-Check, Post-Check, AWS Support Stub, ServiceNow Stub
    - Ensure DevOps Agent can invoke tools on each server and receive results
    - _Requirements: 8.1, 8.2, 8.3, 11.7, 12.7, 18.9, 19.9_

- [x] 13. Checkpoint — Validate failover orchestration end-to-end
  - Ensure the full failover sequence (Pre-Checks → Failover → Post-Checks) executes correctly with ticketing, event logging, and chat display. Ask the user if questions arise.

- [x] 14. README.md documentation
  - [x] 14.1 Create the project README.md
    - Write project summary with purpose, technologies (Strands SDK, AgentCore, Bedrock Guardrails, CloudFormation, RDS PostgreSQL), and DR scenario description
    - Include Mermaid architecture diagram showing all components: DevOps Agent Space (`makita-agentspace`), AgentCore Gateway (`makita-mcp-gateway`), all MCP servers (as AgentCore Runtimes), stub servers, PostgreSQL cluster (us-east-1/us-west-2), Parameter Store, Bedrock Guardrails, Cedar Policies
    - Write Getting Started guide: prerequisites, setup instructions, deployment steps
    - Write CloudFormation deployment instructions
    - Write MCP server configuration instructions (Failover, Pre-Check, Post-Check)
    - Write failover initiation instructions via DevOps Agent
    - Write CloudWatch Dashboard monitoring instructions
    - Write instructions for reviewing event log files and ticket records
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7, 22.8_

  - [x] 14.2 Create the standalone architectural diagram
    - Create `architecture.md` at the project root as a standalone Mermaid-syntax diagram artifact
    - Use `graph TB` Mermaid syntax with subgraphs for each logical grouping
    - Include PostgreSQL cluster: primary instance (us-east-1) and replica instance (us-west-2) with replication relationship
    - Include AgentCore Gateway (`makita-mcp-gateway`) as unified entry point
    - Include MCP servers: Failover, Pre-Check, Post-Check (as AgentCore Runtimes)
    - Include stub servers: AWS Support Stub, ServiceNow Stub (as AgentCore Runtimes)
    - Include AgentCore governance: Cedar Policies, Bedrock Guardrails
    - Include DevOps Agent Space (`makita-agentspace`) with connections through gateway to all five MCP/stub servers
    - Include Parameter Store (`/makita/*` parameters)
    - Show relationships and data flows between all components
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8, 26.9, 26.10, 26.11_

- [x] 15. Comprehensive testing scripts
  - [x] 15.1 Create infrastructure provisioning tests
    - Write tests validating CloudFormation stack deployment and `makita-` prefix on all resources in correct regions
    - Write tests validating Parameter Store parameters with `/makita/` prefix and expected values
    - Write tests validating mandatory resource tags (`auto-delete=no`, `Env=prod1`) are present on all taggable resources
    - Write tests verifying tagging exceptions are documented via inline comments for resources that do not support tags (e.g., `AWS::CloudWatch::Dashboard`)
    - _Requirements: 23.1, 23.2, 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7, 24.8, 24.9, 24.10_

  - [x] 15.2 Create PostgreSQL cluster tests
    - Write tests validating primary instance in us-east-1, replica in us-west-2, and replication health
    - _Requirements: 23.3_

  - [x] 15.3 Create MCP server functionality tests
    - Write tests for Failover MCP Server: failover execution, completion verification, error handling
    - Write tests for Pre-Check MCP Server: replication health, primary status, replica readiness tools
    - Write tests for Post-Check MCP Server: new primary health, endpoint verification, replication established tools
    - _Requirements: 23.4, 23.5, 23.6_

  - [x] 15.4 Create stub server tests
    - Write tests for AWS Support Stub: case creation, case update, not-found error
    - Write tests for ServiceNow Stub: ticket creation, ticket update, not-found error
    - _Requirements: 23.7, 23.8_

  - [x] 15.5 Create AgentCore policy enforcement tests
    - Write tests verifying operations on non-`makita-` resources are denied
    - Write tests verifying operations targeting unauthorized regions are denied
    - Write tests verifying operations using non-`makita-` principals are denied
    - Write tests verifying operations on resources without the `Env=prod1` tag are denied for all three MCP servers (Failover, Pre-Check, Post-Check)
    - Write tests verifying operations on resources with the `Env=prod1` tag are allowed (when other constraints also pass)
    - _Requirements: 23.9, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6_

  - [x] 15.6 Create Bedrock Guardrails enforcement tests
    - Write tests verifying prompt injection detection and blocking
    - Write tests verifying malicious prompt blocking
    - Write tests verifying policy violation structured error responses
    - _Requirements: 23.10_

  - [x] 15.7 Create failover sequence orchestration tests
    - Write end-to-end tests for ordered Pre-Checks → Failover → Post-Checks execution
    - Write tests for failure scenarios at each phase (pre-check failure halts, post-check failure reports)
    - _Requirements: 23.11_

  - [x] 15.8 Create ticketing integration tests
    - Write tests verifying AWS Support case and ServiceNow ticket creation and updates at each phase
    - Write tests for failure, restart, and corrective action state recording in both systems
    - _Requirements: 23.12_

  - [x] 15.9 Create event logging tests
    - Write tests verifying markdown file creation for each case/ticket
    - Write tests verifying ISO 8601 timestamps and event descriptions in entries
    - _Requirements: 23.13_

  - [x] 15.10 Create CloudWatch Dashboard tests
    - Write tests verifying dashboard is not currently provisioned (Updated: `makita-failover-dashboard` was removed from the CloudFormation stack)
    - _Requirements: 23.14_

  - [x] 15.11 Create DevOps Agent chat step listing tests
    - Write tests verifying each failover sequence step is displayed as a chat message at the time the operation begins
    - _Requirements: 23.15_

  - [x] 15.12 Create architectural diagram tests
    - Write tests verifying `architecture.md` exists at the project root
    - Write tests verifying the file contains valid Mermaid syntax
    - Write tests verifying all required components are present in the diagram: PostgreSQL primary (us-east-1), PostgreSQL replica (us-west-2), replication relationship, AgentCore Gateway, Failover MCP Server, Pre-Check MCP Server, Post-Check MCP Server, Cedar Policies, Bedrock Guardrails, AWS Support Stub Server, ServiceNow Stub Server, DevOps Agent, Parameter Store
    - Write tests verifying DevOps Agent connections through the gateway to all five MCP/stub servers are shown
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8, 26.9, 26.10, 26.11_

- [x] 16. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. AgentCore Runtime and Gateway (Updated: implemented via `deploy_agentcore.py` Python script, not a CloudFormation stack)
  - [x] 17.1 Package MCP server code for S3 deployment
    - Packaging is handled within `deploy_agentcore.py` — each MCP server's code is zipped and uploaded to S3
    - Upload the ZIP artifacts to an S3 bucket (`makita-artifacts-{account_id}`) in us-east-1
    - _Requirements: 30.1, 30.2, 30.3_

  - [x] 17.2 Create AgentCore Runtimes and Endpoints via Python script
    - Create 5 separate AgentCore Runtimes (one per MCP server) with underscored names via `deploy_agentcore.py` (Updated: originally specified a single `makita-mcp-runtime` in a CFN stack)
    - Create Runtime Endpoints for each Runtime
    - Each Runtime uses code configuration (S3 artifact, Python 3.11, MCP protocol, PUBLIC network)
    - _Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7_

  - [x] 17.3 Create AgentCore Gateway and Gateway Targets via Python script
    - Create `makita-mcp-gateway` with MCP protocol, IAM auth, failover role via `deploy_agentcore.py`
    - Create gateway targets for each MCP server, each referencing the corresponding Runtime Endpoint
    - Attach Cedar policies from `policies/agentcore/` to each gateway target
    - Attach Bedrock Guardrails from `policies/guardrails/` to each runtime
    - _Requirements: 28.1, 28.2, 28.3, 28.4, 28.5, 28.6_

  - [x] 17.4 Create AgentCore Workload Identities via Python script
    - Create workload identities via `create_workload_identity` API in `deploy_agentcore.py`
    - Map each Workload Identity to its corresponding IAM role
    - _Requirements: 29.1, 29.2, 29.3_

  - [x] 17.5 Update deploy script with agentcore target
    - Add `agentcore` target to `deploy.sh` that invokes `deploy_agentcore.py`
    - _Requirements: 30.1, 30.2, 30.3_

- [x] 18. DevOps Agent Space deployment (Updated: added during implementation)
  - [x] 18.1 Create DevOps Agent Space via Python script
    - Create `scripts/deploy_devops_agent.py` that creates `makita-agentspace` with operator IAM role, web app, and log group
    - Add `devops-agent` target to `deploy.sh`
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 19. Kiro agent configuration (Updated: added during implementation)
  - [x] 19.1 Create Kiro agent config and gateway proxy
    - Create `scripts/deploy_kiro_agent.py` that looks up the gateway endpoint and patches the agent config
    - Create `.kiro/agents/makita-ops.json` with gateway proxy MCP server configuration
    - Create `mcp-servers/agentcore_gateway_proxy.py` for Kiro IDE-based DR operations
    - Add `kiro-agent` target to `deploy.sh`

- [x] 20. Checkpoint — Validate AgentCore Runtime, Gateway, DevOps Agent Space, and Kiro agent deployment
  - Ensure all AgentCore resources deploy successfully with Runtimes, Endpoints, Gateway, Targets, Workload Identities, Cedar Policies, and Guardrails. Ensure DevOps Agent Space and Kiro agent config are functional.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- All MCP servers use Python with the Strands SDK
- Infrastructure uses two CloudFormation stacks under `infrastructure/workloads/postgresql/`: `makita-postgresql-stack` (us-east-1) and `makita-postgresql-replica-stack` (us-west-2). AgentCore resources are deployed via `scripts/deploy_agentcore.py`. DevOps Agent Space is deployed via `scripts/deploy_devops_agent.py`. Kiro agent config is deployed via `scripts/deploy_kiro_agent.py`.
- All resource names use `makita-` prefix, all Parameter Store paths use `/makita/` prefix
- All taggable AWS resources must carry mandatory tags: `auto-delete=no` and `Env=prod1`
- Cedar policies in `policies/agentcore/` enforce `Env=prod1` tag constraint in addition to `makita-*` prefix, region, and principal constraints
- Bedrock Guardrail configs are externalized as standalone JSON files in `policies/guardrails/` for all 5 servers (including stub servers)
- Resources that do not support CloudFormation tagging are documented as exceptions via inline comments
- The standalone architectural diagram (`architecture.md`) is maintained separately from the README for independent review
- The `makita-failover-dashboard` CloudWatch Dashboard was removed from the CloudFormation stack
- Secrets Manager (`makita-db-master-secret`) is used for the PostgreSQL master password
- The `deploy.sh` script supports targets: `postgresql`, `postgresql-dr`, `agentcore`, `devops-agent`, `kiro-agent`, `all`
