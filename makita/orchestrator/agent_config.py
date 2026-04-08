"""MAKITA DevOps Agent Connection Configuration.

Defines the DevOps Agent's connection to all five MCP servers:
  - Failover MCP Server
  - Pre-Check MCP Server
  - Post-Check MCP Server
  - AWS Support Stub Server
  - ServiceNow Stub Server

Each server entry maps a logical name to its AgentCore server name and
the tool functions it exposes.  Tool functions are loaded via importlib
from the hyphenated ``mcp-servers`` package directories (workload servers
live under ``mcp-servers/workloads/``).

Requirements: 8.1, 8.2, 8.3, 11.7, 12.7, 18.9, 19.9
"""

from __future__ import annotations

import importlib
from typing import Any


# ---------------------------------------------------------------------------
# Module loaders — one per MCP server
# ---------------------------------------------------------------------------


def _load_failover_tools() -> dict[str, Any]:
    mod = importlib.import_module("mcp-servers.workloads.postgresql.failover.server")
    return {
        "execute_failover": mod.execute_failover,
        "health_check": mod.health_check,
    }


def _load_precheck_tools() -> dict[str, Any]:
    mod = importlib.import_module("mcp-servers.workloads.postgresql.precheck.server")
    return {
        "verify_replication_health": mod.verify_replication_health,
        "verify_primary_status": mod.verify_primary_status,
        "verify_replica_readiness": mod.verify_replica_readiness,
    }


def _load_postcheck_tools() -> dict[str, Any]:
    mod = importlib.import_module("mcp-servers.workloads.postgresql.postcheck.server")
    return {
        "verify_new_primary_health": mod.verify_new_primary_health,
        "verify_endpoints": mod.verify_endpoints,
        "verify_replication_established": mod.verify_replication_established,
    }


def _load_aws_support_tools() -> dict[str, Any]:
    mod = importlib.import_module("mcp-servers.aws-support-stub.server")
    return {
        "create_support_case": mod.create_support_case,
        "update_support_case": mod.update_support_case,
    }


def _load_servicenow_tools() -> dict[str, Any]:
    mod = importlib.import_module("mcp-servers.servicenow-stub.server")
    return {
        "create_ticket": mod.create_ticket,
        "update_ticket": mod.update_ticket,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_agent_config() -> dict[str, dict[str, Any]]:
    """Return the full DevOps Agent connection configuration.

    The returned dict maps each logical server key to its AgentCore
    ``server_name`` and a ``tools`` dict of callable tool functions.
    """
    return {
        "failover": {
            "server_name": "makita-postgresql-failover-mcp",
            "tools": _load_failover_tools(),
        },
        "precheck": {
            "server_name": "makita-postgresql-precheck-mcp",
            "tools": _load_precheck_tools(),
        },
        "postcheck": {
            "server_name": "makita-postgresql-postcheck-mcp",
            "tools": _load_postcheck_tools(),
        },
        "aws_support": {
            "server_name": "makita-aws-support-stub",
            "tools": _load_aws_support_tools(),
        },
        "servicenow": {
            "server_name": "makita-servicenow-stub",
            "tools": _load_servicenow_tools(),
        },
    }


def invoke_tool(server_key: str, tool_name: str, **kwargs: Any) -> Any:
    """Invoke a tool on a specific MCP server by logical key and tool name.

    This is the primary entry point for DevOps Agent to call any tool
    across all connected MCP servers.

    Args:
        server_key: Logical server key (e.g. "failover", "precheck").
        tool_name: Name of the tool to invoke (e.g. "execute_failover").
        **kwargs: Arguments forwarded to the tool function.

    Returns:
        The tool result dict.

    Raises:
        KeyError: If the server_key or tool_name is not found.
    """
    config = get_agent_config()
    server = config[server_key]
    tool_fn = server["tools"][tool_name]
    return tool_fn(**kwargs)
