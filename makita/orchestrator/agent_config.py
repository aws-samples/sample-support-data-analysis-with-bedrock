"""MAKITA DevOps Agent Connection Configuration.

Defines the DevOps Agent's connection to the three PostgreSQL MCP servers:
  - Failover MCP Server
  - Pre-Check MCP Server
  - Post-Check MCP Server

Each server entry maps a logical name to its AgentCore server name and
the tool functions it exposes.
"""

from __future__ import annotations

import importlib
from typing import Any


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


def get_agent_config() -> dict[str, dict[str, Any]]:
    """Return the DevOps Agent connection configuration.

    Maps each logical server key to its AgentCore ``server_name``
    and a ``tools`` dict of callable tool functions.
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
    }


def invoke_tool(server_key: str, tool_name: str, **kwargs: Any) -> Any:
    """Invoke a tool on a specific MCP server by logical key and tool name."""
    config = get_agent_config()
    server = config[server_key]
    tool_fn = server["tools"][tool_name]
    return tool_fn(**kwargs)
