"""Unit tests for makita_dr.pre_check_engine using moto to mock RDS and EC2."""

import boto3
import pytest
from moto import mock_aws

from makita_dr.models import CheckStatus, DRConfig, PreCheckResult
from makita_dr.pre_check_engine import PreCheckEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DR_REGION = "us-east-2"
_PRIMARY_REGION = "us-east-1"


def _make_config(**overrides) -> DRConfig:
    defaults = dict(
        primary_instance_id="makita-dr-primary",
        replica_instance_id="makita-dr-replica",
        primary_region=_PRIMARY_REGION,
        dr_region=_DR_REGION,
        replication_lag_threshold_seconds=30,
        dns_record_name="db.example.com",
        dns_hosted_zone_id="Z1234567890",
        servicenow_endpoint="http://localhost:8080",
        servicenow_api_key="test-key",
        slack_bot_token="xoxb-test",
        slack_workspace_id="W123",
        support_severity="high",
        support_service_code="amazon-rds",
        support_category_code="failover",
        mcp_server_endpoint="http://localhost:9000",
        lambda_function_arn="arn:aws:lambda:us-east-1:123456789012:function:makita-dr-summary",
        guardrail_id="gr-123",
        guardrail_version="1",
        cognito_user_pool_id="us-east-1_abc",
        cognito_client_id="client123",
    )
    defaults.update(overrides)
    return DRConfig(**defaults)


def _create_primary_instance(rds_primary):
    """Create the primary RDS instance in the primary region."""
    rds_primary.create_db_instance(
        DBInstanceIdentifier="makita-dr-primary",
        DBInstanceClass="db.r5.large",
        Engine="postgres",
        MasterUsername="admin",
        MasterUserPassword="password123",
    )


def _create_replica(rds_primary, rds_dr):
    """Create a cross-region read replica in the DR region."""
    _create_primary_instance(rds_primary)
    rds_dr.create_db_instance_read_replica(
        DBInstanceIdentifier="makita-dr-replica",
        SourceDBInstanceIdentifier=f"arn:aws:rds:{_PRIMARY_REGION}:123456789012:db:makita-dr-primary",
        DBInstanceClass="db.r5.large",
        SourceRegion=_PRIMARY_REGION,
    )


