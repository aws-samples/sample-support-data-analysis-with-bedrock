"""Unit tests for makita_dr.rds_failover using moto to mock RDS and Route53."""

import boto3
import pytest
from moto import mock_aws
from unittest.mock import patch

from makita_dr.models import DRConfig, DNSUpdateResult, PromoteResult
from makita_dr.rds_failover import RDSFailoverManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DR_REGION = "us-east-2"
_PRIMARY_REGION = "us-east-1"
_DNS_RECORD = "db.example.com"


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


def _create_hosted_zone(route53):
    """Create a Route53 hosted zone and return its ID."""
    zone_resp = route53.create_hosted_zone(
        Name="example.com",
        CallerReference="unique-ref-rds-failover",
    )
    return zone_resp["HostedZone"]["Id"].split("/")[-1]


def _create_hosted_zone_with_record(route53, record_value):
    """Create a hosted zone with a CNAME record."""
    zone_id = _create_hosted_zone(route53)
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
# Tests: identify_instances
# ---------------------------------------------------------------------------


class TestIdentifyInstances:
    @mock_aws
    def test_identifies_primary_and_replica(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        manager = RDSFailoverManager(config)
        primary_info, replica_info = manager.identify_instances()

        assert primary_info["DBInstanceIdentifier"] == "makita-dr-primary"
        assert replica_info["DBInstanceIdentifier"] == "makita-dr-replica"

    @mock_aws
    def test_returns_tuple_of_two_dicts(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        manager = RDSFailoverManager(config)
        result = manager.identify_instances()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], dict)
        assert isinstance(result[1], dict)

    @mock_aws
    def test_primary_not_found_raises(self):
        config = _make_config(primary_instance_id="nonexistent-primary")
        manager = RDSFailoverManager(config)

        with pytest.raises(Exception):
            manager.identify_instances()

    @mock_aws
    def test_replica_not_found_raises(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        _create_primary_instance(rds_primary)

        config = _make_config(replica_instance_id="nonexistent-replica")
        manager = RDSFailoverManager(config)

        with pytest.raises(Exception):
            manager.identify_instances()

    @mock_aws
    def test_primary_has_endpoint(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        manager = RDSFailoverManager(config)
        primary_info, _ = manager.identify_instances()

        assert "Endpoint" in primary_info
        assert "Address" in primary_info["Endpoint"]


# ---------------------------------------------------------------------------
# Tests: promote_read_replica
# ---------------------------------------------------------------------------


class TestPromoteReadReplica:
    @mock_aws
    def test_successful_promotion(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        manager = RDSFailoverManager(config)

        # Patch _wait_for_promotion to avoid real polling
        with patch.object(
            manager,
            "_wait_for_promotion",
            return_value="makita-dr-replica.abc123.us-east-2.rds.amazonaws.com",
        ):
            result = manager.promote_read_replica()

        assert isinstance(result, PromoteResult)
        assert result.success is True
        assert result.promoted_instance_id == "makita-dr-replica"
        assert result.promoted_endpoint != ""
        assert "promoted" in result.message.lower()

    @mock_aws
    def test_promotion_of_nonexistent_replica_fails(self):
        config = _make_config(replica_instance_id="nonexistent-replica")
        manager = RDSFailoverManager(config)
        result = manager.promote_read_replica()

        assert isinstance(result, PromoteResult)
        assert result.success is False
        assert "failed" in result.message.lower()

    @mock_aws
    def test_promote_result_has_timestamp(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        manager = RDSFailoverManager(config)

        with patch.object(
            manager,
            "_wait_for_promotion",
            return_value="endpoint.rds.amazonaws.com",
        ):
            result = manager.promote_read_replica()

        assert result.timestamp is not None


# ---------------------------------------------------------------------------
# Tests: update_dns
# ---------------------------------------------------------------------------


class TestUpdateDns:
    @mock_aws
    def test_successful_dns_update(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53")

        # Create a standalone instance (simulating post-promotion)
        rds_dr.create_db_instance(
            DBInstanceIdentifier="makita-dr-replica",
            DBInstanceClass="db.r5.large",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
        )

        zone_id = _create_hosted_zone_with_record(route53, "old-primary.example.com")
        config = _make_config(dns_hosted_zone_id=zone_id)
        manager = RDSFailoverManager(config)
        result = manager.update_dns()

        assert isinstance(result, DNSUpdateResult)
        assert result.success is True
        assert result.record_name == _DNS_RECORD
        assert result.new_value != ""
        assert "updated" in result.message.lower()

    @mock_aws
    def test_dns_update_points_to_promoted_endpoint(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53")

        rds_dr.create_db_instance(
            DBInstanceIdentifier="makita-dr-replica",
            DBInstanceClass="db.r5.large",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
        )

        # Get the endpoint moto assigned
        resp = rds_dr.describe_db_instances(DBInstanceIdentifier="makita-dr-replica")
        expected_endpoint = resp["DBInstances"][0]["Endpoint"]["Address"]

        zone_id = _create_hosted_zone(route53)
        config = _make_config(dns_hosted_zone_id=zone_id)
        manager = RDSFailoverManager(config)
        result = manager.update_dns()

        assert result.new_value == expected_endpoint

        # Verify the Route53 record was actually updated
        dns_resp = route53.list_resource_record_sets(
            HostedZoneId=zone_id,
            StartRecordName=_DNS_RECORD,
            StartRecordType="CNAME",
            MaxItems="1",
        )
        records = dns_resp["ResourceRecordSets"]
        cname_record = next(
            (r for r in records if r["Name"].rstrip(".") == _DNS_RECORD),
            None,
        )
        assert cname_record is not None
        values = [rr["Value"] for rr in cname_record["ResourceRecords"]]
        assert expected_endpoint in values

    @mock_aws
    def test_dns_update_nonexistent_instance_fails(self):
        route53 = boto3.client("route53")
        zone_id = _create_hosted_zone(route53)

        config = _make_config(
            replica_instance_id="nonexistent-replica",
            dns_hosted_zone_id=zone_id,
        )
        manager = RDSFailoverManager(config)
        result = manager.update_dns()

        assert isinstance(result, DNSUpdateResult)
        assert result.success is False
        assert "failed" in result.message.lower()

    @mock_aws
    def test_dns_update_result_has_timestamp(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        route53 = boto3.client("route53")

        rds_dr.create_db_instance(
            DBInstanceIdentifier="makita-dr-replica",
            DBInstanceClass="db.r5.large",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
        )

        zone_id = _create_hosted_zone(route53)
        config = _make_config(dns_hosted_zone_id=zone_id)
        manager = RDSFailoverManager(config)
        result = manager.update_dns()

        assert result.timestamp is not None


# ---------------------------------------------------------------------------
# Tests: verify_read_write
# ---------------------------------------------------------------------------


class TestVerifyReadWrite:
    @mock_aws
    def test_standalone_instance_returns_true(self):
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        rds_dr.create_db_instance(
            DBInstanceIdentifier="makita-dr-replica",
            DBInstanceClass="db.r5.large",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
        )

        config = _make_config()
        manager = RDSFailoverManager(config)
        assert manager.verify_read_write() is True

    @mock_aws
    def test_replica_returns_false(self):
        rds_primary = boto3.client("rds", region_name=_PRIMARY_REGION)
        rds_dr = boto3.client("rds", region_name=_DR_REGION)
        _create_replica(rds_primary, rds_dr)

        config = _make_config()
        manager = RDSFailoverManager(config)
        assert manager.verify_read_write() is False

    @mock_aws
    def test_nonexistent_instance_returns_false(self):
        config = _make_config(replica_instance_id="nonexistent-db")
        manager = RDSFailoverManager(config)
        assert manager.verify_read_write() is False
