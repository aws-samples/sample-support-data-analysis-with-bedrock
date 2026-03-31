"""Unit tests for makita_dr.models data models."""

from datetime import datetime

import pytest

from makita_dr.models import (
    CheckResult,
    CheckStatus,
    DNSUpdateResult,
    DRConfig,
    FailoverEvent,
    FailoverResult,
    FailoverStatus,
    PostCheckResult,
    PreCheckResult,
    PromoteResult,
)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestFailoverStatus:
    def test_values(self):
        assert FailoverStatus.NOT_STARTED.value == "not_started"
        assert FailoverStatus.IN_PROGRESS.value == "in_progress"
        assert FailoverStatus.COMPLETED.value == "completed"
        assert FailoverStatus.FAILED.value == "failed"

    def test_member_count(self):
        assert len(FailoverStatus) == 4


class TestCheckStatus:
    def test_values(self):
        assert CheckStatus.PASSED.value == "passed"
        assert CheckStatus.FAILED.value == "failed"
        assert CheckStatus.SKIPPED.value == "skipped"

    def test_member_count(self):
        assert len(CheckStatus) == 3


# ---------------------------------------------------------------------------
# Helper to build a DRConfig with sensible defaults
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> DRConfig:
    defaults = dict(
        primary_instance_id="makita-dr-primary",
        replica_instance_id="makita-dr-replica",
        primary_region="us-east-1",
        dr_region="us-east-2",
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


# ---------------------------------------------------------------------------
# DRConfig tests
# ---------------------------------------------------------------------------


class TestDRConfig:
    def test_creation(self):
        cfg = _make_config()
        assert cfg.primary_region == "us-east-1"
        assert cfg.dr_region == "us-east-2"
        assert cfg.replication_lag_threshold_seconds == 30

    def test_all_fields_stored(self):
        cfg = _make_config()
        assert cfg.primary_instance_id == "makita-dr-primary"
        assert cfg.replica_instance_id == "makita-dr-replica"
        assert cfg.dns_record_name == "db.example.com"
        assert cfg.servicenow_api_key == "test-key"
        assert cfg.slack_bot_token == "xoxb-test"
        assert cfg.cognito_user_pool_id == "us-east-1_abc"


# ---------------------------------------------------------------------------
# CheckResult tests
# ---------------------------------------------------------------------------


class TestCheckResult:
    def test_creation_with_defaults(self):
        cr = CheckResult(
            check_name="replica_health",
            status=CheckStatus.PASSED,
            message="Replica is healthy",
        )
        assert cr.check_name == "replica_health"
        assert cr.status == CheckStatus.PASSED
        assert isinstance(cr.timestamp, datetime)
        assert cr.details is None

    def test_creation_with_details(self):
        cr = CheckResult(
            check_name="replication_lag",
            status=CheckStatus.FAILED,
            message="Lag too high",
            details={"lag_seconds": 120},
        )
        assert cr.details == {"lag_seconds": 120}


# ---------------------------------------------------------------------------
# PreCheckResult / PostCheckResult tests
# ---------------------------------------------------------------------------


class TestPreCheckResult:
    def test_passed_property_true(self):
        checks = [
            CheckResult("c1", CheckStatus.PASSED, "ok"),
            CheckResult("c2", CheckStatus.PASSED, "ok"),
        ]
        result = PreCheckResult(checks=checks, overall_status=CheckStatus.PASSED)
        assert result.passed is True

    def test_passed_property_false(self):
        checks = [
            CheckResult("c1", CheckStatus.PASSED, "ok"),
            CheckResult("c2", CheckStatus.FAILED, "bad"),
        ]
        result = PreCheckResult(checks=checks, overall_status=CheckStatus.FAILED)
        assert result.passed is False

    def test_timestamp_default(self):
        result = PreCheckResult(checks=[], overall_status=CheckStatus.PASSED)
        assert isinstance(result.timestamp, datetime)


class TestPostCheckResult:
    def test_passed_property_true(self):
        result = PostCheckResult(checks=[], overall_status=CheckStatus.PASSED)
        assert result.passed is True

    def test_passed_property_false(self):
        result = PostCheckResult(checks=[], overall_status=CheckStatus.FAILED)
        assert result.passed is False


# ---------------------------------------------------------------------------
# PromoteResult tests
# ---------------------------------------------------------------------------


class TestPromoteResult:
    def test_creation(self):
        pr = PromoteResult(
            success=True,
            promoted_instance_id="makita-dr-replica",
            promoted_endpoint="makita-dr-replica.abc.us-east-2.rds.amazonaws.com",
            message="Promotion successful",
        )
        assert pr.success is True
        assert pr.promoted_instance_id == "makita-dr-replica"
        assert isinstance(pr.timestamp, datetime)


# ---------------------------------------------------------------------------
# DNSUpdateResult tests
# ---------------------------------------------------------------------------


class TestDNSUpdateResult:
    def test_creation(self):
        dns = DNSUpdateResult(
            success=True,
            record_name="db.example.com",
            new_value="makita-dr-replica.abc.us-east-2.rds.amazonaws.com",
            message="DNS updated",
        )
        assert dns.success is True
        assert dns.record_name == "db.example.com"


# ---------------------------------------------------------------------------
# FailoverEvent tests
# ---------------------------------------------------------------------------


class TestFailoverEvent:
    def test_creation_minimal(self):
        now = datetime.utcnow()
        event = FailoverEvent(
            event_id="evt-001",
            status=FailoverStatus.NOT_STARTED,
            initiated_at=now,
        )
        assert event.event_id == "evt-001"
        assert event.status == FailoverStatus.NOT_STARTED
        assert event.completed_at is None
        assert event.primary_region == "us-east-1"
        assert event.dr_region == "us-east-2"
        assert event.actions_log == []

    def test_optional_fields_default_none(self):
        event = FailoverEvent(
            event_id="evt-002",
            status=FailoverStatus.IN_PROGRESS,
            initiated_at=datetime.utcnow(),
        )
        assert event.pre_check_result is None
        assert event.post_check_result is None
        assert event.promote_result is None
        assert event.dns_update_result is None
        assert event.servicenow_ticket_id is None
        assert event.aws_support_case_id is None
        assert event.slack_channel_id is None
        assert event.error_message is None

    def test_actions_log_independence(self):
        """Each instance should get its own actions_log list."""
        e1 = FailoverEvent("e1", FailoverStatus.NOT_STARTED, datetime.utcnow())
        e2 = FailoverEvent("e2", FailoverStatus.NOT_STARTED, datetime.utcnow())
        e1.actions_log.append("step-1")
        assert e2.actions_log == []


# ---------------------------------------------------------------------------
# FailoverResult tests
# ---------------------------------------------------------------------------


class TestFailoverResult:
    def test_creation(self):
        event = FailoverEvent(
            event_id="evt-003",
            status=FailoverStatus.COMPLETED,
            initiated_at=datetime.utcnow(),
        )
        result = FailoverResult(event=event, summary="All good")
        assert result.event is event
        assert result.summary == "All good"

    def test_summary_defaults_none(self):
        event = FailoverEvent(
            event_id="evt-004",
            status=FailoverStatus.FAILED,
            initiated_at=datetime.utcnow(),
        )
        result = FailoverResult(event=event)
        assert result.summary is None
