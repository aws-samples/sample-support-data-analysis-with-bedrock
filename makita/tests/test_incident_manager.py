"""Unit tests for makita_dr.incident_manager — Slack integration."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from makita_dr.incident_manager import IncidentManager, _determine_pending_actions
from makita_dr.models import (
    CheckStatus,
    DRConfig,
    FailoverEvent,
    FailoverStatus,
    PreCheckResult,
    PromoteResult,
)


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
        slack_bot_token="xoxb-test-token",
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


def _make_event(**overrides) -> FailoverEvent:
    defaults = dict(
        event_id="evt-001",
        status=FailoverStatus.IN_PROGRESS,
        initiated_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        primary_region="us-east-1",
        dr_region="us-east-2",
        primary_instance_id="makita-dr-primary",
        replica_instance_id="makita-dr-replica",
    )
    defaults.update(overrides)
    return FailoverEvent(**defaults)


def _build_manager() -> tuple:
    """Return (IncidentManager, mock_slack_client)."""
    config = _make_config()
    with patch("makita_dr.incident_manager.WebClient") as MockWebClient, \
         patch("makita_dr.incident_manager.boto3") as mock_boto3:
        mock_client = MagicMock()
        MockWebClient.return_value = mock_client
        mock_boto3.client.return_value = MagicMock()
        mgr = IncidentManager(config)
    return mgr, mock_client


# ---------------------------------------------------------------------------
# Tests: create_slack_channel
# ---------------------------------------------------------------------------


class TestCreateSlackChannel:
    def test_creates_channel_with_correct_name(self):
        mgr, mock_client = _build_manager()
        mock_client.conversations_create.return_value = {
            "channel": {"id": "C12345"}
        }

        with patch("makita_dr.incident_manager.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 7, 15, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            channel_id = mgr.create_slack_channel()

        mock_client.conversations_create.assert_called_once_with(
            name="makita-dr-20250715",
            is_private=False,
        )
        assert channel_id == "C12345"

    def test_returns_channel_id(self):
        mgr, mock_client = _build_manager()
        mock_client.conversations_create.return_value = {
            "channel": {"id": "C99999"}
        }

        channel_id = mgr.create_slack_channel()
        assert channel_id == "C99999"


# ---------------------------------------------------------------------------
# Tests: post_slack_message
# ---------------------------------------------------------------------------


class TestPostSlackMessage:
    def test_posts_message_to_channel(self):
        mgr, mock_client = _build_manager()

        mgr.post_slack_message("C12345", "Hello DR team")

        mock_client.chat_postMessage.assert_called_once_with(
            channel="C12345",
            text="Hello DR team",
        )


# ---------------------------------------------------------------------------
# Tests: post_initial_message
# ---------------------------------------------------------------------------


class TestPostInitialMessage:
    def test_message_contains_event_summary(self):
        mgr, mock_client = _build_manager()
        event = _make_event()

        mgr.post_initial_message("C12345", event)

        call_args = mock_client.chat_postMessage.call_args
        message = call_args.kwargs["text"]
        assert "evt-001" in message
        assert "in_progress" in message

    def test_message_contains_affected_resources(self):
        mgr, mock_client = _build_manager()
        event = _make_event()

        mgr.post_initial_message("C12345", event)

        message = mock_client.chat_postMessage.call_args.kwargs["text"]
        assert "makita-dr-primary" in message
        assert "makita-dr-replica" in message

    def test_message_contains_regions(self):
        mgr, mock_client = _build_manager()
        event = _make_event()

        mgr.post_initial_message("C12345", event)

        message = mock_client.chat_postMessage.call_args.kwargs["text"]
        assert "us-east-1" in message
        assert "us-east-2" in message

    def test_message_contains_status(self):
        mgr, mock_client = _build_manager()
        event = _make_event(status=FailoverStatus.NOT_STARTED)

        mgr.post_initial_message("C12345", event)

        message = mock_client.chat_postMessage.call_args.kwargs["text"]
        assert "not_started" in message


# ---------------------------------------------------------------------------
# Tests: log_action
# ---------------------------------------------------------------------------


class TestLogAction:
    def test_logs_action_to_channel(self):
        mgr, mock_client = _build_manager()

        mgr.log_action("C12345", "Pre-checks passed")

        call_args = mock_client.chat_postMessage.call_args
        message = call_args.kwargs["text"]
        assert "Pre-checks passed" in message
        assert "Action Log" in message

    def test_log_includes_timestamp(self):
        mgr, mock_client = _build_manager()

        mgr.log_action("C12345", "Replica promoted")

        message = mock_client.chat_postMessage.call_args.kwargs["text"]
        # ISO timestamp contains 'T' separator
        assert "T" in message


# ---------------------------------------------------------------------------
# Tests: post_status_update
# ---------------------------------------------------------------------------


class TestPostStatusUpdate:
    def test_posts_status_change(self):
        mgr, mock_client = _build_manager()

        mgr.post_status_update("C12345", FailoverStatus.COMPLETED)

        message = mock_client.chat_postMessage.call_args.kwargs["text"]
        assert "completed" in message
        assert "Status Update" in message

    def test_posts_failed_status(self):
        mgr, mock_client = _build_manager()

        mgr.post_status_update("C12345", FailoverStatus.FAILED)

        message = mock_client.chat_postMessage.call_args.kwargs["text"]
        assert "failed" in message


# ---------------------------------------------------------------------------
# Tests: handle_mention / @makita
# ---------------------------------------------------------------------------


class TestHandleMention:
    def test_status_question_returns_status_response(self):
        mgr, mock_client = _build_manager()
        event = _make_event(
            actions_log=["Created Slack channel", "Pre-checks passed"],
        )

        response = mgr.handle_mention("C12345", "What is the DR status?", event)

        assert "in_progress" in response
        assert "Created Slack channel" in response
        assert "Pre-checks passed" in response

    def test_status_response_includes_pending_actions(self):
        mgr, mock_client = _build_manager()
        event = _make_event()  # IN_PROGRESS, no checks done yet

        response = mgr.handle_mention("C12345", "status", event)

        assert "Pending Actions" in response
        assert "pre-failover checks" in response.lower() or "Pre-failover" in response or "pre" in response.lower()

    def test_generic_question_returns_summary(self):
        mgr, mock_client = _build_manager()
        event = _make_event()

        response = mgr.handle_mention("C12345", "What is happening?", event)

        assert "evt-001" in response
        assert "us-east-1" in response

    def test_mention_posts_response_to_channel(self):
        mgr, mock_client = _build_manager()
        event = _make_event()

        mgr.handle_mention("C12345", "status?", event)

        mock_client.chat_postMessage.assert_called_once()
        assert mock_client.chat_postMessage.call_args.kwargs["channel"] == "C12345"

    def test_status_response_shows_completed_steps(self):
        mgr, mock_client = _build_manager()
        event = _make_event(
            status=FailoverStatus.COMPLETED,
            actions_log=["Channel created", "Pre-checks passed", "Replica promoted"],
        )

        response = mgr.handle_mention("C12345", "What is the current status?", event)

        assert "completed" in response
        assert "Channel created" in response
        assert "Pre-checks passed" in response
        assert "Replica promoted" in response

    def test_status_response_no_completed_steps(self):
        mgr, mock_client = _build_manager()
        event = _make_event(status=FailoverStatus.NOT_STARTED)

        response = mgr.handle_mention("C12345", "status", event)

        assert "not_started" in response
        assert "(none)" in response


# ---------------------------------------------------------------------------
# Tests: _determine_pending_actions helper
# ---------------------------------------------------------------------------


class TestDeterminePendingActions:
    def test_not_started_has_all_actions(self):
        event = _make_event(status=FailoverStatus.NOT_STARTED)
        pending = _determine_pending_actions(event)
        assert len(pending) >= 5

    def test_completed_has_no_pending(self):
        event = _make_event(status=FailoverStatus.COMPLETED)
        pending = _determine_pending_actions(event)
        assert pending == []

    def test_failed_has_no_pending(self):
        event = _make_event(status=FailoverStatus.FAILED)
        pending = _determine_pending_actions(event)
        assert pending == []

    def test_in_progress_with_pre_checks_done(self):
        event = _make_event(
            pre_check_result=PreCheckResult(
                checks=[], overall_status=CheckStatus.PASSED
            ),
        )
        pending = _determine_pending_actions(event)
        assert "Run pre-failover checks" not in pending
        assert "Promote read replica" in pending

    def test_in_progress_with_promote_done(self):
        event = _make_event(
            pre_check_result=PreCheckResult(
                checks=[], overall_status=CheckStatus.PASSED
            ),
            promote_result=PromoteResult(
                success=True,
                promoted_instance_id="makita-dr-replica",
                promoted_endpoint="endpoint",
                message="ok",
            ),
        )
        pending = _determine_pending_actions(event)
        assert "Promote read replica" not in pending
        assert "Update DNS" in pending


# ---------------------------------------------------------------------------
# Tests: AWS Support integration via Boto3 against stub server
# ---------------------------------------------------------------------------


def _build_manager_with_support_stub():
    """Return (IncidentManager, AWSSupportStub) wired together.

    Uses the Flask test client to route Boto3 Support API calls to the stub
    without starting a real HTTP server.
    """
    import json as _json
    from io import BytesIO
    from urllib.parse import urlparse as _urlparse

    from botocore.awsrequest import AWSPreparedRequest, AWSResponse

    from makita_dr.aws_support_stub import AWSSupportStub

    stub = AWSSupportStub()
    flask_test_client = stub.app.test_client()

    config = _make_config()

    # We need a real Boto3 Support client pointed at a dummy endpoint.
    # Then we monkey-patch the HTTP layer to route to the Flask test client.
    with patch("makita_dr.incident_manager.WebClient") as MockWebClient:
        mock_slack = MagicMock()
        MockWebClient.return_value = mock_slack
        mgr = IncidentManager(config, support_endpoint_url="http://localhost:8081")

    # Monkey-patch the underlying HTTP sender on the Boto3 client
    original_send = mgr._support_client._endpoint.http_session.send

    def _flask_send(request, **kwargs):
        """Route the Boto3 HTTP request to the Flask test client."""
        headers = {
            k: (v.decode("utf-8") if isinstance(v, bytes) else v)
            for k, v in dict(request.headers).items()
        }
        data = request.body or b""
        if isinstance(data, str):
            data = data.encode("utf-8")

        rv = flask_test_client.post(
            "/",
            data=data,
            content_type=headers.get("Content-Type", "application/x-amz-json-1.1"),
            headers=headers,
        )

        # Build an AWSResponse that botocore expects
        from urllib3.response import HTTPResponse as Urllib3Response

        raw = Urllib3Response(
            body=BytesIO(rv.data),
            headers=dict(rv.headers),
            status=rv.status_code,
            preload_content=False,
        )
        response = AWSResponse(
            url="http://localhost:8081/",
            status_code=rv.status_code,
            headers=dict(rv.headers),
            raw=raw,
        )
        return response

    mgr._support_client._endpoint.http_session.send = _flask_send

    return mgr, stub


class TestCreateSupportTicket:
    """Validates: Requirements 6.2, 6.3, 6.4"""

    def test_returns_case_id(self):
        mgr, stub = _build_manager_with_support_stub()
        event_summary = {
            "summary": "DR failover initiated",
            "affected_resources": "makita-dr-primary, makita-dr-replica",
            "primary_region": "us-east-1",
            "dr_region": "us-east-2",
            "timestamp": "2025-01-15T10:00:00+00:00",
        }

        case_id = mgr.create_support_ticket(event_summary)

        assert case_id is not None
        assert case_id.startswith("case-")

    def test_ticket_contains_event_summary(self):
        mgr, stub = _build_manager_with_support_stub()
        event_summary = {
            "summary": "RDS failover from us-east-1 to us-east-2",
            "affected_resources": "makita-dr-primary, makita-dr-replica",
            "primary_region": "us-east-1",
            "dr_region": "us-east-2",
        }

        mgr.create_support_ticket(event_summary)

        log = stub.get_request_log()
        assert len(log) == 1
        body = log[0]["body"]
        assert "RDS failover" in body.get("communicationBody", "")
        assert "RDS failover" in body.get("subject", "")

    def test_ticket_contains_affected_resources(self):
        mgr, stub = _build_manager_with_support_stub()
        event_summary = {
            "summary": "DR failover",
            "affected_resources": "makita-dr-primary, makita-dr-replica",
            "primary_region": "us-east-1",
            "dr_region": "us-east-2",
        }

        mgr.create_support_ticket(event_summary)

        log = stub.get_request_log()
        body = log[0]["body"]
        comm_body = body.get("communicationBody", "")
        assert "makita-dr-primary" in comm_body
        assert "makita-dr-replica" in comm_body

    def test_ticket_contains_regions(self):
        mgr, stub = _build_manager_with_support_stub()
        event_summary = {
            "summary": "DR failover",
            "affected_resources": "db-primary",
            "primary_region": "us-east-1",
            "dr_region": "us-east-2",
        }

        mgr.create_support_ticket(event_summary)

        log = stub.get_request_log()
        body = log[0]["body"]
        comm_body = body.get("communicationBody", "")
        assert "us-east-1" in comm_body
        assert "us-east-2" in comm_body

    def test_ticket_contains_severity(self):
        mgr, stub = _build_manager_with_support_stub()
        event_summary = {
            "summary": "DR failover",
            "affected_resources": "db-primary",
        }

        mgr.create_support_ticket(event_summary)

        log = stub.get_request_log()
        body = log[0]["body"]
        assert body.get("severityCode") == "high"

    def test_ticket_contains_service_and_category(self):
        mgr, stub = _build_manager_with_support_stub()
        event_summary = {
            "summary": "DR failover",
            "affected_resources": "db-primary",
        }

        mgr.create_support_ticket(event_summary)

        log = stub.get_request_log()
        body = log[0]["body"]
        assert body.get("serviceCode") == "amazon-rds"
        assert body.get("categoryCode") == "failover"

    def test_stub_logs_create_request(self):
        """Validates: Requirement 6.6 — stub logs all API calls."""
        mgr, stub = _build_manager_with_support_stub()
        event_summary = {
            "summary": "test",
            "affected_resources": "db",
        }

        mgr.create_support_ticket(event_summary)

        log = stub.get_request_log()
        assert len(log) == 1
        assert log[0]["operation"] == "CreateCase"


class TestUpdateSupportTicket:
    """Validates: Requirements 6.2, 6.5"""

    def test_updates_ticket_with_completed_status(self):
        mgr, stub = _build_manager_with_support_stub()
        # Create a ticket first
        case_id = mgr.create_support_ticket({
            "summary": "DR failover",
            "affected_resources": "db",
        })

        # Update with completed status
        mgr.update_support_ticket(case_id, "completed")

        log = stub.get_request_log()
        assert len(log) == 2
        update_entry = log[1]
        assert update_entry["operation"] == "AddCommunicationToCase"
        assert "completed" in update_entry["body"].get("communicationBody", "")

    def test_updates_ticket_with_failed_status(self):
        mgr, stub = _build_manager_with_support_stub()
        case_id = mgr.create_support_ticket({
            "summary": "DR failover",
            "affected_resources": "db",
        })

        mgr.update_support_ticket(case_id, "failed")

        log = stub.get_request_log()
        update_entry = log[1]
        assert "failed" in update_entry["body"].get("communicationBody", "")

    def test_update_references_correct_case_id(self):
        mgr, stub = _build_manager_with_support_stub()
        case_id = mgr.create_support_ticket({
            "summary": "DR failover",
            "affected_resources": "db",
        })

        mgr.update_support_ticket(case_id, "completed")

        log = stub.get_request_log()
        update_entry = log[1]
        assert update_entry["body"].get("caseId") == case_id

    def test_stub_logs_update_request(self):
        """Validates: Requirement 6.6 — stub logs all API calls."""
        mgr, stub = _build_manager_with_support_stub()
        case_id = mgr.create_support_ticket({
            "summary": "test",
            "affected_resources": "db",
        })

        mgr.update_support_ticket(case_id, "completed")

        log = stub.get_request_log()
        assert len(log) == 2
        assert log[0]["operation"] == "CreateCase"
        assert log[1]["operation"] == "AddCommunicationToCase"


# ---------------------------------------------------------------------------
# Tests: ServiceNow integration via pysnow against stub server
# ---------------------------------------------------------------------------


def _build_manager_with_snow_stub():
    """Return (IncidentManager, ServiceNowStubServer) wired together.

    The pysnow client's session is replaced with a custom adapter that
    routes HTTP requests to the Flask test client, so no real server is needed.
    """
    import json as _json
    from urllib.parse import urlparse as _urlparse

    from requests.models import Response

    from makita_dr.servicenow_stub import ServiceNowStubServer

    stub = ServiceNowStubServer()
    flask_test_client = stub.app.test_client()

    config = _make_config(servicenow_endpoint="http://localhost:8080")

    with patch("makita_dr.incident_manager.WebClient") as MockWebClient:
        mock_slack = MagicMock()
        MockWebClient.return_value = mock_slack
        with patch("makita_dr.incident_manager.boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()
            mgr = IncidentManager(config)

    # Replace the pysnow session's send method so requests go to the Flask
    # test client instead of making real HTTP calls.
    original_session = mgr._snow_client.session

    def _flask_send(prepared_request, **kwargs):
        """Translate a prepared request into a Flask test-client call."""
        from io import BytesIO

        parsed = _urlparse(prepared_request.url)
        path = parsed.path
        method = prepared_request.method.upper()
        data = prepared_request.body
        headers = dict(prepared_request.headers)

        if method == "POST":
            rv = flask_test_client.post(
                path, data=data, content_type="application/json", headers=headers,
            )
        elif method in ("PATCH", "PUT"):
            rv = flask_test_client.put(
                path, data=data, content_type="application/json", headers=headers,
            )
        elif method == "GET":
            rv = flask_test_client.get(path, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        resp = Response()
        resp.status_code = rv.status_code
        resp._content = rv.data
        resp.headers.update(dict(rv.headers))
        resp.encoding = "utf-8"
        # pysnow accesses response.raw.decode_content — provide a real raw object
        resp.raw = BytesIO(rv.data)
        resp.raw.decode_content = True
        # pysnow accesses response.request.method
        resp.request = prepared_request
        return resp

    original_session.send = _flask_send

    return mgr, stub


class TestCreateServiceNowTicket:
    """Validates: Requirements 4.2, 4.3, 4.4"""

    def test_returns_sys_id(self):
        mgr, stub = _build_manager_with_snow_stub()
        event_summary = {
            "summary": "DR failover initiated",
            "affected_resources": "makita-dr-primary, makita-dr-replica",
            "timestamp": "2025-01-15T10:00:00+00:00",
            "status": "in-progress",
        }

        sys_id = mgr.create_servicenow_ticket(event_summary)

        assert sys_id is not None
        assert len(sys_id) > 0

    def test_ticket_contains_summary(self):
        mgr, stub = _build_manager_with_snow_stub()
        event_summary = {
            "summary": "RDS failover from us-east-1 to us-east-2",
            "affected_resources": "makita-dr-primary, makita-dr-replica",
            "timestamp": "2025-01-15T10:00:00+00:00",
        }

        sys_id = mgr.create_servicenow_ticket(event_summary)

        # Verify the stub recorded the request with the correct fields
        log = stub.get_request_log()
        assert len(log) == 1
        body = log[0]["body"]
        assert "RDS failover" in body["short_description"]
        assert "makita-dr-primary" in body["description"]

    def test_ticket_contains_affected_resources(self):
        mgr, stub = _build_manager_with_snow_stub()
        event_summary = {
            "summary": "DR failover",
            "affected_resources": "makita-dr-primary, makita-dr-replica",
            "timestamp": "2025-01-15T10:00:00+00:00",
        }

        mgr.create_servicenow_ticket(event_summary)

        log = stub.get_request_log()
        body = log[0]["body"]
        assert "makita-dr-primary" in body["u_affected_resources"]
        assert "makita-dr-replica" in body["u_affected_resources"]

    def test_ticket_contains_timestamp(self):
        mgr, stub = _build_manager_with_snow_stub()
        event_summary = {
            "summary": "DR failover",
            "affected_resources": "db-primary",
            "timestamp": "2025-01-15T10:00:00+00:00",
        }

        mgr.create_servicenow_ticket(event_summary)

        log = stub.get_request_log()
        body = log[0]["body"]
        assert body["u_event_timestamp"] == "2025-01-15T10:00:00+00:00"

    def test_ticket_contains_status(self):
        mgr, stub = _build_manager_with_snow_stub()
        event_summary = {
            "summary": "DR failover",
            "affected_resources": "db-primary",
            "timestamp": "2025-01-15T10:00:00+00:00",
            "status": "in-progress",
        }

        mgr.create_servicenow_ticket(event_summary)

        log = stub.get_request_log()
        body = log[0]["body"]
        assert body["state"] == "in-progress"

    def test_stub_logs_create_request(self):
        """Validates: Requirement 4.6 — stub logs all requests."""
        mgr, stub = _build_manager_with_snow_stub()
        event_summary = {"summary": "test", "affected_resources": "db", "timestamp": "now"}

        mgr.create_servicenow_ticket(event_summary)

        log = stub.get_request_log()
        assert len(log) == 1
        assert log[0]["method"] == "POST"
        assert "/api/now/table/incident" in log[0]["path"]


class TestUpdateServiceNowTicket:
    """Validates: Requirements 4.2, 4.5"""

    def test_updates_ticket_status(self):
        mgr, stub = _build_manager_with_snow_stub()
        # First create a ticket
        sys_id = mgr.create_servicenow_ticket({
            "summary": "DR failover",
            "affected_resources": "db",
            "timestamp": "now",
            "status": "in-progress",
        })

        # Now update it
        mgr.update_servicenow_ticket(sys_id, "completed", {"resolution": "Failover successful"})

        log = stub.get_request_log()
        # pysnow update does: POST (create) + GET (query) + PUT (update)
        assert len(log) == 3
        put_entry = [e for e in log if e["method"] == "PUT"][0]
        assert put_entry["body"]["state"] == "completed"

    def test_update_includes_details_in_work_notes(self):
        mgr, stub = _build_manager_with_snow_stub()
        sys_id = mgr.create_servicenow_ticket({
            "summary": "DR failover",
            "affected_resources": "db",
            "timestamp": "now",
        })

        mgr.update_servicenow_ticket(sys_id, "failed", {"error": "Timeout during promotion"})

        log = stub.get_request_log()
        put_entry = [e for e in log if e["method"] == "PUT"][0]
        body = put_entry["body"]
        assert "failed" in body["work_notes"]
        assert "Timeout during promotion" in body["work_notes"]

    def test_update_merges_extra_detail_fields(self):
        mgr, stub = _build_manager_with_snow_stub()
        sys_id = mgr.create_servicenow_ticket({
            "summary": "DR failover",
            "affected_resources": "db",
            "timestamp": "now",
        })

        mgr.update_servicenow_ticket(sys_id, "completed", {"close_code": "Resolved"})

        log = stub.get_request_log()
        put_entry = [e for e in log if e["method"] == "PUT"][0]
        body = put_entry["body"]
        assert body["close_code"] == "Resolved"

    def test_stub_logs_update_request(self):
        """Validates: Requirement 4.6 — stub logs all requests."""
        mgr, stub = _build_manager_with_snow_stub()
        sys_id = mgr.create_servicenow_ticket({
            "summary": "test",
            "affected_resources": "db",
            "timestamp": "now",
        })

        mgr.update_servicenow_ticket(sys_id, "completed", {})

        log = stub.get_request_log()
        # POST + GET + PUT = 3 entries
        assert len(log) == 3
        put_entry = [e for e in log if e["method"] == "PUT"][0]
        assert sys_id in put_entry["path"]
