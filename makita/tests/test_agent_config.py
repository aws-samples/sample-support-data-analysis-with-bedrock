"""Tests for orchestrator.agent_config — DevOps Agent connection configuration."""

from __future__ import annotations

from unittest.mock import patch
import types

import pytest

from orchestrator.agent_config import get_agent_config, invoke_tool


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


_FAKE_MODULES = {
    "mcp-servers.workloads.postgresql.failover.server": _make_failover_module(),
    "mcp-servers.workloads.postgresql.precheck.server": _make_precheck_module(),
    "mcp-servers.workloads.postgresql.postcheck.server": _make_postcheck_module(),
}


def _fake_import(name):
    if name in _FAKE_MODULES:
        return _FAKE_MODULES[name]
    raise ImportError(name)


@patch("orchestrator.agent_config.importlib.import_module", side_effect=_fake_import)
class TestGetAgentConfig:
    """Validates get_agent_config returns the correct structure."""

    def test_returns_all_three_servers(self, _mock_import):
        cfg = get_agent_config()
        assert set(cfg.keys()) == {"failover", "precheck", "postcheck"}

    def test_server_names_match_agentcore(self, _mock_import):
        cfg = get_agent_config()
        assert cfg["failover"]["server_name"] == "makita-postgresql-failover-mcp"
        assert cfg["precheck"]["server_name"] == "makita-postgresql-precheck-mcp"
        assert cfg["postcheck"]["server_name"] == "makita-postgresql-postcheck-mcp"

    def test_failover_tools(self, _mock_import):
        tools = get_agent_config()["failover"]["tools"]
        assert set(tools.keys()) == {"execute_failover", "health_check"}
        assert callable(tools["execute_failover"])

    def test_precheck_tools(self, _mock_import):
        tools = get_agent_config()["precheck"]["tools"]
        assert set(tools.keys()) == {
            "verify_replication_health",
            "verify_primary_status",
            "verify_replica_readiness",
        }

    def test_postcheck_tools(self, _mock_import):
        tools = get_agent_config()["postcheck"]["tools"]
        assert set(tools.keys()) == {
            "verify_new_primary_health",
            "verify_endpoints",
            "verify_replication_established",
        }

    def test_tools_are_invocable(self, _mock_import):
        cfg = get_agent_config()
        result = cfg["failover"]["tools"]["execute_failover"]()
        assert isinstance(result, dict)

    def test_invoke_tool_dispatches_correctly(self, _mock_import):
        assert invoke_tool("failover", "execute_failover") == {"success": True}
        assert invoke_tool("precheck", "verify_replication_health") == {"passed": True}

    def test_invoke_tool_raises_on_unknown_server(self, _mock_import):
        with pytest.raises(KeyError):
            invoke_tool("nonexistent", "some_tool")

    def test_invoke_tool_raises_on_unknown_tool(self, _mock_import):
        with pytest.raises(KeyError):
            invoke_tool("failover", "nonexistent_tool")
