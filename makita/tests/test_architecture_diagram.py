"""
Architectural diagram tests for the MAKITA project.

Validates that architecture.md exists at the project root, contains valid
Mermaid syntax, includes all required components, and shows DevOps Agent
connections to all five MCP/stub servers.

Validates: Requirements 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8, 26.9, 26.10, 26.11
"""

import pytest
from pathlib import Path


ARCHITECTURE_PATH = Path(__file__).parent.parent / "architecture.md"


@pytest.fixture(scope="module")
def architecture_content():
    """Read the raw text content of architecture.md."""
    return ARCHITECTURE_PATH.read_text()


# =========================================================================
# Requirement 26.1 — Standalone artifact exists
# =========================================================================

class TestArchitectureFileExists:
    """Validate architecture.md exists at the project root."""

    def test_architecture_md_exists(self):
        assert ARCHITECTURE_PATH.exists(), (
            "architecture.md does not exist at the project root"
        )

    def test_architecture_md_is_file(self):
        assert ARCHITECTURE_PATH.is_file(), (
            "architecture.md exists but is not a regular file"
        )

    def test_architecture_md_is_not_empty(self, architecture_content):
        assert len(architecture_content.strip()) > 0, (
            "architecture.md exists but is empty"
        )


# =========================================================================
# Requirement 26.2 — Valid Mermaid syntax
# =========================================================================

class TestMermaidSyntax:
    """Validate the file contains valid Mermaid syntax."""

    def test_contains_mermaid_code_block(self, architecture_content):
        assert "```mermaid" in architecture_content, (
            "architecture.md does not contain a ```mermaid code block"
        )

    def test_uses_graph_tb(self, architecture_content):
        assert "graph TB" in architecture_content, (
            "architecture.md Mermaid diagram does not use 'graph TB'"
        )


# =========================================================================
# Requirement 26.3 — PostgreSQL cluster with replication
# =========================================================================

class TestPostgreSQLCluster:
    """Validate PostgreSQL primary, replica, and replication relationship."""

    def test_postgresql_primary_us_east_1(self, architecture_content):
        assert "PostgreSQL" in architecture_content, (
            "architecture.md does not mention PostgreSQL"
        )
        assert "Primary" in architecture_content, (
            "architecture.md does not mention Primary instance"
        )
        assert "us-east-1" in architecture_content, (
            "architecture.md does not mention us-east-1"
        )

    def test_postgresql_replica_us_west_2(self, architecture_content):
        assert "Replica" in architecture_content, (
            "architecture.md does not mention Replica instance"
        )
        assert "us-west-2" in architecture_content, (
            "architecture.md does not mention us-west-2"
        )

    def test_replication_relationship(self, architecture_content):
        assert "replication" in architecture_content.lower(), (
            "architecture.md does not show a replication relationship"
        )


# =========================================================================
# Requirement 26.4 — CloudWatch Dashboard
# =========================================================================

class TestCloudWatchDashboard:
    """Validate CloudWatch Dashboard is present."""

    def test_cloudwatch_dashboard_present(self, architecture_content):
        assert "CloudWatch Dashboard" in architecture_content, (
            "architecture.md does not include CloudWatch Dashboard"
        )


# =========================================================================
# Requirement 26.5 — MCP Servers (Failover, Pre-Check, Post-Check)
# =========================================================================

class TestMCPServers:
    """Validate all three MCP servers are present."""

    def test_failover_mcp_server(self, architecture_content):
        assert "Failover" in architecture_content, (
            "architecture.md does not include Failover MCP Server"
        )
        assert "MCP Server" in architecture_content, (
            "architecture.md does not mention MCP Server"
        )

    def test_precheck_mcp_server(self, architecture_content):
        assert "Pre-Check" in architecture_content, (
            "architecture.md does not include Pre-Check MCP Server"
        )

    def test_postcheck_mcp_server(self, architecture_content):
        assert "Post-Check" in architecture_content, (
            "architecture.md does not include Post-Check MCP Server"
        )


# =========================================================================
# Requirement 26.6 — AgentCore governance components
# =========================================================================

