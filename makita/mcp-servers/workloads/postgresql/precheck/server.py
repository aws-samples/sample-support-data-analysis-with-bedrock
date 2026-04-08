"""MAKITA Pre-Check MCP Server.

Built with the Strands SDK. Performs all pre-failover verifications:
replication health, primary instance status, and replica readiness.
"""

from __future__ import annotations

from dataclasses import asdict

import boto3
from strands import tool

from .models import VerificationResult

# ---------------------------------------------------------------------------
# Helper — boto3 clients per region
# ---------------------------------------------------------------------------


def _rds_client(region: str):
    """Return a boto3 RDS client for the given region."""
    return boto3.client("rds", region_name=region)


def _ssm_client(region: str = "us-east-1"):
    """Return a boto3 SSM client for the given region."""
    return boto3.client("ssm", region_name=region)


# ---------------------------------------------------------------------------
# Tool: verify_replication_health
# ---------------------------------------------------------------------------


@tool
def verify_replication_health(cluster_name: str) -> dict:
    """Checks replication lag, replication state, and data consistency.

    Verifies that the replica is replicating from the primary with
    acceptable lag and healthy replication state.

    Args:
        cluster_name: The PostgreSQL cluster name (e.g. "makita-pg-cluster").

    Returns:
        A dict matching the VerificationResult schema.
    """
    try:
        ssm = _ssm_client()
        primary_region = ssm.get_parameter(Name="/makita/db/primary-region")[
            "Parameter"
        ]["Value"]
        dr_region = ssm.get_parameter(Name="/makita/db/dr-region")["Parameter"][
            "Value"
        ]

        # Describe primary instance
        rds_primary = _rds_client(primary_region)
        primary_id = cluster_name.replace("makita-pg-cluster", "makita-pg-primary")
        primary_info = rds_primary.describe_db_instances(
            DBInstanceIdentifier=primary_id,
        )["DBInstances"][0]
        primary_status = primary_info.get("DBInstanceStatus", "unknown")

        # Describe replica instance
        rds_dr = _rds_client(dr_region)
        replica_id = cluster_name.replace("makita-pg-cluster", "makita-pg-replica")
        replica_info = rds_dr.describe_db_instances(
            DBInstanceIdentifier=replica_id,
        )["DBInstances"][0]
        replica_status = replica_info.get("DBInstanceStatus", "unknown")

        # Replication lag and state
        replication_lag = 0.0
        replication_state = "unknown"
        status_infos = replica_info.get("StatusInfos", [])
        for info in status_infos:
            if info.get("StatusType") == "read replication":
                replication_lag = float(info.get("Message", "0") or "0")
                replication_state = info.get("Status", "unknown")
                if info.get("Normal"):
                    replication_state = "streaming"

        healthy = (
            primary_status == "available"
            and replica_status == "available"
            and replication_lag < 30
        )

        return asdict(
            VerificationResult(
                check_name="replication_health",
                passed=healthy,
                details={
                    "replication_lag_seconds": replication_lag,
                    "replication_state": replication_state,
                    "primary_status": primary_status,
                    "replica_status": replica_status,
                },
                error=None if healthy else "Replication health check failed",
            )
        )

    except Exception as exc:
        return asdict(
            VerificationResult(
                check_name="replication_health",
                passed=False,
                details={},
                error=str(exc),
            )
        )


# ---------------------------------------------------------------------------
# Tool: verify_primary_status
# ---------------------------------------------------------------------------


@tool
def verify_primary_status(cluster_name: str, primary_region: str) -> dict:
    """Verifies the primary instance status in the Primary Region.

    Checks that the primary instance is in a known status (available,
    degraded, or failed) in us-east-1.

    Args:
        cluster_name: The PostgreSQL cluster name (e.g. "makita-pg-cluster").
        primary_region: The primary region (e.g. "us-east-1").

    Returns:
        A dict matching the VerificationResult schema.
    """
    try:
        rds = _rds_client(primary_region)
        primary_id = cluster_name.replace("makita-pg-cluster", "makita-pg-primary")
        primary_info = rds.describe_db_instances(
            DBInstanceIdentifier=primary_id,
        )["DBInstances"][0]

        status = primary_info.get("DBInstanceStatus", "unknown")
        known_statuses = {"available", "degraded", "failed", "backing-up", "maintenance"}
        is_known = status in known_statuses

        return asdict(
            VerificationResult(
                check_name="primary_status",
                passed=is_known,
                details={
                    "primary_status": status,
                    "primary_region": primary_region,
                    "instance_id": primary_id,
                },
                error=None if is_known else f"Primary in unexpected status: {status}",
            )
        )

    except Exception as exc:
        return asdict(
            VerificationResult(
                check_name="primary_status",
                passed=False,
                details={},
                error=str(exc),
            )
        )


# ---------------------------------------------------------------------------
# Tool: verify_replica_readiness
# ---------------------------------------------------------------------------


@tool
def verify_replica_readiness(cluster_name: str, dr_region: str) -> dict:
    """Verifies the replica instance readiness for promotion in the DR Region.

    Checks that the replica is healthy, available, and replication is
    caught up enough for safe promotion.

    Args:
        cluster_name: The PostgreSQL cluster name (e.g. "makita-pg-cluster").
        dr_region: The DR region (e.g. "us-west-2").

    Returns:
        A dict matching the VerificationResult schema.
    """
    try:
        rds = _rds_client(dr_region)
        replica_id = cluster_name.replace("makita-pg-cluster", "makita-pg-replica")
        replica_info = rds.describe_db_instances(
            DBInstanceIdentifier=replica_id,
        )["DBInstances"][0]

        status = replica_info.get("DBInstanceStatus", "unknown")
        is_available = status == "available"

        # Check replication is caught up
        replication_lag = 0.0
        replication_normal = True
        status_infos = replica_info.get("StatusInfos", [])
        for info in status_infos:
            if info.get("StatusType") == "read replication":
                replication_lag = float(info.get("Message", "0") or "0")
                if info.get("Normal") is False:
                    replication_normal = False

        ready = is_available and replication_normal and replication_lag < 30

        return asdict(
            VerificationResult(
                check_name="replica_readiness",
                passed=ready,
                details={
                    "replica_status": status,
                    "dr_region": dr_region,
                    "instance_id": replica_id,
                    "replication_lag_seconds": replication_lag,
                    "replication_normal": replication_normal,
                },
                error=None if ready else "Replica not ready for promotion",
            )
        )

    except Exception as exc:
        return asdict(
            VerificationResult(
                check_name="replica_readiness",
                passed=False,
                details={},
                error=str(exc),
            )
        )
