"""Tests for the MAKITA MCP Servers: Failover, Pre-Check, and Post-Check.

Validates Requirements 23.4, 23.5, 23.6 — MCP server functionality including
success paths, failure paths, and exception handling for all tools.

All boto3 calls are mocked via unittest.mock.patch.
The mcp-servers/workload directory uses a hyphen, so we import via importlib and
patch attributes directly on the imported module objects.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import modules with hyphenated package names via importlib.
# We must also mock boto3.client at import time for the failover server
# because it calls boto3.client("ssm") at module level.
# ---------------------------------------------------------------------------

# Pre-check and post-check servers only call boto3 inside helper functions,
# so they can be imported without mocking.  The failover server has a
# module-level  _ssm = boto3.client("ssm", ...)  call, so we mock boto3
# before importing it.

with patch("boto3.client") as _mock_boto:
    _mock_boto.return_value = MagicMock()
    _failover_mod = importlib.import_module("mcp-servers.workloads.postgresql.failover.server")

_precheck_mod = importlib.import_module("mcp-servers.workloads.postgresql.precheck.server")
_postcheck_mod = importlib.import_module("mcp-servers.workloads.postgresql.postcheck.server")


# ============================================================================
# Failover MCP Server Tests (Requirement 23.4)
# ============================================================================


class TestExecuteFailoverSuccess:
    """execute_failover tool — success path."""

    def test_returns_success(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-endpoint": {"Parameter": {"Value": "primary.us-east-1.rds.amazonaws.com"}},
            "/makita/db/replica-endpoint": {"Parameter": {"Value": "replica.us-west-2.rds.amazonaws.com"}},
        }[Name]
        ssm.put_parameter.return_value = {}

        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Normal": True, "Status": "replicating"}
                    ],
                }
            ]
        }
        rds.promote_read_replica.return_value = {}

        with patch.object(_failover_mod, "_ssm_client", return_value=ssm), \
             patch.object(_failover_mod, "_rds_client", return_value=rds):
            result = _failover_mod.execute_failover(
                primary_region="us-east-1",
                dr_region="us-west-2",
                cluster_name="makita-pg-cluster",
            )

        assert result["success"] is True
        assert result["new_primary_endpoint"] == "replica.us-west-2.rds.amazonaws.com"
        assert result["previous_primary_endpoint"] == "primary.us-east-1.rds.amazonaws.com"
        assert result["endpoints_updated"] is True
        assert result["error"] is None
        assert isinstance(result["failover_duration_seconds"], float)


class TestExecuteFailoverFailure:
    """execute_failover tool — failure path (unhealthy replication)."""

    def test_unhealthy_replication_returns_failure(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-endpoint": {"Parameter": {"Value": "primary.rds.amazonaws.com"}},
            "/makita/db/replica-endpoint": {"Parameter": {"Value": "replica.rds.amazonaws.com"}},
        }[Name]

        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Normal": False, "Status": "error"}
                    ],
                }
            ]
        }

        with patch.object(_failover_mod, "_ssm_client", return_value=ssm), \
             patch.object(_failover_mod, "_rds_client", return_value=rds):
            result = _failover_mod.execute_failover(
                primary_region="us-east-1",
                dr_region="us-west-2",
                cluster_name="makita-pg-cluster",
            )

        assert result["success"] is False
        assert result["error"] is not None


class TestExecuteFailoverException:
    """execute_failover tool — exception handling."""

    def test_exception_returns_structured_error(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = Exception("SSM unavailable")

        with patch.object(_failover_mod, "_ssm_client", return_value=ssm):
            result = _failover_mod.execute_failover(
                primary_region="us-east-1",
                dr_region="us-west-2",
                cluster_name="makita-pg-cluster",
            )

        assert result["success"] is False
        assert "SSM unavailable" in result["error"]


class TestHealthCheckSuccess:
    """health_check tool — success path."""

    def test_healthy_cluster(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-region": {"Parameter": {"Value": "us-east-1"}},
            "/makita/db/dr-region": {"Parameter": {"Value": "us-west-2"}},
        }[Name]

        rds_primary = MagicMock()
        rds_primary.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available"}]
        }
        rds_dr = MagicMock()
        rds_dr.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Message": "0"}
                    ],
                }
            ]
        }

        def rds_by_region(region_name):
            return rds_primary if region_name == "us-east-1" else rds_dr

        with patch.object(_failover_mod, "_ssm_client", return_value=ssm), \
             patch.object(_failover_mod, "_rds_client", side_effect=rds_by_region):
            result = _failover_mod.health_check(cluster_name="makita-pg-cluster")

        assert result["cluster_name"] == "makita-pg-cluster"
        assert result["primary_status"] == "available"
        assert result["replica_status"] == "available"
        assert result["replication_healthy"] is True
        assert result["replication_lag_seconds"] == 0.0


class TestHealthCheckFailure:
    """health_check tool — unhealthy cluster."""

    def test_high_replication_lag(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-region": {"Parameter": {"Value": "us-east-1"}},
            "/makita/db/dr-region": {"Parameter": {"Value": "us-west-2"}},
        }[Name]

        rds_primary = MagicMock()
        rds_primary.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available"}]
        }
        rds_dr = MagicMock()
        rds_dr.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Message": "60"}
                    ],
                }
            ]
        }

        def rds_by_region(region_name):
            return rds_primary if region_name == "us-east-1" else rds_dr

        with patch.object(_failover_mod, "_ssm_client", return_value=ssm), \
             patch.object(_failover_mod, "_rds_client", side_effect=rds_by_region):
            result = _failover_mod.health_check(cluster_name="makita-pg-cluster")

        assert result["replication_healthy"] is False
        assert result["replication_lag_seconds"] == 60.0


class TestHealthCheckException:
    """health_check tool — exception handling."""

    def test_exception_returns_error_dict(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = Exception("connection refused")

        with patch.object(_failover_mod, "_ssm_client", return_value=ssm):
            result = _failover_mod.health_check(cluster_name="makita-pg-cluster")

        assert result["replication_healthy"] is False
        assert "connection refused" in result["error"]


# ============================================================================
# Pre-Check MCP Server Tests (Requirement 23.5)
# ============================================================================


class TestVerifyReplicationHealthSuccess:
    """verify_replication_health tool — success path."""

    def test_healthy_replication(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-region": {"Parameter": {"Value": "us-east-1"}},
            "/makita/db/dr-region": {"Parameter": {"Value": "us-west-2"}},
        }[Name]

        rds_primary = MagicMock()
        rds_primary.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available"}]
        }
        rds_dr = MagicMock()
        rds_dr.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Normal": True, "Message": "0", "Status": "replicating"}
                    ],
                }
            ]
        }

        def rds_by_region(region_name):
            return rds_primary if region_name == "us-east-1" else rds_dr

        with patch.object(_precheck_mod, "_ssm_client", return_value=ssm), \
             patch.object(_precheck_mod, "_rds_client", side_effect=rds_by_region):
            result = _precheck_mod.verify_replication_health(cluster_name="makita-pg-cluster")

        assert result["check_name"] == "replication_health"
        assert result["passed"] is True
        assert result["error"] is None
        assert result["details"]["replication_lag_seconds"] == 0.0


class TestVerifyReplicationHealthFailure:
    """verify_replication_health tool — failure path."""

    def test_high_lag_fails(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-region": {"Parameter": {"Value": "us-east-1"}},
            "/makita/db/dr-region": {"Parameter": {"Value": "us-west-2"}},
        }[Name]

        rds_primary = MagicMock()
        rds_primary.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available"}]
        }
        rds_dr = MagicMock()
        rds_dr.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Normal": True, "Message": "45", "Status": "replicating"}
                    ],
                }
            ]
        }

        def rds_by_region(region_name):
            return rds_primary if region_name == "us-east-1" else rds_dr

        with patch.object(_precheck_mod, "_ssm_client", return_value=ssm), \
             patch.object(_precheck_mod, "_rds_client", side_effect=rds_by_region):
            result = _precheck_mod.verify_replication_health(cluster_name="makita-pg-cluster")

        assert result["passed"] is False
        assert result["error"] is not None


class TestVerifyReplicationHealthException:
    """verify_replication_health tool — exception handling."""

    def test_exception_returns_structured_error(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = Exception("SSM timeout")

        with patch.object(_precheck_mod, "_ssm_client", return_value=ssm):
            result = _precheck_mod.verify_replication_health(cluster_name="makita-pg-cluster")

        assert result["check_name"] == "replication_health"
        assert result["passed"] is False
        assert "SSM timeout" in result["error"]


class TestVerifyPrimaryStatusSuccess:
    """verify_primary_status tool — success path."""

    def test_available_primary(self):
        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available"}]
        }

        with patch.object(_precheck_mod, "_rds_client", return_value=rds):
            result = _precheck_mod.verify_primary_status(
                cluster_name="makita-pg-cluster",
                primary_region="us-east-1",
            )

        assert result["check_name"] == "primary_status"
        assert result["passed"] is True
        assert result["details"]["primary_status"] == "available"
        assert result["error"] is None


class TestVerifyPrimaryStatusFailure:
    """verify_primary_status tool — failure path (unknown status)."""

    def test_unknown_status_fails(self):
        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "stopped"}]
        }

        with patch.object(_precheck_mod, "_rds_client", return_value=rds):
            result = _precheck_mod.verify_primary_status(
                cluster_name="makita-pg-cluster",
                primary_region="us-east-1",
            )

        assert result["passed"] is False
        assert result["error"] is not None


class TestVerifyPrimaryStatusException:
    """verify_primary_status tool — exception handling."""

    def test_exception_returns_structured_error(self):
        rds = MagicMock()
        rds.describe_db_instances.side_effect = Exception("RDS API error")

        with patch.object(_precheck_mod, "_rds_client", return_value=rds):
            result = _precheck_mod.verify_primary_status(
                cluster_name="makita-pg-cluster",
                primary_region="us-east-1",
            )

        assert result["check_name"] == "primary_status"
        assert result["passed"] is False
        assert "RDS API error" in result["error"]


class TestVerifyReplicaReadinessSuccess:
    """verify_replica_readiness tool — success path."""

    def test_ready_replica(self):
        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Normal": True, "Message": "2"}
                    ],
                }
            ]
        }

        with patch.object(_precheck_mod, "_rds_client", return_value=rds):
            result = _precheck_mod.verify_replica_readiness(
                cluster_name="makita-pg-cluster",
                dr_region="us-west-2",
            )

        assert result["check_name"] == "replica_readiness"
        assert result["passed"] is True
        assert result["details"]["replication_lag_seconds"] == 2.0
        assert result["error"] is None


class TestVerifyReplicaReadinessFailure:
    """verify_replica_readiness tool — failure path."""

    def test_not_available_fails(self):
        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "creating",
                    "StatusInfos": [],
                }
            ]
        }

        with patch.object(_precheck_mod, "_rds_client", return_value=rds):
            result = _precheck_mod.verify_replica_readiness(
                cluster_name="makita-pg-cluster",
                dr_region="us-west-2",
            )

        assert result["passed"] is False
        assert result["error"] is not None


class TestVerifyReplicaReadinessException:
    """verify_replica_readiness tool — exception handling."""

    def test_exception_returns_structured_error(self):
        rds = MagicMock()
        rds.describe_db_instances.side_effect = Exception("network error")

        with patch.object(_precheck_mod, "_rds_client", return_value=rds):
            result = _precheck_mod.verify_replica_readiness(
                cluster_name="makita-pg-cluster",
                dr_region="us-west-2",
            )

        assert result["check_name"] == "replica_readiness"
        assert result["passed"] is False
        assert "network error" in result["error"]


# ============================================================================
# Post-Check MCP Server Tests (Requirement 23.6)
# ============================================================================


class TestVerifyNewPrimaryHealthSuccess:
    """verify_new_primary_health tool — success path."""

    def test_healthy_new_primary(self):
        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available"}]
        }

        with patch.object(_postcheck_mod, "_rds_client", return_value=rds):
            result = _postcheck_mod.verify_new_primary_health(
                cluster_name="makita-pg-cluster",
                dr_region="us-west-2",
            )

        assert result["check_name"] == "new_primary_health"
        assert result["passed"] is True
        assert result["details"]["instance_status"] == "available"
        assert result["error"] is None


class TestVerifyNewPrimaryHealthFailure:
    """verify_new_primary_health tool — failure path."""

    def test_unhealthy_new_primary(self):
        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "rebooting"}]
        }

        with patch.object(_postcheck_mod, "_rds_client", return_value=rds):
            result = _postcheck_mod.verify_new_primary_health(
                cluster_name="makita-pg-cluster",
                dr_region="us-west-2",
            )

        assert result["passed"] is False
        assert result["error"] is not None


class TestVerifyNewPrimaryHealthException:
    """verify_new_primary_health tool — exception handling."""

    def test_exception_returns_structured_error(self):
        rds = MagicMock()
        rds.describe_db_instances.side_effect = Exception("RDS describe failed")

        with patch.object(_postcheck_mod, "_rds_client", return_value=rds):
            result = _postcheck_mod.verify_new_primary_health(
                cluster_name="makita-pg-cluster",
                dr_region="us-west-2",
            )

        assert result["check_name"] == "new_primary_health"
        assert result["passed"] is False
        assert "RDS describe failed" in result["error"]


class TestVerifyEndpointsSuccess:
    """verify_endpoints tool — success path."""

    def test_endpoints_reflect_new_primary(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-endpoint": {"Parameter": {"Value": "replica.us-west-2.rds.amazonaws.com"}},
            "/makita/db/replica-endpoint": {"Parameter": {"Value": "primary.us-east-1.rds.amazonaws.com"}},
            "/makita/db/primary-region": {"Parameter": {"Value": "us-west-2"}},
        }[Name]

        with patch.object(_postcheck_mod, "_ssm_client", return_value=ssm):
            result = _postcheck_mod.verify_endpoints(cluster_name="makita-pg-cluster")

        assert result["check_name"] == "endpoint_verification"
        assert result["passed"] is True
        assert result["error"] is None
        assert result["details"]["primary_region"] == "us-west-2"


class TestVerifyEndpointsFailure:
    """verify_endpoints tool — failure path (region not updated)."""

    def test_region_not_updated_fails(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-endpoint": {"Parameter": {"Value": "primary.us-east-1.rds.amazonaws.com"}},
            "/makita/db/replica-endpoint": {"Parameter": {"Value": "replica.us-west-2.rds.amazonaws.com"}},
            "/makita/db/primary-region": {"Parameter": {"Value": "us-east-1"}},
        }[Name]

        with patch.object(_postcheck_mod, "_ssm_client", return_value=ssm):
            result = _postcheck_mod.verify_endpoints(cluster_name="makita-pg-cluster")

        assert result["passed"] is False
        assert result["error"] is not None


class TestVerifyEndpointsException:
    """verify_endpoints tool — exception handling."""

    def test_exception_returns_structured_error(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = Exception("parameter not found")

        with patch.object(_postcheck_mod, "_ssm_client", return_value=ssm):
            result = _postcheck_mod.verify_endpoints(cluster_name="makita-pg-cluster")

        assert result["check_name"] == "endpoint_verification"
        assert result["passed"] is False
        assert "parameter not found" in result["error"]


class TestVerifyReplicationEstablishedSuccess:
    """verify_replication_established tool — success path."""

    def test_replication_established(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-region": {"Parameter": {"Value": "us-west-2"}},
            "/makita/db/dr-region": {"Parameter": {"Value": "us-east-1"}},
            "/makita/db/replication-status": {"Parameter": {"Value": "promoted"}},
        }[Name]

        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceStatus": "available",
                    "StatusInfos": [
                        {"StatusType": "read replication", "Message": "0"}
                    ],
                }
            ]
        }

        with patch.object(_postcheck_mod, "_ssm_client", return_value=ssm), \
             patch.object(_postcheck_mod, "_rds_client", return_value=rds):
            result = _postcheck_mod.verify_replication_established(cluster_name="makita-pg-cluster")

        assert result["check_name"] == "replication_established"
        assert result["passed"] is True
        assert result["error"] is None
        assert result["details"]["replication_status"] == "promoted"


class TestVerifyReplicationEstablishedFailure:
    """verify_replication_established tool — failure path."""

    def test_not_promoted_fails(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = lambda Name: {
            "/makita/db/primary-region": {"Parameter": {"Value": "us-west-2"}},
            "/makita/db/dr-region": {"Parameter": {"Value": "us-east-1"}},
            "/makita/db/replication-status": {"Parameter": {"Value": "replicating"}},
        }[Name]

        rds = MagicMock()
        rds.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceStatus": "available", "StatusInfos": []}]
        }

        with patch.object(_postcheck_mod, "_ssm_client", return_value=ssm), \
             patch.object(_postcheck_mod, "_rds_client", return_value=rds):
            result = _postcheck_mod.verify_replication_established(cluster_name="makita-pg-cluster")

        assert result["passed"] is False
        assert result["error"] is not None


class TestVerifyReplicationEstablishedException:
    """verify_replication_established tool — exception handling."""

    def test_exception_returns_structured_error(self):
        ssm = MagicMock()
        ssm.get_parameter.side_effect = Exception("access denied")

        with patch.object(_postcheck_mod, "_ssm_client", return_value=ssm):
            result = _postcheck_mod.verify_replication_established(cluster_name="makita-pg-cluster")

        assert result["check_name"] == "replication_established"
        assert result["passed"] is False
        assert "access denied" in result["error"]
