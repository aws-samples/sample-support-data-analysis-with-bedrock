# MAKITA — Machine Augmented Key Infrastructure

MAKITA is a reference architecture that demonstrates how Amazon DevOps Agent can orchestrate a multi-region Disaster Recovery (DR) failover for an RDS PostgreSQL database. It automates the full lifecycle — pre-flight validation, replica promotion, DNS cutover, post-flight checks, and incident coordination across Slack, ServiceNow, and AWS Support — all driven through a custom MCP server running on Amazon Bedrock AgentCore.

## What It Does

- **RDS Multi-Region Failover** — Promotes a cross-region read replica (us-east-2) to a standalone read-write instance when the primary (us-east-1) is unavailable
- **Pre/Post Validation** — Runs automated checks before and after failover to confirm replica health, replication lag, network connectivity, DNS routing, and read-write mode
- **Incident Management** — Creates and updates tickets in ServiceNow (via stub) and AWS Support (via stub), and coordinates the entire exercise in a dedicated Slack channel (`makita-dr-YYYYMMDD`)
- **MCP Server on AgentCore** — Exposes DR tools to the DevOps Agent with Bedrock Guardrails, Cognito authentication, and AgentCore Policy authorization
- **CloudWatch Dashboard** — Visualizes primary and DR region RDS metrics with cross-region comparison widgets
- **Configuration via Parameter Store** — All settings are centralized in SSM Parameter Store under the `/makita-dr/` prefix

## Project Structure

```
makita_dr/                  # Core Python package
├── models.py             # Data models (DRConfig, FailoverEvent, etc.)
├── config_loader.py      # SSM Parameter Store configuration loader
├── pre_check_engine.py   # Pre-failover validation checks
├── post_check_engine.py  # Post-failover validation checks
├── rds_failover.py       # RDS replica promotion and DNS update
├── incident_manager.py   # Slack, ServiceNow, and AWS Support integrations
├── servicenow_stub.py    # ServiceNow REST API stub server (Flask)
├── aws_support_stub.py   # AWS Support API stub server (Flask)
├── mcp_server.py         # Custom MCP server with Guardrails and auth
├── cloudwatch_dashboard.py # CloudWatch Dashboard manager
├── dr_orchestrator.py    # Central orchestrator wiring everything together
└── retry.py              # Exponential backoff retry decorator

makita_dr_summary/          # Lambda function package
└── handler.py            # Generates comprehensive failover summaries

infrastructure/           # CloudFormation templates
├── rds-primary.yaml
├── rds-replica.yaml
└── ssm-parameters.yaml

tests/                    # Unit and integration tests
```

## Getting Started

### Prerequisites

- Python 3.9+
- AWS credentials configured (for Boto3)
- An AWS account with RDS, Route53, SSM, CloudWatch, and Lambda access

### Installation

```bash
# Clone the repository
git clone <repo-url> && cd makita

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running Tests

The test suite uses `pytest` with `moto` for AWS service mocking — no live AWS resources needed.

```bash
python -m pytest tests/ -v
```

### Configuration

Populate SSM Parameter Store with the required parameters under `/makita-dr/`. See `infrastructure/ssm-parameters.yaml` for the full list. Sensitive values (API keys, tokens) should use `SecureString` type.

### Usage

```python
from makita_dr.config_loader import ConfigLoader
from makita_dr.dr_orchestrator import DROrchestrator

# Load configuration from Parameter Store
config = ConfigLoader(region="us-east-1").load_config()

# Run the DR failover
orchestrator = DROrchestrator(config)
result = orchestrator.initiate_failover()

print(f"Status: {result.event.status.value}")
print(f"Summary: {result.summary}")
```

### Stub Servers

For local development, start the ServiceNow and AWS Support stub servers:

```python
from makita_dr.servicenow_stub import ServiceNowStubServer
from makita_dr.aws_support_stub import AWSSupportStub

ServiceNowStubServer(port=8080).start()
AWSSupportStub(port=8081).start()
```

## License

This project is provided as a reference architecture for demonstration purposes.
