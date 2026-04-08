"""Tests for the MAKITA ticketing integration module."""

from orchestrator.ticketing import (
    TicketUpdateContext,
    build_update_description,
    create_tickets,
    update_tickets,
)


# ---------------------------------------------------------------------------
# Helpers — fake tool functions
# ---------------------------------------------------------------------------

def _fake_create_support_case(**kwargs):
    return {"case_id": "makita-case-20240101-001", "subject": kwargs["subject"],
            "status": "opened", "created_at": "2024-01-01T00:00:00Z"}


def _fake_update_support_case(**kwargs):
    return {"case_id": kwargs["case_id"], "status": kwargs["status"],
            "updated_at": "2024-01-01T00:01:00Z", "error": None}


def _fake_create_ticket(**kwargs):
    return {"ticket_id": "INC0000001", "short_description": kwargs["short_description"],
            "status": "New", "created_at": "2024-01-01T00:00:00Z"}


def _fake_update_ticket(**kwargs):
    return {"ticket_id": kwargs["ticket_id"], "status": kwargs["status"],
            "updated_at": "2024-01-01T00:01:00Z", "error": None}


SUPPORT_TOOLS = {
    "create_support_case": _fake_create_support_case,
    "update_support_case": _fake_update_support_case,
}

SNOW_TOOLS = {
    "create_ticket": _fake_create_ticket,
    "update_ticket": _fake_update_ticket,
}


def _sample_context(**overrides) -> TicketUpdateContext:
    defaults = dict(
        phase="failover",
        status="failover initiated",
        resource_names=["makita-pg-primary", "makita-pg-replica"],
        parameter_paths=["/makita/db/primary-endpoint"],
        agentcore_resources=["makita-postgresql-failover-mcp"],
        primary_region="us-east-1",
        dr_region="us-west-2",
        endpoints={"primary": "primary.rds.amazonaws.com", "replica": "replica.rds.amazonaws.com"},
        replication_status="healthy",
        iam_role="makita-failover-role",
        error_code=None,
        error_message=None,
        mcp_server="makita-postgresql-failover-mcp",
    )
    defaults.update(overrides)
    return TicketUpdateContext(**defaults)


# ---------------------------------------------------------------------------
# Tests — build_update_description
# ---------------------------------------------------------------------------

