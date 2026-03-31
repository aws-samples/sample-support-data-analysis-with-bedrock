"""Unit tests for makita_dr.post_check_engine using moto to mock RDS and Route53."""

import boto3
import pytest
from moto import mock_aws

from makita_dr.models import CheckStatus, DRConfig, PostCheckResult
from makita_dr.post_check_engine import PostCheckEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DR_REGION = "us-east-2"
_PRIMARY_REGION = "us-east-1"
_DNS_RECORD = "db.example.com"
_HOSTED_ZONE_ID = None  # Set dynamically in tests


def _make_config(**overrides) -> DRConfig:
    defaults = dict(
        primary_instance_id="makita-dr-primary",
        replica_instance_id="makita-dr-replica",
        primary_region=_PRIMARY_REGION,
        dr_region=_DR_REGION,
        replication_lag_threshold_seconds=30,
        dns_record_name=_DNS_RECORD,
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


def _create_promoted_instance(rds_dr):
    """Create a standalone (promoted) RDS instance in the DR region."""
    rds_dr.create_db_instance(
        DBInstanceIdentifier="makita-dr-replica",
        DBInstanceClass="db.r5.large",
        Engine="postgres",
        MasterUsername="admin",
        MasterUserPassword="password123",
    )


def _create_replica(rds_primary, rds_dr):
    """Create a cross-region read replica (not yet promoted)."""
    rds_primary.create_db_instance(
        DBInstanceIdentifier="makita-dr-primary",
        DBInstanceClass="db.r5.large",
        Engine="postgres",
        MasterUsername="admin",
        MasterUserPassword="password123",
    )
    rds_dr.create_db_instance_read_replica(
        DBInstanceIdentifier="makita-dr-replica",
        SourceDBInstanceIdentifier=f"arn:aws:rds:{_PRIMARY_REGION}:123456789012:db:makita-dr-primary",
        DBInstanceClass="db.r5.large",
        SourceRegion=_PRIMARY_REGION,
    )


def _create_hosted_zone_with_record(route53, record_value):
    """Create a Route53 hosted zone and a CNAME record pointing to record_value."""
    zone_resp = route53.create_hosted_zone(
        Name="example.com",
        CallerReference="unique-ref-123",
    )
    zone_id = zone_resp["HostedZone"]["Id"].split("/")[-1]

    route53.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={
            "Changes": [
                {
                    "Action": "CREATE",
                    "ResourceRecordSet": {
                        "Name": _DNS_RECORD,
                        "Type": "CNAME",
                        "TTL": 300,
                        "ResourceRecords": [{"Value": record_value}],
                    },
                }
            ]
        },
    )
    return zone_id


