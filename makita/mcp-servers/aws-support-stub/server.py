"""MAKITA AWS Support Stub MCP Server.

Built with the Strands SDK. Simulates the AWS Support API by storing
support cases in-memory. Allows DevOps Agent to create and update
AWS Support cases during disaster recovery operations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from strands import tool

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CaseUpdate:
    """A single status update applied to a support case."""

    status: str
    description: str
    updated_at: str  # ISO 8601


@dataclass
class SupportCase:
    """An in-memory representation of an AWS Support case."""

    case_id: str  # "makita-case-{date}-{seq}"
    subject: str
    description: str
    severity: str
    status: str
    created_at: str  # ISO 8601
    updates: list[CaseUpdate] = field(default_factory=list)


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

support_cases: dict[str, SupportCase] = {}
_case_seq: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _next_case_id() -> str:
    """Generate the next unique case ID in the format makita-case-{date}-{seq}."""
    global _case_seq
    _case_seq += 1
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"makita-case-{date_str}-{_case_seq:03d}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Tool: create_support_case
# ---------------------------------------------------------------------------


@tool
def create_support_case(
    subject: str,
    description: str,
    severity: str,
) -> dict:
    """Creates a new AWS Support case.

    Returns a unique case ID, the subject, initial status, and creation
    timestamp.

    Args:
        subject: Brief summary of the support case.
        description: Detailed description of the issue.
        severity: Case severity — "critical", "high", "normal", or "low".

    Returns:
        A dict matching the CreateCaseResult schema.
    """
    case_id = _next_case_id()
    created_at = _now_iso()

    case = SupportCase(
        case_id=case_id,
        subject=subject,
        description=description,
        severity=severity,
        status="opened",
        created_at=created_at,
    )
    support_cases[case_id] = case

    return {
        "case_id": case_id,
        "subject": subject,
        "status": "opened",
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Tool: update_support_case
# ---------------------------------------------------------------------------


@tool
def update_support_case(
    case_id: str,
    status: str,
    update_description: str,
) -> dict:
    """Updates an existing AWS Support case with a new status.

    Returns the case ID, updated status, and timestamp. If the case does
    not exist, returns a structured error response.

    Args:
        case_id: The unique identifier of the support case to update.
        status: The new status to set on the case.
        update_description: A description of the update being applied.

    Returns:
        A dict matching the UpdateCaseResult schema, or an error dict
        if the case is not found.
    """
    if case_id not in support_cases:
        return {
            "error": {
                "code": "CASE_NOT_FOUND",
                "message": f"AWS Support case {case_id} not found",
            }
        }

    case = support_cases[case_id]
    updated_at = _now_iso()

    case.status = status
    case.updates.append(
        CaseUpdate(
            status=status,
            description=update_description,
            updated_at=updated_at,
        )
    )

    return {
        "case_id": case_id,
        "status": status,
        "updated_at": updated_at,
        "error": None,
    }
