"""
Cedar policy tests for the MAKITA AgentCore Gateway targets.

Validates that each Cedar policy file in policies/agentcore/:
  - Exists and is non-empty
  - Contains permit and forbid statements
  - References exactly the tool actions exposed by its MCP server
  - Enforces proj=makita and Env=prod1 tag constraints

Each policy file maps 1:1 to an MCP server behind the AgentCore Gateway.
"""

import re
from pathlib import Path

import pytest

POLICIES_DIR = Path(__file__).parent.parent / "policies" / "agentcore"

# Expected Cedar policy files and the tool actions each must reference.
# These must match the @tool-decorated functions in each server.py.
EXPECTED_POLICIES = {
    "postgresql-failover.cedar": [
        "execute_failover",
        "health_check",
    ],
    "postgresql-precheck.cedar": [
        "verify_replication_health",
        "verify_primary_status",
        "verify_replica_readiness",
    ],
    "postgresql-postcheck.cedar": [
        "verify_new_primary_health",
        "verify_endpoints",
        "verify_replication_established",
    ],
    "aws-support-stub.cedar": [
        "create_support_case",
        "update_support_case",
    ],
    "servicenow-stub.cedar": [
        "create_ticket",
        "update_ticket",
    ],
}


def _read_policy(filename: str) -> str:
    return (POLICIES_DIR / filename).read_text()


def _extract_actions(content: str) -> list[str]:
    """Extract all Action::"name" references from Cedar content."""
    return re.findall(r'Action::"(\w+)"', content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCedarPolicyFilesExist:
    """Every expected Cedar policy file must exist and be non-empty."""

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_policy_file_exists(self, filename):
        path = POLICIES_DIR / filename
        assert path.exists(), f"Missing Cedar policy: {path}"

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_policy_file_not_empty(self, filename):
        content = _read_policy(filename)
        assert len(content.strip()) > 0

    def test_no_unexpected_policy_files(self):
        actual = {p.name for p in POLICIES_DIR.glob("*.cedar")}
        expected = set(EXPECTED_POLICIES.keys())
        assert actual == expected, f"Unexpected files: {actual - expected}"


class TestCedarPolicyStructure:
    """Each policy must contain both permit and forbid statements."""

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_has_permit_statement(self, filename):
        content = _read_policy(filename)
        assert "permit(" in content

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_has_forbid_statement(self, filename):
        content = _read_policy(filename)
        assert "forbid(" in content


class TestCedarPolicyActions:
    """Each policy must reference exactly the actions its MCP server exposes."""

    @pytest.mark.parametrize("filename,expected_actions", list(EXPECTED_POLICIES.items()))
    def test_actions_match_server_tools(self, filename, expected_actions):
        content = _read_policy(filename)
        actions = _extract_actions(content)
        # Each action appears in both permit and forbid blocks
        unique_actions = sorted(set(actions))
        assert unique_actions == sorted(expected_actions), (
            f"{filename}: expected {sorted(expected_actions)}, got {unique_actions}"
        )


class TestCedarPolicyTagConstraints:
    """Each policy must enforce proj=makita and Env=prod1 tag constraints."""

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_enforces_proj_makita_tag(self, filename):
        content = _read_policy(filename)
        assert '"proj"' in content and '"makita"' in content

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_enforces_env_prod1_tag(self, filename):
        content = _read_policy(filename)
        assert '"Env"' in content and '"prod1"' in content
