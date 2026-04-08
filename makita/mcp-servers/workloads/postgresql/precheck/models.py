"""Data models for the MAKITA Pre-Check MCP Server."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of a pre-check verification operation.

    Returned by each pre-check tool with the check name, pass/fail status,
    details about the verification, and any error information.
    """

    check_name: str
    passed: bool
    details: dict = field(default_factory=dict)
    error: str | None = None
