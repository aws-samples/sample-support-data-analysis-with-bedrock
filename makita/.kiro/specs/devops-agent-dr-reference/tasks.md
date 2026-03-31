# Implementation Plan: DevOps Agent DR Reference Architecture

## Overview

Implement a reference architecture for Amazon DevOps Agent orchestrating RDS Postgres multi-region DR failover. All code is Python with Boto3. Components are built incrementally: data models and config first, then core engines, then integrations, then MCP server, then dashboard, and finally the orchestrator wiring everything together.

## Tasks

- [x] 1. Set up project structure, data models, and configuration loader
  - [x] 1.1 Create project directory structure and `requirements.txt` with dependencies (boto3, hypothesis, slack_sdk, pysnow, flask)
    - Create `makita_dr/` package with `__init__.py`
    - Create `makita_dr/models.py`, `makita_dr/config_loader.py`
    - Create `makita_dr_summary/` Lambda package
    - Create `tests/` directory
    - _Requirements: 11.1_

  - [x] 1.2 Implement data models in `makita_dr/models.py`
    - Implement `FailoverStatus`, `CheckStatus` enums
    - Implement `DRConfig`, `CheckResult`, `PreCheckResult`, `PostCheckResult`, `PromoteResult`, `DNSUpdateResult`, `FailoverEvent`, `FailoverResult` dataclasses
    - _Requirements: 1.1, 2.1, 3.1_

  - [x] 1.3 Implement configuration loader in `makita_dr/config_loader.py`
    - Implement `ConfigLoader` class with `/makita-dr/` parameter prefix
    - Load all required parameters from SSM Parameter Store using Boto3
    - Use `WithDecryption=True` for SecureString parameters (API keys, credentials)
    - Raise `MissingConfigError` with the specific parameter name if any required parameter is absent
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 1.4 Write property test for missing configuration detection
    - **Property 18: Missing configuration halts workflow**
    - **Validates: Requirements 10.5**

- [x] 2. Implement pre-check and post-check engines
  - [x] 2.1 Implement pre-check engine in `makita_dr/pre_check_engine.py`
    - Implement `PreCheckEngine` with `run_all_checks()`, `check_replica_health()`, `check_replication_lag()`, `check_network_connectivity()`
    - Use Boto3 RDS client to check replica status and replication lag
    - Use Boto3 EC2 client to verify VPC/security group/subnet connectivity
    - Aggregate individual check results into `PreCheckResult`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Implement post-check engine in `makita_dr/post_check_engine.py`
    - Implement `PostCheckEngine` with `run_all_checks()`, `check_read_write_mode()`, `check_application_queries()`, `check_dns_routing()`
    - Use Boto3 RDS client to verify promoted instance status
    - Aggregate individual check results into `PostCheckResult`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 2.3 Write property test for check result aggregation
    - **Property 1: Check result aggregation**
    - **Validates: Requirements 2.5, 2.6, 3.5, 3.6**

  - [ ]* 2.4 Write property test for replication lag threshold
    - **Property 2: Replication lag threshold comparison**
    - **Validates: Requirements 2.3**

- [x] 3. Implement RDS failover manager
  - [x] 3.1 Implement RDS failover manager in `makita_dr/rds_failover.py`
    - Implement `RDSFailoverManager` with `identify_instances()`, `promote_read_replica()`, `update_dns()`, `verify_read_write()`
    - Use Boto3 RDS client for `describe_db_instances` and `promote_read_replica`
    - Use Boto3 Route53 client for DNS record updates
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 4. Checkpoint - Ensure core engines work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement incident management integrations
  - [x] 5.1 Implement Slack integration in `makita_dr/incident_manager.py`
    - Implement Slack channel creation with "makita-dr-YYYYMMDD" naming
    - Implement message posting, action logging, and status updates using `slack_sdk`
    - Implement @makita mention handling for status queries
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 5.2 Write property test for Slack channel naming
    - **Property 4: Slack channel naming**
    - **Validates: Requirements 5.1**

  - [ ]* 5.3 Write property test for Slack status response completeness
    - **Property 7: Slack status response completeness**
    - **Validates: Requirements 5.6**

  - [x] 5.4 Implement ServiceNow stub server in `makita_dr/servicenow_stub.py`
    - Implement `ServiceNowStubServer` as a Flask app mimicking ServiceNow REST API
    - Log and store all incoming requests for verification
    - _Requirements: 4.1, 4.6_

  - [x] 5.5 Implement ServiceNow client in `makita_dr/incident_manager.py`
    - Use the official `pysnow` SDK to create and update incident tickets
    - Point the SDK at the stub server endpoint from config
    - _Requirements: 4.2, 4.3, 4.4, 4.5_

  - [ ]* 5.6 Write property test for ServiceNow ticket field completeness
    - **Property 8: ServiceNow ticket field completeness**
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 5.7 Write property test for ServiceNow stub request logging
    - **Property 10: ServiceNow stub server request logging**
    - **Validates: Requirements 4.6**

  - [x] 5.8 Implement AWS Support stub in `makita_dr/aws_support_stub.py`
    - Implement `AWSSupportStub` as a Flask app intercepting Boto3 Support API calls
    - Log and store all received API calls for verification
    - _Requirements: 6.1, 6.6_

  - [x] 5.9 Implement AWS Support client in `makita_dr/incident_manager.py`
    - Use actual Boto3 Support client with `endpoint_url` override pointing to stub
    - Create and update support cases with event summary, regions, and severity
    - _Requirements: 6.2, 6.3, 6.4, 6.5_

  - [ ]* 5.10 Write property test for AWS Support ticket field completeness
    - **Property 11: AWS Support ticket field completeness**
    - **Validates: Requirements 6.1, 6.2**

  - [x] 5.11 Implement retry mechanism with exponential backoff in `makita_dr/retry.py`
    - Shared retry decorator/utility for all external API calls
    - Base delay 1s, multiplied by 2^attempt, max 3 retries
    - _Requirements: 4.7, 5.7, 6.7_

  - [ ]* 5.12 Write property test for retry exponential backoff
    - **Property 13: Retry with exponential backoff**
    - **Validates: Requirements 4.7, 5.7, 6.7**

