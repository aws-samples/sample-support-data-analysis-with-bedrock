"""Tests for the MAKITA event integration module (orchestrator/event_integration.py).

Validates that run_failover_with_logging correctly wires together
ticketing, event logging, and the failover sequence.
"""

from orchestrator.event_integration import run_failover_with_logging


# ---------------------------------------------------------------------------
# Helpers — fake tool functions
# ---------------------------------------------------------------------------

def _passing_precheck(**kwargs):
    return {"check_name": "test_check", "passed": True, "details": {}, "error": None}


def _failing_precheck(**kwargs):
    return {"check_name": "test_check", "passed": False, "details": {}, "error": "check failed"}


def _passing_failover(**kwargs):
    return {
        "success": True,
        "new_primary_endpoint": "replica.us-west-2.rds.amazonaws.com",
        "previous_primary_endpoint": "primary.us-east-1.rds.amazonaws.com",
        "failover_duration_seconds": 12.5,
        "endpoints_updated": True,
        "error": None,
    }


def _passing_postcheck(**kwargs):
    return {"check_name": "test_post", "passed": True, "details": {}, "error": None}


def _make_precheck_tools(verify_replication=None, verify_primary=None, verify_replica=None):
    return {
        "verify_replication_health": verify_replication or _passing_precheck,
        "verify_primary_status": verify_primary or _passing_precheck,
        "verify_replica_readiness": verify_replica or _passing_precheck,
    }


def _make_failover_tools(execute=None):
    return {"execute_failover": execute or _passing_failover}


def _make_postcheck_tools(health=None, endpoints=None, replication=None):
    return {
        "verify_new_primary_health": health or _passing_postcheck,
        "verify_endpoints": endpoints or _passing_postcheck,
        "verify_replication_established": replication or _passing_postcheck,
    }


# Fake support / servicenow tools
_CASE_SEQ = 0
_TICKET_SEQ = 0


def _make_support_tools():
    updates = []

    def create(**kwargs):
        global _CASE_SEQ
        _CASE_SEQ += 1
        return {"case_id": f"makita-case-test-{_CASE_SEQ:03d}"}

    def update(**kwargs):
        updates.append(kwargs)
        return {"case_id": kwargs["case_id"], "status": kwargs["status"]}

    return {"create_support_case": create, "update_support_case": update}, updates


def _make_servicenow_tools():
    updates = []

    def create(**kwargs):
        global _TICKET_SEQ
        _TICKET_SEQ += 1
        return {"ticket_id": f"INC{_TICKET_SEQ:07d}"}

    def update(**kwargs):
        updates.append(kwargs)
        return {"ticket_id": kwargs["ticket_id"], "status": kwargs["status"]}

    return {"create_ticket": create, "update_ticket": update}, updates


# Fake event logger module
class FakeEventLogger:
    def __init__(self):
        self.created = []   # list of (identifier, initial_event)
        self.appended = []  # list of (identifier, event_description)

    def create_event_log(self, identifier, initial_event):
        self.created.append((identifier, initial_event))
        return f"/fake/event-log-{identifier}.md"

    def append_event(self, identifier, event_description):
        self.appended.append((identifier, event_description))


CLUSTER = "makita-pg-cluster"
PRIMARY = "us-east-1"
DR = "us-west-2"


def _run_happy_path():
    """Helper that runs a full successful failover with all fakes."""
    support, s_updates = _make_support_tools()
    snow, sn_updates = _make_servicenow_tools()
    logger = FakeEventLogger()

    result = run_failover_with_logging(
        cluster_name=CLUSTER,
        primary_region=PRIMARY,
        dr_region=DR,
        precheck_tools=_make_precheck_tools(),
        failover_tools=_make_failover_tools(),
        postcheck_tools=_make_postcheck_tools(),
        support_tools=support,
        servicenow_tools=snow,
        event_logger=logger,
    )
    return result, logger, s_updates, sn_updates


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReturnStructure:
    def test_returns_case_id(self):
        result, *_ = _run_happy_path()
        assert "case_id" in result
        assert result["case_id"].startswith("makita-case-")

    def test_returns_ticket_id(self):
        result, *_ = _run_happy_path()
        assert "ticket_id" in result
        assert result["ticket_id"].startswith("INC")

    def test_returns_failover_result(self):
        result, *_ = _run_happy_path()
        assert "failover_result" in result
        assert result["failover_result"]["success"] is True


class TestEventLogCreation:
    """Req 14.1, 14.2 — event log files created for case and ticket."""

    def test_creates_two_event_logs(self):
        _, logger, *_ = _run_happy_path()
        assert len(logger.created) == 2

    def test_case_log_created(self):
        result, logger, *_ = _run_happy_path()
        ids = [c[0] for c in logger.created]
        assert result["case_id"] in ids

    def test_ticket_log_created(self):
        result, logger, *_ = _run_happy_path()
        ids = [c[0] for c in logger.created]
        assert result["ticket_id"] in ids


class TestEventLogAppending:
    """Req 14.3, 14.4 — events appended at each phase transition."""

    def test_events_appended_to_case_log(self):
        result, logger, *_ = _run_happy_path()
        case_events = [a for a in logger.appended if a[0] == result["case_id"]]
        assert len(case_events) > 0

    def test_events_appended_to_ticket_log(self):
        result, logger, *_ = _run_happy_path()
        ticket_events = [a for a in logger.appended if a[0] == result["ticket_id"]]
        assert len(ticket_events) > 0

    def test_events_appended_in_pairs(self):
        """Each step appends to both case and ticket logs."""
        result, logger, *_ = _run_happy_path()
        case_count = sum(1 for a in logger.appended if a[0] == result["case_id"])
        ticket_count = sum(1 for a in logger.appended if a[0] == result["ticket_id"])
        assert case_count == ticket_count


class TestTicketUpdates:
    """Tickets are updated at key phase transitions."""

    def test_support_case_updated(self):
        _, _, s_updates, _ = _run_happy_path()
        assert len(s_updates) > 0

    def test_servicenow_ticket_updated(self):
        _, _, _, sn_updates = _run_happy_path()
        assert len(sn_updates) > 0


class TestOnStepForwarding:
    """Caller's on_step callback is still invoked."""

    def test_caller_callback_receives_messages(self):
        support, _ = _make_support_tools()
        snow, _ = _make_servicenow_tools()
        logger = FakeEventLogger()
        steps = []

        run_failover_with_logging(
            cluster_name=CLUSTER,
            primary_region=PRIMARY,
            dr_region=DR,
            on_step=steps.append,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
            support_tools=support,
            servicenow_tools=snow,
            event_logger=logger,
        )
        assert len(steps) > 0
        assert any("Pre-Checks" in s for s in steps)


class TestPreCheckFailureLogging:
    """Event logs capture pre-check failures."""

    def test_failure_events_logged(self):
        support, _ = _make_support_tools()
        snow, _ = _make_servicenow_tools()
        logger = FakeEventLogger()

        result = run_failover_with_logging(
            cluster_name=CLUSTER,
            primary_region=PRIMARY,
            dr_region=DR,
            precheck_tools=_make_precheck_tools(verify_replication=_failing_precheck),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
            support_tools=support,
            servicenow_tools=snow,
            event_logger=logger,
        )
        assert result["failover_result"]["success"] is False
        # Events should still have been appended for the steps that ran
        assert len(logger.appended) > 0