# ---------------------------------------------------------------------------
# Tests: run_all_checks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    @mock_aws
    def test_all_checks_pass_returns_passed(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        # Get the endpoint address moto assigned
        resp = rds_dr.describe_db_instances(DBInstanceIdentifier="makita-dr-replica")
        endpoint_addr = resp["DBInstances"][0]["Endpoint"]["Address"]

        zone_id = _create_hosted_zone_with_record(route53, endpoint_addr)
        config = _make_config(dns_hosted_zone_id=zone_id)
        engine = PostCheckEngine(config)
        result = engine.run_all_checks()

        assert isinstance(result, PostCheckResult)
        assert len(result.checks) == 3
        assert result.overall_status == CheckStatus.PASSED
        assert result.passed is True

    @mock_aws
    def test_returns_postcheck_result_type(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        config = _make_config()
        engine = PostCheckEngine(config)
        result = engine.run_all_checks()

        assert isinstance(result, PostCheckResult)
        assert result.timestamp is not None

    @mock_aws
    def test_any_failure_makes_overall_failed(self):
        """If instance doesn't exist, all checks fail → overall FAILED."""
        config = _make_config(replica_instance_id="nonexistent-instance")
        engine = PostCheckEngine(config)
        result = engine.run_all_checks()

        assert result.overall_status == CheckStatus.FAILED
        assert result.passed is False

    @mock_aws
    def test_partial_failure_makes_overall_failed(self):
        """If DNS doesn't match but instance is fine, overall is FAILED."""
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        # Point DNS to wrong address
        zone_id = _create_hosted_zone_with_record(route53, "wrong-endpoint.example.com")
        config = _make_config(dns_hosted_zone_id=zone_id)
        engine = PostCheckEngine(config)
        result = engine.run_all_checks()

        assert result.overall_status == CheckStatus.FAILED
        # read_write_mode and application_queries should pass
        passed = [c for c in result.checks if c.status == CheckStatus.PASSED]
        failed = [c for c in result.checks if c.status == CheckStatus.FAILED]
        assert len(passed) == 2
        assert len(failed) == 1
        assert failed[0].check_name == "dns_routing"


# ---------------------------------------------------------------------------
# Tests: check_read_write_mode
# ---------------------------------------------------------------------------


class TestCheckReadWriteMode:
    @mock_aws
    def test_promoted_standalone_instance_passes(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        config = _make_config()
        engine = PostCheckEngine(config)
        result = engine.check_read_write_mode()

        assert result.check_name == "read_write_mode"
        assert result.status == CheckStatus.PASSED
        assert "read-write" in result.message.lower()

    @mock_aws
    def test_nonexistent_instance_fails(self):
        config = _make_config(replica_instance_id="nonexistent-db")
        engine = PostCheckEngine(config)
        result = engine.check_read_write_mode()

        assert result.status == CheckStatus.FAILED
        assert result.check_name == "read_write_mode"

    @mock_aws
    def test_still_replica_fails(self):
        """An instance still configured as a read replica should fail."""
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        engine = PostCheckEngine(config)
        result = engine.check_read_write_mode()

        assert result.status == CheckStatus.FAILED
        assert "replica" in result.message.lower()


# ---------------------------------------------------------------------------
# Tests: check_application_queries
# ---------------------------------------------------------------------------


class TestCheckApplicationQueries:
    @mock_aws
    def test_available_instance_with_endpoint_passes(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        config = _make_config()
        engine = PostCheckEngine(config)
        result = engine.check_application_queries()

        assert result.check_name == "application_queries"
        assert result.status == CheckStatus.PASSED
        assert result.details is not None
        assert result.details["endpoint_address"] != ""

    @mock_aws
    def test_nonexistent_instance_fails(self):
        config = _make_config(replica_instance_id="nonexistent-db")
        engine = PostCheckEngine(config)
        result = engine.check_application_queries()

        assert result.status == CheckStatus.FAILED
        assert result.check_name == "application_queries"


# ---------------------------------------------------------------------------
# Tests: check_dns_routing
# ---------------------------------------------------------------------------


class TestCheckDnsRouting:
    @mock_aws
    def test_dns_pointing_to_promoted_instance_passes(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        resp = rds_dr.describe_db_instances(DBInstanceIdentifier="makita-dr-replica")
        endpoint_addr = resp["DBInstances"][0]["Endpoint"]["Address"]

        zone_id = _create_hosted_zone_with_record(route53, endpoint_addr)
        config = _make_config(dns_hosted_zone_id=zone_id)
        engine = PostCheckEngine(config)
        result = engine.check_dns_routing()

        assert result.check_name == "dns_routing"
        assert result.status == CheckStatus.PASSED
        assert endpoint_addr in result.message

    @mock_aws
    def test_dns_pointing_to_wrong_endpoint_fails(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        zone_id = _create_hosted_zone_with_record(route53, "old-primary.example.com")
        config = _make_config(dns_hosted_zone_id=zone_id)
        engine = PostCheckEngine(config)
        result = engine.check_dns_routing()

        assert result.check_name == "dns_routing"
        assert result.status == CheckStatus.FAILED
        assert "does not point" in result.message

    @mock_aws
    def test_missing_dns_record_fails(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53", region_name=_DR_REGION)
        _create_promoted_instance(rds_dr)

        # Create hosted zone without any record
        zone_resp = route53.create_hosted_zone(
            Name="example.com",
            CallerReference="unique-ref-456",
        )
        zone_id = zone_resp["HostedZone"]["Id"].split("/")[-1]

        config = _make_config(dns_hosted_zone_id=zone_id)
        engine = PostCheckEngine(config)
        result = engine.check_dns_routing()

        assert result.check_name == "dns_routing"
        assert result.status == CheckStatus.FAILED

    @mock_aws
    def test_nonexistent_instance_fails(self):
        config = _make_config(replica_instance_id="nonexistent-db")
        engine = PostCheckEngine(config)
        result = engine.check_dns_routing()

        assert result.status == CheckStatus.FAILED
        assert result.check_name == "dns_routing"
