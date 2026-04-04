"""Data models for the MAKITA Post-Check MCP Server."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of a post-check verification operation.

    Returned by each post-check tool with the check name, pass/fail status,
    details about the verification, and any error information.
    """

    check_name: str
    passed: bool
    details: dict = field(default_factory=dict)
    error: str | None = None