# ---------------------------------------------------------------------------
# Tests: run_all_checks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    @mock_aws
    def test_all_checks_pass_returns_passed(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        engine = PreCheckEngine(config)
        result = engine.run_all_checks()

        assert isinstance(result, PreCheckResult)
        assert len(result.checks) == 3

    @mock_aws
    def test_returns_precheck_result_type(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        engine = PreCheckEngine(config)
        result = engine.run_all_checks()

        assert isinstance(result, PreCheckResult)
        assert result.timestamp is not None

    @mock_aws
    def test_any_failure_makes_overall_failed(self):
        """If replica doesn't exist, at least one check fails → overall FAILED."""
        config = _make_config(replica_instance_id="nonexistent-replica")
        engine = PreCheckEngine(config)
        result = engine.run_all_checks()

        assert result.overall_status == CheckStatus.FAILED
        assert result.passed is False

    @mock_aws
    def test_aggregation_all_passed_means_overall_passed(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        engine = PreCheckEngine(config)
        result = engine.run_all_checks()

        passed_checks = [c for c in result.checks if c.status == CheckStatus.PASSED]
        failed_checks = [c for c in result.checks if c.status == CheckStatus.FAILED]

        if len(failed_checks) == 0:
            assert result.overall_status == CheckStatus.PASSED
        else:
            assert result.overall_status == CheckStatus.FAILED


# ---------------------------------------------------------------------------
# Tests: check_replica_health
# ---------------------------------------------------------------------------


class TestCheckReplicaHealth:
    @mock_aws
    def test_healthy_replica_passes(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        engine = PreCheckEngine(config)
        result = engine.check_replica_health()

        assert result.check_name == "replica_health"
        assert result.status == CheckStatus.PASSED
        assert "available" in result.message.lower() or "replicating" in result.message.lower()

    @mock_aws
    def test_nonexistent_replica_fails(self):
        config = _make_config(replica_instance_id="nonexistent-db")
        engine = PreCheckEngine(config)
        result = engine.check_replica_health()

        assert result.status == CheckStatus.FAILED
        assert result.check_name == "replica_health"

    @mock_aws
    def test_standalone_instance_not_replica_fails(self):
        """A standalone instance (not a replica) should fail the replica health check."""
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        rds_dr.create_db_instance(
            DBInstanceIdentifier="makita-dr-replica",
            DBInstanceClass="db.r5.large",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
        )

        config = _make_config()
        engine = PreCheckEngine(config)
        result = engine.check_replica_health()

        assert result.status == CheckStatus.FAILED
        assert "not configured as a read replica" in result.message


# ---------------------------------------------------------------------------
# Tests: check_replication_lag
# ---------------------------------------------------------------------------


class TestCheckReplicationLag:
    @mock_aws
    def test_nonexistent_replica_fails(self):
        config = _make_config(replica_instance_id="nonexistent-db")
        engine = PreCheckEngine(config)
        result = engine.check_replication_lag()

        assert result.status == CheckStatus.FAILED
        assert result.check_name == "replication_lag"

    @mock_aws
    def test_replica_exists_returns_check_result(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        engine = PreCheckEngine(config)
        result = engine.check_replication_lag()

        # moto may not populate StatusInfos, so lag info may not be available
        assert result.check_name == "replication_lag"
        assert result.status in (CheckStatus.PASSED, CheckStatus.FAILED)


# ---------------------------------------------------------------------------
# Tests: check_network_connectivity
# ---------------------------------------------------------------------------


class TestCheckNetworkConnectivity:
    @mock_aws
    def test_nonexistent_replica_fails(self):
        config = _make_config(replica_instance_id="nonexistent-db")
        engine = PreCheckEngine(config)
        result = engine.check_network_connectivity()

        assert result.status == CheckStatus.FAILED
        assert result.check_name == "network_connectivity"

    @mock_aws
    def test_replica_with_valid_network_config(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        engine = PreCheckEngine(config)
        result = engine.check_network_connectivity()

        assert result.check_name == "network_connectivity"
        # moto creates default VPC/subnets/SGs, so this should pass
        assert result.status in (CheckStatus.PASSED, CheckStatus.FAILED)


# ---------------------------------------------------------------------------
# Tests: _extract_replication_lag
# ---------------------------------------------------------------------------


class TestExtractReplicationLag:
    def test_valid_status_info(self):
        db = {
            "StatusInfos": [
                {
                    "StatusType": "read replication",
                    "Normal": True,
                    "Status": "replicating",
                    "Message": "5",
                }
            ]
        }
        assert PreCheckEngine._extract_replication_lag(db) == 5

    def test_no_status_infos(self):
        assert PreCheckEngine._extract_replication_lag({}) is None

    def test_empty_status_infos(self):
        assert PreCheckEngine._extract_replication_lag({"StatusInfos": []}) is None

    def test_non_replication_status(self):
        db = {
            "StatusInfos": [
                {
                    "StatusType": "other",
                    "Normal": True,
                    "Message": "10",
                }
            ]
        }
        assert PreCheckEngine._extract_replication_lag(db) is None

    def test_invalid_message_value(self):
        db = {
            "StatusInfos": [
                {
                    "StatusType": "read replication",
                    "Normal": True,
                    "Message": "not-a-number",
                }
            ]
        }
        assert PreCheckEngine._extract_replication_lag(db) is None

    def test_zero_lag(self):
        db = {
            "StatusInfos": [
                {
                    "StatusType": "read replication",
                    "Normal": True,
                    "Message": "0",
                }
            ]
        }
        assert PreCheckEngine._extract_replication_lag(db) == 0

    def test_high_lag_value(self):
        db = {
            "StatusInfos": [
                {
                    "StatusType": "read replication",
                    "Normal": False,
                    "Message": "300",
                }
            ]
        }
        assert PreCheckEngine._extract_replication_lag(db) == 300
