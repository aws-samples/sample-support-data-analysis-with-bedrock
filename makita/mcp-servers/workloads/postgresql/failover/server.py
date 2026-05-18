"""MAKITA Failover MCP Server.

Built with the Strands SDK. Executes the core failover operation:
promotes the DR replica to primary, updates Parameter Store endpoints,
and provides health check capabilities for the PostgreSQL cluster.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, timezone

import boto3
from mcp.server.fastmcp import FastMCP

from models import FailoverResult, FailoverState, HealthCheckResult

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

ALLOWED_REGIONS = {"us-east-1", "us-west-2"}
ALLOWED_CLUSTERS = {"makita-pg-cluster"}

# ---------------------------------------------------------------------------
# Runtime configuration — loaded from Parameter Store on first use
# ---------------------------------------------------------------------------

_ssm = None


def _get_ssm():
    """Lazily create the SSM client."""
    global _ssm
    if _ssm is None:
        _ssm = boto3.client("ssm", region_name="us-east-1")
    return _ssm


def _get_parameter(name: str) -> str:
    """Retrieve a single parameter value from Parameter Store."""
    resp = _get_ssm().get_parameter(Name=name)
    return resp["Parameter"]["Value"]


def load_config() -> dict[str, str]:
    """Read MAKITA runtime configuration from Parameter Store."""
    param_keys = [
        "/makita/db/primary-endpoint",
        "/makita/db/replica-endpoint",
        "/makita/db/primary-region",
        "/makita/db/dr-region",
        "/makita/db/cluster-name",
        "/makita/db/replication-status",
        "/makita/db/port",
    ]
    config: dict[str, str] = {}
    resp = _get_ssm().get_parameters(Names=param_keys)
    for p in resp["Parameters"]:
        config[p["Name"]] = p["Value"]
    return config


# ---------------------------------------------------------------------------
# Helper — RDS clients per region
# ---------------------------------------------------------------------------


def _rds_client(region: str):
    """Return a boto3 RDS client for the given region."""
    return boto3.client("rds", region_name=region)


def _ssm_client(region: str = "us-east-1"):
    """Return a boto3 SSM client for the given region."""
    return boto3.client("ssm", region_name=region)


# ---------------------------------------------------------------------------
# Tool: execute_failover
# ---------------------------------------------------------------------------


@mcp.tool()
def execute_failover(
    primary_region: str,
    dr_region: str,
    cluster_name: str,
) -> dict:
    """Promotes the DR replica to primary.

    Verifies replication status first, promotes the replica, updates
    Parameter Store endpoints, and returns a summary with new primary
    endpoint, previous primary endpoint, and failover duration.

    Args:
        primary_region: The current primary region (e.g. "us-east-1").
        dr_region: The disaster-recovery region (e.g. "us-west-2").
        cluster_name: The PostgreSQL cluster name (e.g. "makita-pg-cluster").

    Returns:
        A dict matching the FailoverResult schema.
    """
    if primary_region not in ALLOWED_REGIONS:
        return asdict(FailoverResult(success=False, error=f"Invalid primary_region: {primary_region}"))
    if dr_region not in ALLOWED_REGIONS:
        return asdict(FailoverResult(success=False, error=f"Invalid dr_region: {dr_region}"))
    if cluster_name not in ALLOWED_CLUSTERS:
        return asdict(FailoverResult(success=False, error=f"Invalid cluster_name: {cluster_name}"))

    start = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    state = FailoverState(
        cluster_name=cluster_name,
        primary_region=primary_region,
        dr_region=dr_region,
        previous_primary_endpoint="",
        new_primary_endpoint="",
        started_at=started_at,
    )

    try:
        # --- 1. Read current endpoints from Parameter Store ----------------
        ssm = _ssm_client(primary_region)
        primary_endpoint = ssm.get_parameter(Name="/makita/db/primary-endpoint")["Parameter"]["Value"]
        replica_endpoint = ssm.get_parameter(Name="/makita/db/replica-endpoint")["Parameter"]["Value"]

        state.previous_primary_endpoint = primary_endpoint
        state.new_primary_endpoint = replica_endpoint

        # --- 2. Verify replication status ----------------------------------
        rds_dr = _rds_client(dr_region)
        replica_id = f"{cluster_name.replace('makita-pg-cluster', 'makita-pg-replica')}"
        replica_info = rds_dr.describe_db_instances(
            DBInstanceIdentifier=replica_id,
        )["DBInstances"][0]

        rep_status = replica_info.get("StatusInfos", [])
        for info in rep_status:
            if info.get("StatusType") == "read replication" and info.get("Normal") is False:
                state.status = "failed"
                state.error = (
                    f"Replication is not healthy: {info.get('Status', 'unknown')}"
                )
                return asdict(
                    FailoverResult(
                        success=False,
                        error=state.error,
                    )
                )

        state.status = "replication_verified"

        # --- 3. Promote replica to primary ---------------------------------
        state.status = "promotion_started"
        rds_dr.promote_read_replica(DBInstanceIdentifier=replica_id)
        state.status = "promotion_completed"

        # --- 4. Update Parameter Store endpoints ---------------------------
        ssm.put_parameter(
            Name="/makita/db/primary-endpoint",
            Value=replica_endpoint,
            Overwrite=True,
        )
        ssm.put_parameter(
            Name="/makita/db/replica-endpoint",
            Value=primary_endpoint,
            Overwrite=True,
        )
        ssm.put_parameter(
            Name="/makita/db/primary-region",
            Value=dr_region,
            Overwrite=True,
        )
        ssm.put_parameter(
            Name="/makita/db/dr-region",
            Value=primary_region,
            Overwrite=True,
        )
        ssm.put_parameter(
            Name="/makita/db/replication-status",
            Value="promoted",
            Overwrite=True,
        )
        state.status = "endpoints_updated"

        # --- 5. Build result -----------------------------------------------
        elapsed = time.monotonic() - start
        state.completed_at = datetime.now(timezone.utc).isoformat()
        state.duration_seconds = elapsed
        state.status = "complete"

        return asdict(
            FailoverResult(
                success=True,
                new_primary_endpoint=replica_endpoint,
                previous_primary_endpoint=primary_endpoint,
                failover_duration_seconds=round(elapsed, 2),
                endpoints_updated=True,
                error=None,
            )
        )

    except Exception as exc:
        state.status = "failed"
        state.error = str(exc)
        return asdict(
            FailoverResult(
                success=False,
                error=str(exc),
            )
        )


# ---------------------------------------------------------------------------
# Tool: health_check
# ---------------------------------------------------------------------------


@mcp.tool()
def health_check(cluster_name: str) -> dict:
    """Returns the current health status of the PostgreSQL cluster.

    Checks primary status, replica status, and replication lag.

    Args:
        cluster_name: The PostgreSQL cluster name (e.g. "makita-pg-cluster").

    Returns:
        A dict matching the HealthCheckResult schema.
    """
    if cluster_name not in ALLOWED_CLUSTERS:
        return {"cluster_name": cluster_name, "primary_status": "unknown",
                "replica_status": "unknown", "replication_lag_seconds": -1,
                "replication_healthy": False, "error": f"Invalid cluster_name: {cluster_name}"}

    try:
        # Read regions from Parameter Store
        ssm = _ssm_client()
        primary_region = ssm.get_parameter(Name="/makita/db/primary-region")["Parameter"]["Value"]
        dr_region = ssm.get_parameter(Name="/makita/db/dr-region")["Parameter"]["Value"]

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

        # Replication lag (seconds) — available on read replicas
        replication_lag = 0.0
        status_infos = replica_info.get("StatusInfos", [])
        for info in status_infos:
            if info.get("StatusType") == "read replication":
                replication_lag = float(info.get("Message", "0") or "0")

        replication_healthy = (
            primary_status == "available"
            and replica_status == "available"
            and replication_lag < 30
        )

        return asdict(
            HealthCheckResult(
                cluster_name=cluster_name,
                primary_status=primary_status,
                replica_status=replica_status,
                replication_lag_seconds=replication_lag,
                replication_healthy=replication_healthy,
            )
        )

    except Exception as exc:
        return {
            "cluster_name": cluster_name,
            "primary_status": "unknown",
            "replica_status": "unknown",
            "replication_lag_seconds": -1,
            "replication_healthy": False,
            "error": str(exc),
        }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
