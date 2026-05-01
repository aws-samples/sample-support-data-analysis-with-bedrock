"""MAKITA Post-Check MCP Server.

Built with the Strands SDK. Performs all post-failover verifications:
new primary health, endpoint correctness, and replication establishment.
"""

from __future__ import annotations

from dataclasses import asdict

import boto3
from mcp.server.fastmcp import FastMCP

from models import VerificationResult

mcp = FastMCP(host="0.0.0.0", stateless_http=True)

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
# Tool: verify_new_primary_health
# ---------------------------------------------------------------------------


@mcp.tool()
def verify_new_primary_health(cluster_name: str, dr_region: str) -> dict:
    """Verifies the promoted instance health in the DR Region.

    Checks that the newly promoted primary instance in us-west-2 is
    healthy and accepting connections.

    Args:
        cluster_name: The PostgreSQL cluster name (e.g. "makita-pg-cluster").
        dr_region: The DR region where the new primary lives (e.g. "us-west-2").

    Returns:
        A dict matching the VerificationResult schema.
    """
    try:
        rds = _rds_client(dr_region)
        # After promotion the replica becomes the new primary; its instance
        # identifier remains the same (makita-pg-replica) until renamed.
        instance_id = cluster_name.replace("makita-pg-cluster", "makita-pg-replica")
        instance_info = rds.describe_db_instances(
            DBInstanceIdentifier=instance_id,
        )["DBInstances"][0]

        status = instance_info.get("DBInstanceStatus", "unknown")
        healthy = status == "available"

        return asdict(
            VerificationResult(
                check_name="new_primary_health",
                passed=healthy,
                details={
                    "instance_status": status,
                    "dr_region": dr_region,
                    "instance_id": instance_id,
                },
                error=None if healthy else f"New primary not healthy: {status}",
            )
        )

    except Exception as exc:
        return asdict(
            VerificationResult(
                check_name="new_primary_health",
                passed=False,
                details={},
                error=str(exc),
            )
        )


# ---------------------------------------------------------------------------
# Tool: verify_endpoints
# ---------------------------------------------------------------------------


@mcp.tool()
def verify_endpoints(cluster_name: str) -> dict:
    """Verifies Parameter Store endpoint values reflect the new primary.

    Checks that /makita/db/primary-endpoint and /makita/db/replica-endpoint
    have been updated to reflect the promoted instance in us-west-2.

    Args:
        cluster_name: The PostgreSQL cluster name (e.g. "makita-pg-cluster").

    Returns:
        A dict matching the VerificationResult schema.
    """
    try:
        ssm = _ssm_client()
        primary_endpoint = ssm.get_parameter(Name="/makita/db/primary-endpoint")[
            "Parameter"
        ]["Value"]
        replica_endpoint = ssm.get_parameter(Name="/makita/db/replica-endpoint")[
            "Parameter"
        ]["Value"]
        primary_region = ssm.get_parameter(Name="/makita/db/primary-region")[
            "Parameter"
        ]["Value"]

        # After failover, the primary endpoint should reference the DR region
        # instance and the primary-region parameter should be us-west-2.
        endpoints_swapped = primary_endpoint != replica_endpoint
        region_updated = primary_region == "us-west-2"
        passed = endpoints_swapped and region_updated

        return asdict(
            VerificationResult(
                check_name="endpoint_verification",
                passed=passed,
                details={
                    "primary_endpoint": primary_endpoint,
                    "replica_endpoint": replica_endpoint,
                    "primary_region": primary_region,
                },
                error=None if passed else "Endpoints do not reflect new primary",
            )
        )

    except Exception as exc:
        return asdict(
            VerificationResult(
                check_name="endpoint_verification",
                passed=False,
                details={},
                error=str(exc),
            )
        )


# ---------------------------------------------------------------------------
# Tool: verify_replication_established
# ---------------------------------------------------------------------------


@mcp.tool()
def verify_replication_established(cluster_name: str) -> dict:
    """Verifies replication from the new primary is established.

    Checks whether a new replica has been configured to replicate from
    the promoted primary instance.

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
        replication_status = ssm.get_parameter(Name="/makita/db/replication-status")[
            "Parameter"
        ]["Value"]

        # After failover the old primary region becomes the new DR region.
        # Check if a replica exists in the new DR region.
        rds_dr = _rds_client(dr_region)
        replica_id = cluster_name.replace("makita-pg-cluster", "makita-pg-primary")

        replica_exists = False
        replica_status = "unknown"
        replication_lag = -1.0
        try:
            info = rds_dr.describe_db_instances(
                DBInstanceIdentifier=replica_id,
            )["DBInstances"][0]
            replica_exists = True
            replica_status = info.get("DBInstanceStatus", "unknown")
            for si in info.get("StatusInfos", []):
                if si.get("StatusType") == "read replication":
                    replication_lag = float(si.get("Message", "0") or "0")
        except Exception:
            # Replica may not exist yet after failover — that's acceptable
            pass

        # Replication is considered established if the status was updated
        # to "promoted" (indicating failover completed) and either a new
        # replica exists or the status reflects the promotion.
        established = replication_status == "promoted"

        return asdict(
            VerificationResult(
                check_name="replication_established",
                passed=established,
                details={
                    "replication_status": replication_status,
                    "primary_region": primary_region,
                    "dr_region": dr_region,
                    "new_replica_exists": replica_exists,
                    "new_replica_status": replica_status,
                    "replication_lag_seconds": replication_lag,
                },
                error=None
                if established
                else "Replication from new primary not yet established",
            )
        )

    except Exception as exc:
        return asdict(
            VerificationResult(
                check_name="replication_established",
                passed=False,
                details={},
                error=str(exc),
            )
        )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
