"""Tests for the MAKITA Stub MCP Servers: AWS Support Stub and ServiceNow Stub.

Validates Requirements 23.7, 23.8 — stub server functionality including
case/ticket creation, updates, and not-found error handling.

The stub servers use in-memory stores and do not require boto3 mocking.
Modules are imported via importlib because the directories use hyphens.
"""

from __future__ import annotations

import importlib

import pytest

# ---------------------------------------------------------------------------
# Import stub server modules via importlib (hyphenated directory names).
# ---------------------------------------------------------------------------

_aws_support_mod = importlib.import_module("mcp-servers.aws-support-stub.server")
_servicenow_mod = importlib.import_module("mcp-servers.servicenow-stub.server")


# ---------------------------------------------------------------------------
# Fixtures — reset global state between tests to avoid pollution.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_aws_support_state():
    """Clear the AWS Support stub in-memory store before each test."""
    _aws_support_mod.support_cases.clear()
    _aws_support_mod._case_seq = 0
    yield
    _aws_support_mod.support_cases.clear()
    _aws_support_mod._case_seq = 0


@pytest.fixture(autouse=True)
def _reset_servicenow_state():
    """Clear the ServiceNow stub in-memory store before each test."""
    _servicenow_mod.tickets.clear()
    _servicenow_mod._ticket_seq = 0
    yield
    _servicenow_mod.tickets.clear()
    _servicenow_mod._ticket_seq = 0


# ============================================================================
# AWS Support Stub Server Tests (Requirement 23.7)
# ============================================================================


class TestCreateSupportCase:
    """create_support_case tool — case creation."""

    def test_returns_unique_case_id(self):
        result = _aws_support_mod.create_support_case(
            subject="DR failover",
            description="Initiating disaster recovery",
            severity="critical",
        )
        assert "case_id" in result
        assert result["case_id"].startswith("makita-case-")

    def test_returns_opened_status(self):
        result = _aws_support_mod.create_support_case(
            subject="DR failover",
            description="Initiating disaster recovery",
            severity="critical",
        )
        assert result["status"] == "opened"
        assert result["subject"] == "DR failover"
        assert "created_at" in result

    def test_case_stored_in_memory(self):
        result = _aws_support_mod.create_support_case(
            subject="Test case",
            description="desc",
            severity="high",
        )
        assert result["case_id"] in _aws_support_mod.support_cases

    def test_sequential_ids_are_unique(self):
        r1 = _aws_support_mod.create_support_case(
            subject="Case 1", description="d1", severity="low",
        )
        r2 = _aws_support_mod.create_support_case(
            subject="Case 2", description="d2", severity="low",
        )
        assert r1["case_id"] != r2["case_id"]


class TestUpdateSupportCase:
    """update_support_case tool — case update."""

    def test_update_returns_new_status(self):
        created = _aws_support_mod.create_support_case(
            subject="DR failover",
            description="desc",
            severity="critical",
        )
        result = _aws_support_mod.update_support_case(
            case_id=created["case_id"],
            status="failover initiated",
            update_description="Starting failover sequence",
        )
        assert result["case_id"] == created["case_id"]
        assert result["status"] == "failover initiated"
        assert "updated_at" in result
        assert result["error"] is None

    def test_update_appends_to_updates_list(self):
        created = _aws_support_mod.create_support_case(
            subject="DR failover",
            description="desc",
            severity="critical",
        )
        _aws_support_mod.update_support_case(
            case_id=created["case_id"],
            status="replication verified",
            update_description="Replication is healthy",
        )
        case = _aws_support_mod.support_cases[created["case_id"]]
        assert len(case.updates) == 1
        assert case.updates[0].status == "replication verified"


class TestUpdateSupportCaseNotFound:
    """update_support_case tool — not-found error."""

    def test_nonexistent_case_returns_error(self):
        result = _aws_support_mod.update_support_case(
            case_id="makita-case-00000000-999",
            status="failover initiated",
            update_description="Should fail",
        )
        assert "error" in result
        assert result["error"]["code"] == "CASE_NOT_FOUND"
        assert "not found" in result["error"]["message"]


# ============================================================================
# ServiceNow Stub Server Tests (Requirement 23.8)
# ============================================================================


class TestCreateTicket:
    """create_ticket tool — ticket creation."""

    def test_returns_unique_ticket_id(self):
        result = _servicenow_mod.create_ticket(
            short_description="DR failover",
            description="Initiating disaster recovery",
            priority="1-Critical",
            category="Disaster Recovery",
        )
        assert "ticket_id" in result
        assert result["ticket_id"].startswith("INC")

    def test_returns_new_status(self):
        result = _servicenow_mod.create_ticket(
            short_description="DR failover",
            description="desc",
            priority="1-Critical",
            category="Disaster Recovery",
        )
        assert result["status"] == "New"
        assert result["short_description"] == "DR failover"
        assert "created_at" in result

    def test_ticket_stored_in_memory(self):
        result = _servicenow_mod.create_ticket(
            short_description="Test",
            description="desc",
            priority="2-High",
            category="Disaster Recovery",
        )
        assert result["ticket_id"] in _servicenow_mod.tickets

    def test_sequential_ids_are_unique(self):
        r1 = _servicenow_mod.create_ticket(
            short_description="T1", description="d1",
            priority="3-Medium", category="DR",
        )
        r2 = _servicenow_mod.create_ticket(
            short_description="T2", description="d2",
            priority="3-Medium", category="DR",
        )
        assert r1["ticket_id"] != r2["ticket_id"]


class TestUpdateTicket:
    """update_ticket tool — ticket update."""

    def test_update_returns_new_status(self):
        created = _servicenow_mod.create_ticket(
            short_description="DR failover",
            description="desc",
            priority="1-Critical",
            category="Disaster Recovery",
        )
        result = _servicenow_mod.update_ticket(
            ticket_id=created["ticket_id"],
            status="In Progress",
            work_notes="Failover sequence started",
        )
        assert result["ticket_id"] == created["ticket_id"]
        assert result["status"] == "In Progress"
        assert "updated_at" in result
        assert result["error"] is None

    def test_update_appends_work_note(self):
        created = _servicenow_mod.create_ticket(
            short_description="DR failover",
            description="desc",
            priority="1-Critical",
            category="Disaster Recovery",
        )
        _servicenow_mod.update_ticket(
            ticket_id=created["ticket_id"],
            status="In Progress",
            work_notes="Replication verified",
        )
        ticket = _servicenow_mod.tickets[created["ticket_id"]]
        assert len(ticket.work_notes) == 1
        assert ticket.work_notes[0].status == "In Progress"
        assert ticket.work_notes[0].notes == "Replication verified"


class TestUpdateTicketNotFound:
    """update_ticket tool — not-found error."""

    def test_nonexistent_ticket_returns_error(self):
        result = _servicenow_mod.update_ticket(
            ticket_id="INC9999999",
            status="In Progress",
            work_notes="Should fail",
        )
        assert "error" in result
        assert result["error"]["code"] == "TICKET_NOT_FOUND"
        assert "not found" in result["error"]["message"]