class TestAgentCoreGovernance:
    """Validate AgentCore Policies, Identities, and Bedrock Guardrails."""

    def test_agentcore_policies(self, architecture_content):
        assert "AgentCore Policies" in architecture_content, (
            "architecture.md does not include AgentCore Policies"
        )

    def test_agentcore_identities(self, architecture_content):
        assert "AgentCore Identities" in architecture_content, (
            "architecture.md does not include AgentCore Identities"
        )

    def test_bedrock_guardrails(self, architecture_content):
        assert "Bedrock Guardrails" in architecture_content, (
            "architecture.md does not include Bedrock Guardrails"
        )


# =========================================================================
# Requirement 26.7 — AWS Support Stub Server
# =========================================================================

class TestAWSSupportStub:
    """Validate AWS Support Stub Server is present."""

    def test_aws_support_stub_server(self, architecture_content):
        assert "AWS Support" in architecture_content, (
            "architecture.md does not include AWS Support Stub Server"
        )
        assert "Stub Server" in architecture_content, (
            "architecture.md does not mention Stub Server"
        )


# =========================================================================
# Requirement 26.8 — ServiceNow Stub Server
# =========================================================================

class TestServiceNowStub:
    """Validate ServiceNow Stub Server is present."""

    def test_servicenow_stub_server(self, architecture_content):
        assert "ServiceNow" in architecture_content, (
            "architecture.md does not include ServiceNow Stub Server"
        )


# =========================================================================
# Requirement 26.9 — DevOps Agent connections to all five servers
# =========================================================================

class TestDevOpsAgentConnections:
    """Validate DevOps Agent and its connections to all five MCP/stub servers."""

    def test_devops_agent_present(self, architecture_content):
        assert "DevOps Agent" in architecture_content, (
            "architecture.md does not include DevOps Agent"
        )

    def test_devops_agent_to_precheck(self, architecture_content):
        # DA --> PreMCP connection
        assert "DA --> PreMCP" in architecture_content, (
            "architecture.md does not show DevOps Agent connection to Pre-Check MCP Server"
        )

    def test_devops_agent_to_failover(self, architecture_content):
        # DA --> FailMCP connection
        assert "DA --> FailMCP" in architecture_content, (
            "architecture.md does not show DevOps Agent connection to Failover MCP Server"
        )

    def test_devops_agent_to_postcheck(self, architecture_content):
        # DA --> PostMCP connection
        assert "DA --> PostMCP" in architecture_content, (
            "architecture.md does not show DevOps Agent connection to Post-Check MCP Server"
        )

    def test_devops_agent_to_aws_support_stub(self, architecture_content):
        # DA --> AWSS connection
        assert "DA --> AWSS" in architecture_content, (
            "architecture.md does not show DevOps Agent connection to AWS Support Stub Server"
        )

    def test_devops_agent_to_servicenow_stub(self, architecture_content):
        # DA --> SNS connection
        assert "DA --> SNS" in architecture_content, (
            "architecture.md does not show DevOps Agent connection to ServiceNow Stub Server"
        )


# =========================================================================
# Requirement 26.10 — Parameter Store
# =========================================================================

class TestParameterStore:
    """Validate Parameter Store is present."""

    def test_parameter_store_present(self, architecture_content):
        assert "Parameter Store" in architecture_content, (
            "architecture.md does not include Parameter Store"
        )


# =========================================================================
# Requirement 26.11 — Relationships and data flows
# =========================================================================

class TestRelationshipsAndDataFlows:
    """Validate relationships and data flows between components."""

    def test_governance_relationships_shown(self, architecture_content):
        # Guardrails govern MCP servers
        assert "governs" in architecture_content, (
            "architecture.md does not show governance relationships"
        )

    def test_policy_restriction_relationships_shown(self, architecture_content):
        # Policies restrict MCP servers
        assert "restricts" in architecture_content, (
            "architecture.md does not show policy restriction relationships"
        )

    def test_identity_relationships_shown(self, architecture_content):
        # Identities provide identity to MCP servers
        assert "identity" in architecture_content, (
            "architecture.md does not show identity relationships"
        )
