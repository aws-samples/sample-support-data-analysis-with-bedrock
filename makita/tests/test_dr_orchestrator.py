"""Unit tests for makita_dr.dr_orchestrator using unittest.mock to mock all dependencies."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from makita_dr.models import (
    CheckResult,
    CheckStatus,
    DRConfig,
    DNSUpdateResult,
    FailoverEvent,
    FailoverResult,
    FailoverStatus,
    PostCheckResult,
    PreCheckResult,
    PromoteResult,
)
from makita_dr.dr_orchestrator import DROrchestrator


# ---------------------------------------------------------------------------
# Helpers
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


def _passing_pre_check_result() -> PreCheckResult:
    return PreCheckResult(
        checks=[
            CheckResult(check_name="replica_health", status=CheckStatus.PASSED, message="OK"),
            CheckResult(check_name="replication_lag", status=CheckStatus.PASSED, message="OK"),
            CheckResult(check_name="network_connectivity", status=CheckStatus.PASSED, message="OK"),
        ],
        overall_status=CheckStatus.PASSED,
    )


def _failing_pre_check_result() -> PreCheckResult:
    return PreCheckResult(
        checks=[
            CheckResult(check_name="replica_health", status=CheckStatus.PASSED, message="OK"),
            CheckResult(check_name="replication_lag", status=CheckStatus.FAILED, message="Lag too high"),
        ],
        overall_status=CheckStatus.FAILED,
    )


def _passing_post_check_result() -> PostCheckResult:
    return PostCheckResult(
        checks=[
            CheckResult(check_name="read_write_mode", status=CheckStatus.PASSED, message="OK"),
            CheckResult(check_name="application_queries", status=CheckStatus.PASSED, message="OK"),
            CheckResult(check_name="dns_routing", status=CheckStatus.PASSED, message="OK"),
        ],
        overall_status=CheckStatus.PASSED,
    )


def _failing_post_check_result() -> PostCheckResult:
    return PostCheckResult(
        checks=[
            CheckResult(check_name="dns_routing", status=CheckStatus.FAILED, message="DNS mismatch"),
        ],
        overall_status=CheckStatus.FAILED,
    )


def _success_promote_result() -> PromoteResult:
    return PromoteResult(
        success=True,
        promoted_instance_id="makita-dr-replica",
        promoted_endpoint="makita-dr-replica.us-east-2.rds.amazonaws.com",
        message="Promoted successfully",
    )


def _success_dns_result() -> DNSUpdateResult:
    return DNSUpdateResult(
        success=True,
        record_name="db.example.com",
        new_value="makita-dr-replica.us-east-2.rds.amazonaws.com",
        message="DNS updated",
    )


def _build_orchestrator(
    pre_check_result=None,
    post_check_result=None,
    promote_result=None,
    dns_result=None,
    verify_rw=True,
    mcp_summary_result=None,
):
    """Build a DROrchestrator with fully mocked dependencies."""
    config = _make_config()

    incident_manager = MagicMock()
    incident_manager.create_slack_channel.return_value = "C_TEST_CHANNEL"
    incident_manager.create_servicenow_ticket.return_value = "SNOW-001"
    incident_manager.create_support_ticket.return_value = "CASE-001"

    pre_check_engine = MagicMock()
    pre_check_engine.run_all_checks.return_value = (
        pre_check_result if pre_check_result else _passing_pre_check_result()
    )

    post_check_engine = MagicMock()
    post_check_engine.run_all_checks.return_value = (
        post_check_result if post_check_result else _passing_post_check_result()
    )

    rds_failover = MagicMock()
    rds_failover.identify_instances.return_value = ({}, {})
    rds_failover.promote_read_replica.return_value = (
        promote_result if promote_result else _success_promote_result()
    )
    rds_failover.update_dns.return_value = (
        dns_result if dns_result else _success_dns_result()
    )
    rds_failover.verify_read_write.return_value = verify_rw

    mcp_server = MagicMock()
    mcp_server.generate_failover_summary.return_value = (
        mcp_summary_result
        if mcp_summary_result
        else {"status": "success", "summary": "All steps completed."}
    )

    dashboard_manager = MagicMock()

    orch = DROrchestrator(
        config=config,
        incident_manager=incident_manager,
        pre_check_engine=pre_check_engine,
        post_check_engine=post_check_engine,
        rds_failover_manager=rds_failover,
        mcp_server=mcp_server,
        dashboard_manager=dashboard_manager,
    )
    return orch, {
        "incident_manager": incident_manager,
        "pre_check_engine": pre_check_engine,
        "post_check_engine": post_check_engine,
        "rds_failover": rds_failover,
        "mcp_server": mcp_server,
        "dashboard_manager": dashboard_manager,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_returns_completed_status(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.COMPLETED

    def test_returns_summary(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.summary == "All steps completed."

    def test_event_has_slack_channel(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.slack_channel_id == "C_TEST_CHANNEL"

    def test_event_has_servicenow_ticket(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.servicenow_ticket_id == "SNOW-001"

    def test_event_has_support_case(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.aws_support_case_id == "CASE-001"

    def test_event_has_pre_check_result(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.pre_check_result is not None
        assert result.event.pre_check_result.passed

    def test_event_has_post_check_result(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.post_check_result is not None
        assert result.event.post_check_result.passed

    def test_event_has_promote_result(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.promote_result is not None
        assert result.event.promote_result.success

    def test_event_has_dns_update_result(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.dns_update_result is not None
        assert result.event.dns_update_result.success

    def test_event_completed_at_is_set(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.completed_at is not None

    def test_actions_log_is_populated(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert len(result.event.actions_log) > 0

    def test_no_error_message(self):
        orch, _ = _build_orchestrator()
        result = orch.initiate_failover()
        assert result.event.error_message is None


# ---------------------------------------------------------------------------
# Workflow step calls
# ---------------------------------------------------------------------------

class TestWorkflowCalls:
    def test_slack_channel_created(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["incident_manager"].create_slack_channel.assert_called_once()

    def test_initial_message_posted(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["incident_manager"].post_initial_message.assert_called_once()

    def test_servicenow_ticket_created(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["incident_manager"].create_servicenow_ticket.assert_called_once()

    def test_support_ticket_created(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["incident_manager"].create_support_ticket.assert_called_once()

    def test_pre_checks_run(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["pre_check_engine"].run_all_checks.assert_called_once()

    def test_instances_identified(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["rds_failover"].identify_instances.assert_called_once()

    def test_replica_promoted(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["rds_failover"].promote_read_replica.assert_called_once()

    def test_dns_updated(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["rds_failover"].update_dns.assert_called_once()

    def test_read_write_verified(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["rds_failover"].verify_read_write.assert_called_once()

    def test_post_checks_run(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["post_check_engine"].run_all_checks.assert_called_once()

    def test_mcp_summary_generated(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["mcp_server"].generate_failover_summary.assert_called_once()

    def test_tickets_updated_with_completed(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["incident_manager"].update_servicenow_ticket.assert_called()
        call_args = deps["incident_manager"].update_servicenow_ticket.call_args
        assert call_args[0][0] == "SNOW-001"
        assert call_args[0][1] == "completed"

    def test_actions_logged_to_slack(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        assert deps["incident_manager"].log_action.call_count > 0


# ---------------------------------------------------------------------------
# Failure scenarios
# ---------------------------------------------------------------------------

class TestPreCheckFailure:
    def test_halts_on_pre_check_failure(self):
        orch, deps = _build_orchestrator(pre_check_result=_failing_pre_check_result())
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.FAILED
        assert "Pre-checks failed" in result.event.error_message

    def test_does_not_promote_on_pre_check_failure(self):
        orch, deps = _build_orchestrator(pre_check_result=_failing_pre_check_result())
        orch.initiate_failover()
        deps["rds_failover"].promote_read_replica.assert_not_called()

    def test_does_not_run_post_checks_on_pre_check_failure(self):
        orch, deps = _build_orchestrator(pre_check_result=_failing_pre_check_result())
        orch.initiate_failover()
        deps["post_check_engine"].run_all_checks.assert_not_called()

    def test_tickets_updated_with_failed_on_pre_check_failure(self):
        orch, deps = _build_orchestrator(pre_check_result=_failing_pre_check_result())
        orch.initiate_failover()
        # Tickets should be updated with "failed" status
        snow_calls = deps["incident_manager"].update_servicenow_ticket.call_args_list
        assert any(c[0][1] == "failed" for c in snow_calls)


class TestPromotionFailure:
    def test_halts_on_promotion_failure(self):
        bad_promote = PromoteResult(
            success=False,
            promoted_instance_id="makita-dr-replica",
            promoted_endpoint="",
            message="Promotion timed out",
        )
        orch, deps = _build_orchestrator(promote_result=bad_promote)
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.FAILED
        assert "Replica promotion failed" in result.event.error_message

    def test_does_not_update_dns_on_promotion_failure(self):
        bad_promote = PromoteResult(
            success=False,
            promoted_instance_id="makita-dr-replica",
            promoted_endpoint="",
            message="Promotion timed out",
        )
        orch, deps = _build_orchestrator(promote_result=bad_promote)
        orch.initiate_failover()
        deps["rds_failover"].update_dns.assert_not_called()


class TestDNSFailure:
    def test_halts_on_dns_failure(self):
        bad_dns = DNSUpdateResult(
            success=False,
            record_name="db.example.com",
            new_value="",
            message="Route53 error",
        )
        orch, _ = _build_orchestrator(dns_result=bad_dns)
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.FAILED
        assert "DNS update failed" in result.event.error_message


class TestVerifyReadWriteFailure:
    def test_halts_when_not_read_write(self):
        orch, _ = _build_orchestrator(verify_rw=False)
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.FAILED
        assert "read-write" in result.event.error_message.lower()


class TestPostCheckFailure:
    def test_halts_on_post_check_failure(self):
        orch, _ = _build_orchestrator(post_check_result=_failing_post_check_result())
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.FAILED
        assert "Post-checks failed" in result.event.error_message


class TestMCPSummaryFailure:
    def test_completes_even_if_summary_fails(self):
        orch, _ = _build_orchestrator(
            mcp_summary_result={"status": "error", "message": "Lambda timeout"}
        )
        result = orch.initiate_failover()
        # Summary failure should not halt the workflow
        assert result.event.status == FailoverStatus.COMPLETED
        assert result.summary is None


class TestExceptionDuringFailover:
    def test_exception_in_identify_halts(self):
        orch, deps = _build_orchestrator()
        deps["rds_failover"].identify_instances.side_effect = RuntimeError("RDS API error")
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.FAILED
        assert "RDS API error" in result.event.error_message

    def test_exception_in_promote_halts(self):
        orch, deps = _build_orchestrator()
        deps["rds_failover"].promote_read_replica.side_effect = Exception("Timeout")
        result = orch.initiate_failover()
        assert result.event.status == FailoverStatus.FAILED

    def test_error_logged_to_slack(self):
        orch, deps = _build_orchestrator()
        deps["rds_failover"].identify_instances.side_effect = RuntimeError("boom")
        orch.initiate_failover()
        # log_action should have been called with the error
        log_calls = [str(c) for c in deps["incident_manager"].log_action.call_args_list]
        assert any("FAILED" in c for c in log_calls)


# ---------------------------------------------------------------------------
# handle_slack_question
# ---------------------------------------------------------------------------

class TestHandleSlackQuestion:
    def test_delegates_to_incident_manager(self):
        orch, deps = _build_orchestrator()
        orch.initiate_failover()
        deps["incident_manager"].handle_mention.return_value = "Status: completed"
        response = orch.handle_slack_question("What is the DR status?")
        deps["incident_manager"].handle_mention.assert_called_once_with(
            "C_TEST_CHANNEL", "What is the DR status?", orch._event
        )
        assert response == "Status: completed"

    def test_returns_message_when_no_active_event(self):
        config = _make_config()
        orch = DROrchestrator(
            config=config,
            incident_manager=MagicMock(),
            pre_check_engine=MagicMock(),
            post_check_engine=MagicMock(),
            rds_failover_manager=MagicMock(),
            mcp_server=MagicMock(),
            dashboard_manager=MagicMock(),
        )
        response = orch.handle_slack_question("status?")
        assert "No active DR event" in response

    def test_returns_message_when_no_channel(self):
        config = _make_config()
        orch = DROrchestrator(
            config=config,
            incident_manager=MagicMock(),
            pre_check_engine=MagicMock(),
            post_check_engine=MagicMock(),
            rds_failover_manager=MagicMock(),
            mcp_server=MagicMock(),
            dashboard_manager=MagicMock(),
        )
        response = orch.handle_slack_question("What happened?")
        assert "No active DR event" in response
