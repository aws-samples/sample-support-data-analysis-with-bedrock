"""Tests for orchestrator.agent_config — DevOps Agent connection configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import types

import pytest

from orchestrator.agent_config import get_agent_config, invoke_tool


# ---------------------------------------------------------------------------
# Helpers — build lightweight stub modules so importlib.import_module
# returns something with the expected attributes without touching boto3.
# ---------------------------------------------------------------------------

def _make_failover_module():
    mod = types.ModuleType("mcp-servers.workloads.postgresql.failover.server")
    mod.execute_failover = lambda **kw: {"success": True}
    mod.health_check = lambda **kw: {"cluster_name": "test"}
    return mod


def _make_precheck_module():
    mod = types.ModuleType("mcp-servers.workloads.postgresql.precheck.server")
    mod.verify_replication_health = lambda **kw: {"passed": True}
    mod.verify_primary_status = lambda **kw: {"passed": True}
    mod.verify_replica_readiness = lambda **kw: {"passed": True}
    return mod


def _make_postcheck_module():
    mod = types.ModuleType("mcp-servers.workloads.postgresql.postcheck.server")
    mod.verify_new_primary_health = lambda **kw: {"passed": True}
    mod.verify_endpoints = lambda **kw: {"passed": True}
    mod.verify_replication_established = lambda **kw: {"passed": True}
    return mod


def _make_aws_support_module():
    mod = types.ModuleType("mcp-servers.aws-support-stub.server")
    mod.create_support_case = lambda **kw: {"case_id": "c1"}
    mod.update_support_case = lambda **kw: {"case_id": "c1"}
    return mod


def _make_servicenow_module():
    mod = types.ModuleType("mcp-servers.servicenow-stub.server")
    mod.create_ticket = lambda **kw: {"ticket_id": "t1"}
    mod.update_ticket = lambda **kw: {"ticket_id": "t1"}
    return mod


_FAKE_MODULES = {
    "mcp-servers.workloads.postgresql.failover.server": _make_failover_module(),
    "mcp-servers.workloads.postgresql.precheck.server": _make_precheck_module(),
    "mcp-servers.workloads.postgresql.postcheck.server": _make_postcheck_module(),
    "mcp-servers.aws-support-stub.server": _make_aws_support_module(),
    "mcp-servers.servicenow-stub.server": _make_servicenow_module(),
}


def _fake_import(name):
    if name in _FAKE_MODULES:
        return _FAKE_MODULES[name]
    raise ImportError(name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("orchestrator.agent_config.importlib.import_module", side_effect=_fake_import)
class TestGetAgentConfig:
    """Validates get_agent_config returns the correct structure."""

    def test_returns_all_five_servers(self, _mock_import):
        cfg = get_agent_config()
        assert set(cfg.keys()) == {
            "failover",
            "precheck",
            "postcheck",
            "aws_support",
            "servicenow",
        }

    def test_server_names_match_agentcore(self, _mock_import):
        cfg = get_agent_config()
        assert cfg["failover"]["server_name"] == "makita-postgresql-failover-mcp"
        assert cfg["precheck"]["server_name"] == "makita-postgresql-precheck-mcp"
        assert cfg["postcheck"]["server_name"] == "makita-postgresql-postcheck-mcp"
        assert cfg["aws_support"]["server_name"] == "makita-aws-support-stub"
        assert cfg["servicenow"]["server_name"] == "makita-servicenow-stub"

    def test_failover_tools(self, _mock_import):
        tools = get_agent_config()["failover"]["tools"]
        assert set(tools.keys()) == {"execute_failover", "health_check"}
        assert callable(tools["execute_failover"])
        assert callable(tools["health_check"])

    def test_precheck_tools(self, _mock_import):
        tools = get_agent_config()["precheck"]["tools"]
        assert set(tools.keys()) == {
            "verify_replication_health",
            "verify_primary_status",
            "verify_replica_readiness",
        }
        for fn in tools.values():
            assert callable(fn)

    def test_postcheck_tools(self, _mock_import):
        tools = get_agent_config()["postcheck"]["tools"]
        assert set(tools.keys()) == {
            "verify_new_primary_health",
            "verify_endpoints",
            "verify_replication_established",
        }
        for fn in tools.values():
            assert callable(fn)

    def test_aws_support_tools(self, _mock_import):
        tools = get_agent_config()["aws_support"]["tools"]
        assert set(tools.keys()) == {"create_support_case", "update_support_case"}
        for fn in tools.values():
            assert callable(fn)

    def test_servicenow_tools(self, _mock_import):
        tools = get_agent_config()["servicenow"]["tools"]
        assert set(tools.keys()) == {"create_ticket", "update_ticket"}
        for fn in tools.values():
            assert callable(fn)

    def test_tools_are_invocable(self, _mock_import):
        """Each tool function can be called and returns a dict."""
        cfg = get_agent_config()
        result = cfg["failover"]["tools"]["execute_failover"]()
        assert isinstance(result, dict)
        result = cfg["aws_support"]["tools"]["create_support_case"]()
        assert isinstance(result, dict)

    def test_invoke_tool_dispatches_correctly(self, _mock_import):
        """invoke_tool routes to the correct server and tool."""
        result = invoke_tool("failover", "execute_failover")
        assert result == {"success": True}

        result = invoke_tool("precheck", "verify_replication_health")
        assert result == {"passed": True}

        result = invoke_tool("aws_support", "create_support_case")
        assert result == {"case_id": "c1"}

        result = invoke_tool("servicenow", "create_ticket")
        assert result == {"ticket_id": "t1"}

    def test_invoke_tool_raises_on_unknown_server(self, _mock_import):
        with pytest.raises(KeyError):
            invoke_tool("nonexistent", "some_tool")

    def test_invoke_tool_raises_on_unknown_tool(self, _mock_import):
        with pytest.raises(KeyError):
            invoke_tool("failover", "nonexistent_tool")
