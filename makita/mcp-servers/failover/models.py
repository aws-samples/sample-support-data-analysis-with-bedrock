"""Data models for the MAKITA Failover MCP Server."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FailoverResult:
    """Result of a failover execution operation.

    Returned by the execute_failover tool with details about the
    failover outcome including new/previous endpoints and duration.
    """

    success: bool
    new_primary_endpoint: str | None = None
    previous_primary_endpoint: str | None = None
    failover_duration_seconds: float | None = None
    endpoints_updated: bool = False
    error: str | None = None


@dataclass
class HealthCheckResult:
    """Result of a health check on the PostgreSQL cluster.

    Returned by the health_check tool with primary/replica status
    and replication lag information.
    """

    cluster_name: str
    primary_status: str
    replica_status: str
    replication_lag_seconds: float
    replication_healthy: bool


@dataclass
class FailoverState:
    """Internal state tracking for an in-progress failover operation.

    Tracks the lifecycle of a failover from initiation through completion,
    including timing and status transitions.
    """

    cluster_name: str
    primary_region: str
    dr_region: str
    previous_primary_endpoint: str
    new_primary_endpoint: str
    started_at: str  # ISO 8601
    completed_at: str | None = None
    duration_seconds: float | None = None
    status: str = "initiated"
    # Valid statuses: "initiated", "replication_verified", "promotion_started",
    #                 "promotion_completed", "endpoints_updated", "complete", "failed"
    error: str | None = None
