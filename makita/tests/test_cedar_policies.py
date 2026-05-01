"""Cedar policy tests for the MAKITA AgentCore Gateway targets.

Validates that each Cedar policy file in policies/agentcore/:
  - Exists and is non-empty
  - Contains permit and forbid statements
  - References exactly the tool actions exposed by its MCP server
  - Enforces proj=makita and Env=prod1 tag constraints
"""

import re
from pathlib import Path

import pytest

POLICIES_DIR = Path(__file__).parent.parent / "policies" / "agentcore"

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
}


def _read_policy(filename: str) -> str:
    return (POLICIES_DIR / filename).read_text()


def _extract_actions(content: str) -> list[str]:
    return re.findall(r'Action::"(\w+)"', content)


class TestCedarPolicyFilesExist:
    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_policy_file_exists(self, filename):
        assert (POLICIES_DIR / filename).exists()

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_policy_file_not_empty(self, filename):
        assert len(_read_policy(filename).strip()) > 0

    def test_no_unexpected_policy_files(self):
        actual = {p.name for p in POLICIES_DIR.glob("*.cedar")}
        assert actual == set(EXPECTED_POLICIES.keys())


class TestCedarPolicyStructure:
    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_has_permit_statement(self, filename):
        assert "permit(" in _read_policy(filename)

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_has_forbid_statement(self, filename):
        assert "forbid(" in _read_policy(filename)


class TestCedarPolicyActions:
    @pytest.mark.parametrize("filename,expected_actions", list(EXPECTED_POLICIES.items()))
    def test_actions_match_server_tools(self, filename, expected_actions):
        actions = _extract_actions(_read_policy(filename))
        assert sorted(set(actions)) == sorted(expected_actions)


class TestCedarPolicyTagConstraints:
    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_enforces_proj_makita_tag(self, filename):
        content = _read_policy(filename)
        assert '"proj"' in content and '"makita"' in content

    @pytest.mark.parametrize("filename", list(EXPECTED_POLICIES.keys()))
    def test_enforces_env_prod1_tag(self, filename):
        content = _read_policy(filename)
        assert '"Env"' in content and '"prod1"' in content