class TestBuildUpdateDescription:

    def test_includes_phase_and_status(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "Phase: failover" in desc
        assert "Status: failover initiated" in desc

    def test_includes_regions(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "Primary Region: us-east-1" in desc
        assert "DR Region: us-west-2" in desc

    def test_includes_mcp_server(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "MCP Server: makita-postgresql-failover-mcp" in desc

    def test_includes_resource_names(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "makita-pg-primary" in desc
        assert "makita-pg-replica" in desc

    def test_includes_parameter_paths(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "/makita/db/primary-endpoint" in desc

    def test_includes_agentcore_resources(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "AgentCore Resources: makita-postgresql-failover-mcp" in desc

    def test_includes_endpoints(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "primary=primary.rds.amazonaws.com" in desc

    def test_includes_replication_status(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "Replication Status: healthy" in desc

    def test_includes_iam_role(self):
        ctx = _sample_context()
        desc = build_update_description(ctx)
        assert "IAM Role: makita-failover-role" in desc

    def test_includes_error_fields_when_present(self):
        ctx = _sample_context(error_code="REPL_FAIL", error_message="Replication lag too high")
        desc = build_update_description(ctx)
        assert "Error Code: REPL_FAIL" in desc
        assert "Error Message: Replication lag too high" in desc

    def test_omits_none_optional_fields(self):
        ctx = _sample_context(
            replication_status=None, iam_role=None,
            error_code=None, error_message=None,
            mcp_server="", resource_names=[], parameter_paths=[],
            agentcore_resources=[], endpoints={},
        )
        desc = build_update_description(ctx)
        assert "Replication Status" not in desc
        assert "IAM Role" not in desc
        assert "Error Code" not in desc
        assert "Error Message" not in desc
        assert "MCP Server" not in desc
        assert "Resources" not in desc
        assert "Parameters" not in desc
        assert "AgentCore" not in desc
        assert "Endpoints" not in desc


# ---------------------------------------------------------------------------
# Tests — create_tickets
# ---------------------------------------------------------------------------

class TestCreateTickets:

    def test_returns_case_and_ticket_ids(self):
        case_id, ticket_id = create_tickets(
            "DR Failover", "Initiating failover",
            support_tools=SUPPORT_TOOLS, servicenow_tools=SNOW_TOOLS,
        )
        assert case_id == "makita-case-20240101-001"
        assert ticket_id == "INC0000001"

    def test_passes_subject_and_description(self):
        captured = {}

        def capturing_create(**kwargs):
            captured.update(kwargs)
            return {"case_id": "c1", "subject": kwargs["subject"],
                    "status": "opened", "created_at": "t"}

        tools = {**SUPPORT_TOOLS, "create_support_case": capturing_create}
        create_tickets("My Subject", "My Desc", support_tools=tools, servicenow_tools=SNOW_TOOLS)
        assert captured["subject"] == "My Subject"
        assert captured["description"] == "My Desc"

    def test_passes_severity_and_priority(self):
        captured_support = {}
        captured_snow = {}

        def cap_support(**kw):
            captured_support.update(kw)
            return {"case_id": "c1", "subject": "", "status": "opened", "created_at": "t"}

        def cap_snow(**kw):
            captured_snow.update(kw)
            return {"ticket_id": "t1", "short_description": "", "status": "New", "created_at": "t"}

        create_tickets(
            "s", "d", severity="high", priority="2-High",
            support_tools={**SUPPORT_TOOLS, "create_support_case": cap_support},
            servicenow_tools={**SNOW_TOOLS, "create_ticket": cap_snow},
        )
        assert captured_support["severity"] == "high"
        assert captured_snow["priority"] == "2-High"
        assert captured_snow["category"] == "Disaster Recovery"


# ---------------------------------------------------------------------------
# Tests — update_tickets
# ---------------------------------------------------------------------------

class TestUpdateTickets:

    def test_calls_both_update_tools(self):
        calls = {"support": False, "snow": False}

        def track_support(**kw):
            calls["support"] = True
            return _fake_update_support_case(**kw)

        def track_snow(**kw):
            calls["snow"] = True
            return _fake_update_ticket(**kw)

        ctx = _sample_context()
        update_tickets(
            "c1", "t1", ctx,
            support_tools={**SUPPORT_TOOLS, "update_support_case": track_support},
            servicenow_tools={**SNOW_TOOLS, "update_ticket": track_snow},
        )
        assert calls["support"] is True
        assert calls["snow"] is True

    def test_passes_context_status(self):
        captured = {}

        def cap(**kw):
            captured.update(kw)
            return _fake_update_support_case(**kw)

        ctx = _sample_context(status="replication verified")
        update_tickets(
            "c1", "t1", ctx,
            support_tools={**SUPPORT_TOOLS, "update_support_case": cap},
            servicenow_tools=SNOW_TOOLS,
        )
        assert captured["status"] == "replication verified"

    def test_description_contains_context_info(self):
        captured = {}

        def cap(**kw):
            captured.update(kw)
            return _fake_update_support_case(**kw)

        ctx = _sample_context(status="failover complete", phase="post-check")
        update_tickets(
            "c1", "t1", ctx,
            support_tools={**SUPPORT_TOOLS, "update_support_case": cap},
            servicenow_tools=SNOW_TOOLS,
        )
        desc = captured["update_description"]
        assert "Phase: post-check" in desc
        assert "Status: failover complete" in desc
        assert "us-east-1" in desc
        assert "us-west-2" in desc

    def test_update_on_error_context(self):
        """Req 13.9/13.10 — failure details included in update."""
        captured = {}

        def cap(**kw):
            captured.update(kw)
            return _fake_update_support_case(**kw)

        ctx = _sample_context(
            phase="pre-check",
            status="pre-check failure",
            error_code="REPL_LAG",
            error_message="Replication lag exceeds threshold",
        )
        update_tickets(
            "c1", "t1", ctx,
            support_tools={**SUPPORT_TOOLS, "update_support_case": cap},
            servicenow_tools=SNOW_TOOLS,
        )
        desc = captured["update_description"]
        assert "REPL_LAG" in desc
        assert "Replication lag exceeds threshold" in desc


# ---------------------------------------------------------------------------
# Tests — TicketUpdateContext dataclass
# ---------------------------------------------------------------------------

class TestTicketUpdateContext:

    def test_defaults(self):
        ctx = TicketUpdateContext(phase="failover", status="initiated")
        assert ctx.resource_names == []
        assert ctx.parameter_paths == []
        assert ctx.agentcore_resources == []
        assert ctx.primary_region == "us-east-1"
        assert ctx.dr_region == "us-west-2"
        assert ctx.endpoints == {}
        assert ctx.replication_status is None
        assert ctx.iam_role is None
        assert ctx.error_code is None
        assert ctx.error_message is None
        assert ctx.mcp_server == ""

    def test_all_fields_settable(self):
        ctx = _sample_context()
        assert ctx.phase == "failover"
        assert ctx.status == "failover initiated"
        assert len(ctx.resource_names) == 2
        assert ctx.mcp_server == "makita-postgresql-failover-mcp"
