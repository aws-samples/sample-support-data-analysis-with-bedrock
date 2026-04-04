"""MAKITA Ticketing Integration.

Creates and updates AWS Support cases and ServiceNow tickets throughout
the failover process.  Tool functions are loaded from the stub MCP servers
by default but can be overridden via dependency injection for testing.

Requirements: 13.1–13.17
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TicketUpdateContext:
    """Contextual information included in every ticket update.

    Satisfies Requirement 13.15 (resource names, parameter paths, AgentCore
    resources), 13.16 (regions), and 13.17 (phase, MCP server, endpoints,
    replication status, IAM role, error codes/messages).
    """

    phase: str  # "pre-check", "failover", "post-check"
    status: str  # e.g. "failover initiated", "replication verified"
    resource_names: list[str] = field(default_factory=list)
    parameter_paths: list[str] = field(default_factory=list)
    agentcore_resources: list[str] = field(default_factory=list)
    primary_region: str = "us-east-1"
    dr_region: str = "us-west-2"
    endpoints: dict[str, str] = field(default_factory=dict)
    replication_status: str | None = None
    iam_role: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    mcp_server: str = ""


# ---------------------------------------------------------------------------
# Default tool loaders
# ---------------------------------------------------------------------------


def _load_support_tools() -> dict:
    mod = importlib.import_module("mcp-servers.aws-support-stub.server")
    return {
        "create_support_case": mod.create_support_case,
        "update_support_case": mod.update_support_case,
    }


def _load_servicenow_tools() -> dict:
    mod = importlib.import_module("mcp-servers.servicenow-stub.server")
    return {
        "create_ticket": mod.create_ticket,
        "update_ticket": mod.update_ticket,
    }


# ---------------------------------------------------------------------------
# Description builder
# ---------------------------------------------------------------------------


def build_update_description(context: TicketUpdateContext) -> str:
    """Build a human-readable description string from a TicketUpdateContext.

    The description includes all contextual fields so that every ticket
    update carries full operational context (Req 13.15–13.17).
    """
    lines: list[str] = [
        f"Phase: {context.phase}",
        f"Status: {context.status}",
        f"Primary Region: {context.primary_region}",
        f"DR Region: {context.dr_region}",
    ]

    if context.mcp_server:
        lines.append(f"MCP Server: {context.mcp_server}")

    if context.resource_names:
        lines.append(f"Resources: {', '.join(context.resource_names)}")

    if context.parameter_paths:
        lines.append(f"Parameters: {', '.join(context.parameter_paths)}")

    if context.agentcore_resources:
        lines.append(f"AgentCore Resources: {', '.join(context.agentcore_resources)}")

    if context.endpoints:
        ep_parts = [f"{k}={v}" for k, v in context.endpoints.items()]
        lines.append(f"Endpoints: {', '.join(ep_parts)}")

    if context.replication_status is not None:
        lines.append(f"Replication Status: {context.replication_status}")

    if context.iam_role is not None:
        lines.append(f"IAM Role: {context.iam_role}")

    if context.error_code is not None:
        lines.append(f"Error Code: {context.error_code}")

    if context.error_message is not None:
        lines.append(f"Error Message: {context.error_message}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ticket creation
# ---------------------------------------------------------------------------


def create_tickets(
    subject: str,
    description: str,
    severity: str = "critical",
    priority: str = "1-Critical",
    *,
    support_tools: dict | None = None,
    servicenow_tools: dict | None = None,
) -> tuple[str, str]:
    """Create an AWS Support case and a ServiceNow ticket.

    Returns (case_id, ticket_id).

    Satisfies Requirements 13.1 and 13.2.
    """
    _support = support_tools if support_tools is not None else _load_support_tools()
    _snow = servicenow_tools if servicenow_tools is not None else _load_servicenow_tools()

    case_result = _support["create_support_case"](
        subject=subject,
        description=description,
        severity=severity,
    )
    case_id: str = case_result["case_id"]

    ticket_result = _snow["create_ticket"](
        short_description=subject,
        description=description,
        priority=priority,
        category="Disaster Recovery",
    )
    ticket_id: str = ticket_result["ticket_id"]

    return case_id, ticket_id


# ---------------------------------------------------------------------------
# Ticket update
# ---------------------------------------------------------------------------


def update_tickets(
    case_id: str,
    ticket_id: str,
    context: TicketUpdateContext,
    *,
    support_tools: dict | None = None,
    servicenow_tools: dict | None = None,
) -> None:
    """Update both the AWS Support case and ServiceNow ticket.

    Satisfies Requirements 13.3–13.14 (phase transitions, failures,
    restarts, corrective actions) and 13.15–13.17 (contextual info).
    """
    _support = support_tools if support_tools is not None else _load_support_tools()
    _snow = servicenow_tools if servicenow_tools is not None else _load_servicenow_tools()

    desc = build_update_description(context)

    _support["update_support_case"](
        case_id=case_id,
        status=context.status,
        update_description=desc,
    )

    _snow["update_ticket"](
        ticket_id=ticket_id,
        status=context.status,
        work_notes=desc,
    )