- [x] 6. Checkpoint - Ensure incident management integrations work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement MCP server and Lambda function
  - [x] 7.1 Implement Lambda summary function in `makita_dr_summary/handler.py`
    - Accept FailoverEvent data as input
    - Collect and format pre-check results, failover steps, post-check results, and incident management actions
    - Return formatted summary string
    - _Requirements: 7.3, 7.4_

  - [ ]* 7.2 Write property test for Lambda summary completeness
    - **Property 14: Lambda summary completeness**
    - **Validates: Requirements 7.4**

  - [x] 7.3 Implement MCP server in `makita_dr/mcp_server.py`
    - Implement `DRMCPServer` with tool listing and invocation
    - Integrate Guardrails evaluation on all incoming requests
    - Integrate Cognito authentication via AgentCore Identity
    - Integrate AgentCore Policy authorization
    - Restrict Lambda invocation to Cognito-authenticated identities only
    - Log all Guardrail evaluations and auth decisions for audit
    - _Requirements: 7.1, 7.2, 7.5, 7.6, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 7.4 Write property test for Guardrails enforcement
    - **Property 15: Guardrails enforcement and violation rejection**
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 7.5 Write property test for authentication and authorization
    - **Property 16: Authentication and authorization enforcement**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

  - [ ]* 7.6 Write property test for audit logging completeness
    - **Property 17: Audit logging completeness**
    - **Validates: Requirements 8.3, 9.6**

  - [ ]* 7.7 Write property test for Lambda error propagation
    - **Property 20: Lambda error propagation**
    - **Validates: Requirements 7.6**

- [x] 8. Implement CloudWatch Dashboard
  - [x] 8.1 Implement CloudWatch Dashboard manager in `makita_dr/cloudwatch_dashboard.py`
    - Create `makita-dr-dashboard` using Boto3 CloudWatch client
    - Add widgets for primary region RDS metrics (connection count, CPU utilization, DB connections)
    - Add widgets for DR region RDS metrics (replication lag, connection count, CPU utilization)
    - Add cross-region comparison widgets
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 9. Implement DR Orchestrator and wire everything together
  - [x] 9.1 Implement DR Orchestrator in `makita_dr/dr_orchestrator.py`
    - Wire together: ConfigLoader → Slack channel creation → incident ticket creation → pre-checks → RDS failover → post-checks → ticket updates → MCP summary → Slack final summary
    - Log every action to the Slack channel
    - Halt on any failover error, log details, update tickets with failure status
    - Implement `handle_slack_question()` for @makita status queries
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.3, 5.5, 5.6_

  - [ ]* 9.2 Write property test for failover halts on error
    - **Property 3: Failover halts on error**
    - **Validates: Requirements 1.5**

  - [ ]* 9.3 Write property test for Slack action logging completeness
    - **Property 6: Slack action logging completeness**
    - **Validates: Requirements 5.3**

  - [ ]* 9.4 Write property test for resource naming prefix
    - **Property 19: Resource naming prefix**
    - **Validates: Requirements 11.1, 11.2, 11.3**

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests use `hypothesis` library with minimum 100 iterations each
- Unit tests use `pytest` with `moto` for AWS service mocking
- All resources use the "makita-dr-" prefix per Requirement 11
