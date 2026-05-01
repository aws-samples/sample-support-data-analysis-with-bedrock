"""Architectural diagram tests for the MAKITA project.

Validates that architecture.md contains valid Mermaid syntax, includes all
required components, and shows DevOps Agent connections through the
AgentCore Gateway to the three PostgreSQL MCP servers.
"""

import pytest
from pathlib import Path

ARCHITECTURE_PATH = Path(__file__).parent.parent / "architecture.md"


@pytest.fixture(scope="module")
def architecture_content():
    return ARCHITECTURE_PATH.read_text()


class TestArchitectureFileExists:
    def test_architecture_md_exists(self):
        assert ARCHITECTURE_PATH.exists()

    def test_architecture_md_is_file(self):
        assert ARCHITECTURE_PATH.is_file()

    def test_architecture_md_is_not_empty(self, architecture_content):
        assert len(architecture_content.strip()) > 0


class TestMermaidSyntax:
    def test_contains_mermaid_code_block(self, architecture_content):
        assert "```mermaid" in architecture_content

    def test_uses_graph_tb(self, architecture_content):
        assert "graph TB" in architecture_content


class TestPostgreSQLCluster:
    def test_postgresql_primary_us_east_1(self, architecture_content):
        assert "PostgreSQL" in architecture_content
        assert "Primary" in architecture_content
        assert "us-east-1" in architecture_content

    def test_postgresql_replica_us_west_2(self, architecture_content):
        assert "Replica" in architecture_content
        assert "us-west-2" in architecture_content

    def test_replication_relationship(self, architecture_content):
        assert "replication" in architecture_content.lower()


class TestCloudWatchDashboard:
    def test_cloudwatch_dashboard_present(self, architecture_content):
        assert "CloudWatch Dashboard" in architecture_content


class TestMCPServers:
    def test_failover_mcp_server(self, architecture_content):
        assert "Failover" in architecture_content
        assert "MCP Server" in architecture_content

    def test_precheck_mcp_server(self, architecture_content):
        assert "Pre-Check" in architecture_content

    def test_postcheck_mcp_server(self, architecture_content):
        assert "Post-Check" in architecture_content


class TestAgentCoreGovernance:
    def test_agentcore_policies(self, architecture_content):
        assert "AgentCore Policies" in architecture_content

    def test_agentcore_identities(self, architecture_content):
        assert "AgentCore Identities" in architecture_content

    def test_bedrock_guardrails(self, architecture_content):
        assert "Bedrock Guardrails" in architecture_content


class TestAgentCoreGateway:
    def test_gateway_present(self, architecture_content):
        assert "AgentCore Gateway" in architecture_content

    def test_devops_agent_connects_to_gateway(self, architecture_content):
        assert "DA --> GW" in architecture_content

    def test_gateway_connects_to_mcp_servers(self, architecture_content):
        assert "GW --> PreMCP" in architecture_content
        assert "GW --> FailMCP" in architecture_content
        assert "GW --> PostMCP" in architecture_content


class TestDevOpsAgentConnections:
    def test_devops_agent_present(self, architecture_content):
        assert "DevOps Agent" in architecture_content

    def test_devops_agent_to_gateway(self, architecture_content):
        assert "DA --> GW" in architecture_content


class TestParameterStore:
    def test_parameter_store_present(self, architecture_content):
        assert "Parameter Store" in architecture_content


class TestRelationshipsAndDataFlows:
    def test_governance_relationships_shown(self, architecture_content):
        assert "governs" in architecture_content

    def test_policy_restriction_relationships_shown(self, architecture_content):
        assert "restricts" in architecture_content

    def test_identity_relationships_shown(self, architecture_content):
        assert "identity" in architecture_content
