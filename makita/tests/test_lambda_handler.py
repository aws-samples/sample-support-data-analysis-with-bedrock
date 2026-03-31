"""Unit tests for the makita_dr_summary Lambda handler."""

import pytest

from makita_dr_summary.handler import handler


class TestHandlerValidation:
    """Tests for input validation and error handling."""

    def test_none_event_returns_400(self):
        result = handler(None, None)
        assert result["statusCode"] == 400
        assert "missing or invalid" in result["error"].lower()

    def test_empty_dict_returns_400(self):
        result = handler({}, None)
        assert result["statusCode"] == 400
        assert "Missing required fields" in result["error"]

    def test_non_dict_event_returns_400(self):
        result = handler("not a dict", None)
        assert result["statusCode"] == 400

    def test_missing_event_id_returns_400(self):
        event = {"status": "completed", "initiated_at": "2024-01-15T10:00:00"}
        result = handler(event, None)
        assert result["statusCode"] == 400
        assert "event_id" in result["error"]

    def test_missing_status_returns_400(self):
        event = {"event_id": "evt-1", "initiated_at": "2024-01-15T10:00:00"}
        result = handler(event, None)
        assert result["statusCode"] == 400
        assert "status" in result["error"]

    def test_missing_initiated_at_returns_400(self):
        event = {"event_id": "evt-1", "status": "completed"}
        result = handler(event, None)
        assert result["statusCode"] == 400
        assert "initiated_at" in result["error"]


class TestHandlerHappyPath:
    """Tests for successful summary generation."""

    @pytest.fixture
    def minimal_event(self):
        return {
            "event_id": "evt-001",
            "status": "completed",
            "initiated_at": "2024-01-15T10:00:00",
            "primary_region": "us-east-1",
            "dr_region": "us-east-2",
        }

    @pytest.fixture
    def full_event(self):
        return {
            "event_id": "evt-002",
            "status": "completed",
            "initiated_at": "2024-01-15T10:00:00",
            "completed_at": "2024-01-15T10:30:00",
            "primary_region": "us-east-1",
            "dr_region": "us-east-2",
            "primary_instance_id": "makita-dr-primary",
            "replica_instance_id": "makita-dr-replica",
            "pre_check_result": {
                "overall_status": "passed",
                "checks": [
                    {
                        "check_name": "replica_health",
                        "status": "passed",
                        "message": "Replica is healthy",
                    },
                    {
                        "check_name": "replication_lag",
                        "status": "passed",
                        "message": "Lag within threshold",
                    },
                ],
            },
            "promote_result": {
                "success": True,
                "promoted_instance_id": "makita-dr-replica",
                "promoted_endpoint": "makita-dr-replica.us-east-2.rds.amazonaws.com",
                "message": "Replica promoted successfully",
            },
            "dns_update_result": {
                "success": True,
                "record_name": "db.example.com",
                "new_value": "makita-dr-replica.us-east-2.rds.amazonaws.com",
                "message": "DNS updated",
            },
            "post_check_result": {
                "overall_status": "passed",
                "checks": [
                    {
                        "check_name": "read_write_mode",
                        "status": "passed",
                        "message": "Instance is read-write",
                    },
                ],
            },
            "servicenow_ticket_id": "INC0012345",
            "aws_support_case_id": "case-111222333",
            "slack_channel_id": "C0DRCH4NNEL",
            "actions_log": [
                "Created Slack channel",
                "Created ServiceNow ticket",
                "Pre-checks passed",
                "Replica promoted",
                "DNS updated",
                "Post-checks passed",
            ],
        }

    def test_minimal_event_returns_200(self, minimal_event):
        result = handler(minimal_event, None)
        assert result["statusCode"] == 200
        assert "summary" in result

    def test_summary_contains_event_id(self, minimal_event):
        result = handler(minimal_event, None)
        assert "evt-001" in result["summary"]

    def test_summary_contains_status(self, minimal_event):
        result = handler(minimal_event, None)
        assert "completed" in result["summary"]

    def test_summary_contains_regions(self, minimal_event):
        result = handler(minimal_event, None)
        assert "us-east-1" in result["summary"]
        assert "us-east-2" in result["summary"]

    def test_summary_contains_pre_check_section(self, full_event):
        result = handler(full_event, None)
        summary = result["summary"]
        assert "PRE-CHECK RESULTS" in summary
        assert "replica_health" in summary
        assert "replication_lag" in summary

    def test_summary_contains_failover_steps(self, full_event):
        result = handler(full_event, None)
        summary = result["summary"]
        assert "FAILOVER STEPS" in summary
        assert "Replica Promotion" in summary
        assert "DNS Update" in summary
        assert "makita-dr-replica" in summary

    def test_summary_contains_post_check_section(self, full_event):
        result = handler(full_event, None)
        summary = result["summary"]
        assert "POST-CHECK RESULTS" in summary
        assert "read_write_mode" in summary

    def test_summary_contains_incident_management(self, full_event):
        result = handler(full_event, None)
        summary = result["summary"]
        assert "INCIDENT MANAGEMENT ACTIONS" in summary
        assert "INC0012345" in summary
        assert "case-111222333" in summary
        assert "C0DRCH4NNEL" in summary

    def test_summary_contains_actions_log(self, full_event):
        result = handler(full_event, None)
        summary = result["summary"]
        assert "Actions Log" in summary
        assert "Created Slack channel" in summary
        assert "Replica promoted" in summary

    def test_summary_shows_completed_at(self, full_event):
        result = handler(full_event, None)
        assert "2024-01-15T10:30:00" in result["summary"]

    def test_no_pre_checks_shows_placeholder(self, minimal_event):
        result = handler(minimal_event, None)
        assert "No pre-check results available" in result["summary"]

    def test_no_post_checks_shows_placeholder(self, minimal_event):
        result = handler(minimal_event, None)
        assert "No post-check results available" in result["summary"]

    def test_no_incident_actions_shows_placeholder(self, minimal_event):
        result = handler(minimal_event, None)
        assert "No incident management actions recorded" in result["summary"]

    def test_error_message_included_in_summary(self, minimal_event):
        minimal_event["error_message"] = "Replica promotion timed out"
        result = handler(minimal_event, None)
        summary = result["summary"]
        assert "ERROR" in summary
        assert "Replica promotion timed out" in summary

    def test_failed_event_summary(self):
        event = {
            "event_id": "evt-fail",
            "status": "failed",
            "initiated_at": "2024-01-15T10:00:00",
            "primary_region": "us-east-1",
            "dr_region": "us-east-2",
            "pre_check_result": {
                "overall_status": "failed",
                "checks": [
                    {
                        "check_name": "replica_health",
                        "status": "failed",
                        "message": "Replica unreachable",
                    },
                ],
            },
            "error_message": "Pre-checks failed, failover aborted",
        }
        result = handler(event, None)
        assert result["statusCode"] == 200
        assert "failed" in result["summary"]
        assert "Replica unreachable" in result["summary"]
        assert "Pre-checks failed" in result["summary"]
