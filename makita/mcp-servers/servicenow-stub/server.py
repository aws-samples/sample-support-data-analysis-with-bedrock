"""MAKITA ServiceNow Stub MCP Server.

Simulates the ServiceNow API by storing tickets in-memory.
Runs as a FastMCP server on streamable-http transport for
AgentCore container deployment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(host="0.0.0.0", port=8080, stateless_http=True)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class WorkNote:
    """A single work note applied to a ServiceNow ticket."""

    status: str
    notes: str
    updated_at: str  # ISO 8601


@dataclass
class ServiceNowTicket:
    """An in-memory representation of a ServiceNow ticket."""

    ticket_id: str  # "INC{seq:07d}"
    short_description: str
    description: str
    priority: str
    category: str
    status: str
    created_at: str  # ISO 8601
    work_notes: list[WorkNote] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

tickets: dict[str, ServiceNowTicket] = {}
_ticket_seq: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _next_ticket_id() -> str:
    """Generate the next unique ticket ID in the format INC{seq:07d}."""
    global _ticket_seq
    _ticket_seq += 1
    return f"INC{_ticket_seq:07d}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Tool: create_ticket
# ---------------------------------------------------------------------------


@mcp.tool()
def create_ticket(
    short_description: str,
    description: str,
    priority: str,
    category: str,
) -> dict:
    """Creates a new ServiceNow ticket.

    Returns a unique ticket ID, the short description, initial status,
    and creation timestamp.

    Args:
        short_description: Brief summary of the ticket.
        description: Detailed description of the issue.
        priority: Ticket priority — "1-Critical", "2-High", "3-Medium", or "4-Low".
        category: Ticket category — e.g. "Disaster Recovery".

    Returns:
        A dict matching the CreateTicketResult schema.
    """
    ticket_id = _next_ticket_id()
    created_at = _now_iso()

    ticket = ServiceNowTicket(
        ticket_id=ticket_id,
        short_description=short_description,
        description=description,
        priority=priority,
        category=category,
        status="New",
        created_at=created_at,
    )
    tickets[ticket_id] = ticket

    return {
        "ticket_id": ticket_id,
        "short_description": short_description,
        "status": "New",
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Tool: update_ticket
# ---------------------------------------------------------------------------


@mcp.tool()
def update_ticket(
    ticket_id: str,
    status: str,
    work_notes: str,
) -> dict:
    """Updates an existing ServiceNow ticket with a new status.

    Returns the ticket ID, updated status, and timestamp. If the ticket
    does not exist, returns a structured error response.

    Args:
        ticket_id: The unique identifier of the ticket to update.
        status: The new status to set on the ticket.
        work_notes: Notes describing the update being applied.

    Returns:
        A dict matching the UpdateTicketResult schema, or an error dict
        if the ticket is not found.
    """
    if ticket_id not in tickets:
        return {
            "error": {
                "code": "TICKET_NOT_FOUND",
                "message": f"ServiceNow ticket {ticket_id} not found",
            }
        }

    ticket = tickets[ticket_id]
    updated_at = _now_iso()

    ticket.status = status
    ticket.work_notes.append(
        WorkNote(
            status=status,
            notes=work_notes,
            updated_at=updated_at,
        )
    )

    return {
        "ticket_id": ticket_id,
        "status": status,
        "updated_at": updated_at,
        "error": None,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
