"""Unit tests for the DRMCPServer MCP server."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from makita_dr.mcp_server import COGNITO_RESTRICTED_ACTIONS, TOOL_DEFINITIONS, DRMCPServer
from makita_dr.models import DRConfig


@pytest.fixture
def config():
    return DRConfig(
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
        slack_workspace_id="T12345",
        support_severity="high",
        support_service_code="amazon-rds",
        support_category_code="failover",
        mcp_server_endpoint="http://localhost:9000",
        lambda_function_arn="arn:aws:lambda:us-east-1:123456789012:function:makita-dr-summary",
        guardrail_id="gr-test-001",
        guardrail_version="1",
        cognito_user_pool_id="us-east-1_TestPool",
        cognito_client_id="test-client-id",
    )


@pytest.fixture
def mock_clients():
    return {
        "lambda_client": MagicMock(),
        "bedrock_runtime_client": MagicMock(),
        "cognito_client": MagicMock(),
    }


@pytest.fixture
def server(config, mock_clients):
    return DRMCPServer(
        config=config,
        lambda_client=mock_clients["lambda_client"],
        bedrock_runtime_client=mock_clients["bedrock_runtime_client"],
        cognito_client=mock_clients["cognito_client"],
    )


def _allow_guardrail(mock_clients):
    """Configure the bedrock client to allow the guardrail check."""
    mock_clients["bedrock_runtime_client"].apply_guardrail.return_value = {
        "action": "NONE",
    }


def _block_guardrail(mock_clients):
    """Configure the bedrock client to block via guardrail."""
    mock_clients["bedrock_runtime_client"].apply_guardrail.return_value = {
        "action": "GUARDRAIL_INTERVENED",
        "outputs": [{"text": "Blocked by policy"}],
        "assessments": [{"topicPolicy": {"topics": [{"name": "blocked"}]}}],
    }


def _authenticate_user(mock_clients, username="testuser"):
    """Configure cognito client to return a valid user."""
    mock_clients["cognito_client"].get_user.return_value = {
        "Username": username,
        "UserAttributes": [
            {"Name": "sub", "Value": "user-sub-123"},
            {"Name": "email", "Value": "test@example.com"},
        ],
    }


def _make_lambda_success(mock_clients, summary="DR summary text"):
    """Configure lambda client to return a successful summary."""
    payload = json.dumps({"statusCode": 200, "summary": summary}).encode()
    mock_clients["lambda_client"].invoke.return_value = {
        "Payload": io.BytesIO(payload),
    }


def _make_lambda_error(mock_clients, error_msg="Lambda failed"):
    """Configure lambda client to return an error response."""
    payload = json.dumps({"statusCode": 400, "error": error_msg}).encode()
    mock_clients["lambda_client"].invoke.return_value = {
        "Payload": io.BytesIO(payload),
    }


class TestListTools:
    """Tests for tool listing / discovery."""

    def test_list_tools_returns_tool_definitions(self, server):
        tools = server.list_tools()
        assert len(tools) == len(TOOL_DEFINITIONS)
        assert tools[0]["name"] == "generate_failover_summary"

    def test_list_tools_returns_copy(self, server):
        tools = server.list_tools()
        tools.clear()
        assert len(server.list_tools()) == len(TOOL_DEFINITIONS)

    def test_tool_has_required_fields(self, server):
        tools = server.list_tools()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool


class TestGuardrailsEnforcement:
    """Tests for Bedrock Guardrails evaluation (Req 8.1, 8.2, 8.3)."""

    def test_guardrail_allowed_proceeds(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_success(mock_clients)

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "evt-1", "status": "completed", "initiated_at": "2024-01-01"}},
            auth_token="valid-token",
        )
        assert result["status"] == "success"

    def test_guardrail_blocked_rejects(self, server, mock_clients):
        _block_guardrail(mock_clients)

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {}},
            auth_token="valid-token",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "guardrail_violation"
        assert "Guardrail policy" in result["message"]

    def test_guardrail_exception_fails_closed(self, server, mock_clients):
        mock_clients["bedrock_runtime_client"].apply_guardrail.side_effect = Exception("Service error")

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {}},
            auth_token="valid-token",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "guardrail_violation"

    def test_guardrail_evaluation_logged(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_success(mock_clients)

        server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "e", "status": "ok", "initiated_at": "now"}},
            auth_token="tok",
        )
        guardrail_logs = [e for e in server.audit_log if e["event_type"] == "guardrail_evaluation"]
        assert len(guardrail_logs) == 1
        assert guardrail_logs[0]["action"] == "ALLOWED"

    def test_guardrail_blocked_logged(self, server, mock_clients):
        _block_guardrail(mock_clients)

        server.invoke_tool("generate_failover_summary", {"event_data": {}}, auth_token="tok")
        guardrail_logs = [e for e in server.audit_log if e["event_type"] == "guardrail_evaluation"]
        assert len(guardrail_logs) == 1
        assert guardrail_logs[0]["action"] == "BLOCKED"


class TestAuthentication:
    """Tests for Cognito authentication (Req 9.1, 9.2, 9.6)."""

    def test_no_token_returns_auth_error(self, server, mock_clients):
        _allow_guardrail(mock_clients)

        result = server.invoke_tool("generate_failover_summary", {"event_data": {}})
        assert result["status"] == "error"
        assert result["error_type"] == "authentication_error"

    def test_none_token_returns_auth_error(self, server, mock_clients):
        _allow_guardrail(mock_clients)

        result = server.invoke_tool("generate_failover_summary", {"event_data": {}}, auth_token=None)
        assert result["status"] == "error"
        assert result["error_type"] == "authentication_error"

    def test_invalid_token_returns_auth_error(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        mock_clients["cognito_client"].get_user.side_effect = Exception("Token is invalid")

        result = server.invoke_tool("generate_failover_summary", {"event_data": {}}, auth_token="bad-token")
        assert result["status"] == "error"
        assert result["error_type"] == "authentication_error"

    def test_valid_token_authenticates(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients, username="dr-admin")
        _make_lambda_success(mock_clients)

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "e", "status": "ok", "initiated_at": "now"}},
            auth_token="valid-token",
        )
        assert result["status"] == "success"

    def test_auth_rejection_logged(self, server, mock_clients):
        _allow_guardrail(mock_clients)

        server.invoke_tool("generate_failover_summary", {"event_data": {}})
        auth_logs = [e for e in server.audit_log if e["event_type"] == "authentication"]
        assert len(auth_logs) == 1
        assert auth_logs[0]["result"] == "rejected"

    def test_auth_success_logged(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients, username="admin")
        _make_lambda_success(mock_clients)

        server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "e", "status": "ok", "initiated_at": "now"}},
            auth_token="tok",
        )
        auth_logs = [e for e in server.audit_log if e["event_type"] == "authentication"]
        assert len(auth_logs) == 1
        assert auth_logs[0]["result"] == "authenticated"
        assert auth_logs[0]["username"] == "admin"


class TestAuthorization:
    """Tests for AgentCore Policy authorization (Req 9.3, 9.4, 9.5, 9.6)."""

    def test_cognito_identity_authorized_for_lambda_tool(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_success(mock_clients)

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "e", "status": "ok", "initiated_at": "now"}},
            auth_token="tok",
        )
        assert result["status"] == "success"

    def test_non_cognito_identity_denied_for_lambda_tool(self, server, mock_clients):
        """An identity without cognito auth_source should be denied for restricted tools."""
        _allow_guardrail(mock_clients)
        # Simulate a user that authenticates but with a non-cognito source
        # We do this by patching _authenticate to return a non-cognito identity
        server._authenticate = MagicMock(return_value={
            "username": "api-user",
            "auth_source": "api_key",
        })

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {}},
            auth_token="tok",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "authorization_error"

    def test_authorization_decision_logged(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_success(mock_clients)

        server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "e", "status": "ok", "initiated_at": "now"}},
            auth_token="tok",
        )
        auth_z_logs = [e for e in server.audit_log if e["event_type"] == "authorization"]
        assert len(auth_z_logs) == 1
        assert auth_z_logs[0]["result"] == "authorized"

    def test_authorization_denial_logged(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        server._authenticate = MagicMock(return_value={
            "username": "api-user",
            "auth_source": "api_key",
        })

        server.invoke_tool("generate_failover_summary", {"event_data": {}}, auth_token="tok")
        auth_z_logs = [e for e in server.audit_log if e["event_type"] == "authorization"]
        assert len(auth_z_logs) == 1
        assert auth_z_logs[0]["result"] == "denied"


class TestGenerateFailoverSummary:
    """Tests for Lambda invocation and summary generation (Req 7.1, 7.2, 7.5, 7.6)."""

    def test_successful_summary_generation(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_success(mock_clients, summary="Full DR summary")

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "evt-1", "status": "completed", "initiated_at": "2024-01-01"}},
            auth_token="tok",
        )
        assert result["status"] == "success"
        assert result["summary"] == "Full DR summary"

    def test_lambda_invoked_with_correct_arn(self, server, mock_clients, config):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_success(mock_clients)

        event_data = {"event_id": "evt-1", "status": "completed", "initiated_at": "2024-01-01"}
        server.invoke_tool("generate_failover_summary", {"event_data": event_data}, auth_token="tok")

        mock_clients["lambda_client"].invoke.assert_called_once_with(
            FunctionName=config.lambda_function_arn,
            InvocationType="RequestResponse",
            Payload=json.dumps(event_data),
        )

    def test_lambda_error_response_returned(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_error(mock_clients, error_msg="Missing required fields: event_id")

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {}},
            auth_token="tok",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "lambda_error"
        assert "Missing required fields" in result["message"]

    def test_lambda_invocation_exception(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        mock_clients["lambda_client"].invoke.side_effect = Exception("Network timeout")

        result = server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "e", "status": "ok", "initiated_at": "now"}},
            auth_token="tok",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "lambda_invocation_error"
        assert "Network timeout" in result["message"]

    def test_unknown_tool_returns_error(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)

        result = server.invoke_tool("nonexistent_tool", {}, auth_token="tok")
        assert result["status"] == "error"
        assert result["error_type"] == "unknown_tool"


class TestAuditLog:
    """Tests for audit logging completeness (Req 8.3, 9.6)."""

    def test_full_invocation_logs_all_steps(self, server, mock_clients):
        _allow_guardrail(mock_clients)
        _authenticate_user(mock_clients)
        _make_lambda_success(mock_clients)

        server.invoke_tool(
            "generate_failover_summary",
            {"event_data": {"event_id": "e", "status": "ok", "initiated_at": "now"}},
            auth_token="tok",
        )
        log_types = [e["event_type"] for e in server.audit_log]
        assert "guardrail_evaluation" in log_types
        assert "authentication" in log_types
        assert "authorization" in log_types

    def test_blocked_guardrail_only_logs_guardrail(self, server, mock_clients):
        _block_guardrail(mock_clients)

        server.invoke_tool("generate_failover_summary", {"event_data": {}}, auth_token="tok")
        log_types = [e["event_type"] for e in server.audit_log]
        assert "guardrail_evaluation" in log_types
        # Should not reach auth steps
        assert "authentication" not in log_types
        assert "authorization" not in log_types

    def test_auth_failure_logs_guardrail_and_auth(self, server, mock_clients):
        _allow_guardrail(mock_clients)

        server.invoke_tool("generate_failover_summary", {"event_data": {}})
        log_types = [e["event_type"] for e in server.audit_log]
        assert "guardrail_evaluation" in log_types
        assert "authentication" in log_types
        assert "authorization" not in log_types

    def test_audit_log_returns_copy(self, server):
        log = server.audit_log
        log.append({"fake": True})
        assert len(server.audit_log) == 0
