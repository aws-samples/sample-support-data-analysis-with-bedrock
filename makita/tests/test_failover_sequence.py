"""Tests for the MAKITA failover sequence orchestrator."""

from orchestrator.failover_sequence import run_failover_sequence


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


def _failing_failover(**kwargs):
    return {"success": False, "error": "promotion failed"}


def _passing_postcheck(**kwargs):
    return {"check_name": "test_post", "passed": True, "details": {}, "error": None}


def _failing_postcheck(**kwargs):
    return {"check_name": "test_post", "passed": False, "details": {}, "error": "post-check failed"}


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


CLUSTER = "makita-pg-cluster"
PRIMARY = "us-east-1"
DR = "us-west-2"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullSuccessPath:
    """All phases pass — happy path."""

    def test_returns_success(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is True

    def test_phase_is_post_checks(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["phase"] == "post_checks"

    def test_no_error(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["error"] is None

    def test_no_warnings(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["warnings"] == []

    def test_pre_check_results_populated(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert len(result["pre_check_results"]) == 3

    def test_failover_result_populated(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["failover_result"]["success"] is True

    def test_post_check_results_populated(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert len(result["post_check_results"]) == 3


class TestPreCheckFailure:
    """Pre-check failure halts the sequence."""

    def test_halts_on_first_precheck_failure(self):
        tools = _make_precheck_tools(verify_replication=_failing_precheck)
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=tools,
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is False
        assert result["phase"] == "pre_checks"
        assert result["failover_result"] is None
        assert result["post_check_results"] == []

    def test_halts_on_second_precheck_failure(self):
        tools = _make_precheck_tools(verify_primary=_failing_precheck)
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=tools,
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is False
        assert len(result["pre_check_results"]) == 2  # first passed, second failed

    def test_halts_on_third_precheck_failure(self):
        tools = _make_precheck_tools(verify_replica=_failing_precheck)
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=tools,
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is False
        assert len(result["pre_check_results"]) == 3

    def test_error_message_set(self):
        tools = _make_precheck_tools(verify_replication=_failing_precheck)
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=tools,
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["error"] == "check failed"


class TestFailoverFailure:
    """Failover failure halts before post-checks."""

    def test_halts_on_failover_failure(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(execute=_failing_failover),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is False
        assert result["phase"] == "failover"
        assert result["post_check_results"] == []

    def test_failover_error_message(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(execute=_failing_failover),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["error"] == "promotion failed"

    def test_precheck_results_still_present(self):
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(execute=_failing_failover),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert len(result["pre_check_results"]) == 3


class TestPostCheckFailure:
    """Post-check failures are warnings — failover is still success."""

    def test_success_with_post_check_warnings(self):
        tools = _make_postcheck_tools(health=_failing_postcheck)
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=tools,
        )
        assert result["success"] is True
        assert len(result["warnings"]) == 1

    def test_all_post_checks_fail_still_success(self):
        tools = _make_postcheck_tools(
            health=_failing_postcheck,
            endpoints=_failing_postcheck,
            replication=_failing_postcheck,
        )
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=tools,
        )
        assert result["success"] is True
        assert len(result["warnings"]) == 3


class TestOnStepCallback:
    """The on_step callback receives messages for each step."""

    def test_step_messages_on_success(self):
        steps = []
        run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            on_step=steps.append,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert any("Pre-Checks" in s for s in steps)
        assert any("Failover" in s for s in steps)
        assert any("Post-Checks" in s for s in steps)
        assert any("complete" in s.lower() for s in steps)

    def test_step_messages_on_precheck_failure(self):
        steps = []
        tools = _make_precheck_tools(verify_replication=_failing_precheck)
        run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            on_step=steps.append,
            precheck_tools=tools,
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert any("failed" in s.lower() for s in steps)
        # Should NOT have failover or post-check steps
        assert not any("Phase 2" in s for s in steps)

    def test_none_callback_does_not_raise(self):
        """on_step=None should not cause errors."""
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            on_step=None,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is True


class TestExceptionHandling:
    """Tool functions that raise exceptions are handled gracefully."""

    def test_precheck_exception_treated_as_failure(self):
        def exploding(**kwargs):
            raise RuntimeError("boom")

        tools = _make_precheck_tools(verify_replication=exploding)
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=tools,
            failover_tools=_make_failover_tools(),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is False
        assert "boom" in result["error"]

    def test_failover_exception_treated_as_failure(self):
        def exploding(**kwargs):
            raise RuntimeError("kaboom")

        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(execute=exploding),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert result["success"] is False
        assert "kaboom" in result["error"]

    def test_postcheck_exception_treated_as_warning(self):
        def exploding(**kwargs):
            raise RuntimeError("oops")

        tools = _make_postcheck_tools(health=exploding)
        result = run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(),
            postcheck_tools=tools,
        )
        assert result["success"] is True
        assert any("oops" in w for w in result["warnings"])


class TestPhaseOrdering:
    """Strict phase ordering: Pre-Checks → Failover → Post-Checks."""

    def test_failover_not_called_on_precheck_failure(self):
        called = {"failover": False}

        def tracking_failover(**kwargs):
            called["failover"] = True
            return _passing_failover()

        tools = _make_precheck_tools(verify_replication=_failing_precheck)
        run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=tools,
            failover_tools=_make_failover_tools(execute=tracking_failover),
            postcheck_tools=_make_postcheck_tools(),
        )
        assert called["failover"] is False

    def test_postchecks_not_called_on_failover_failure(self):
        called = {"postcheck": False}

        def tracking_postcheck(**kwargs):
            called["postcheck"] = True
            return _passing_postcheck()

        tools = _make_postcheck_tools(health=tracking_postcheck)
        run_failover_sequence(
            CLUSTER, PRIMARY, DR,
            precheck_tools=_make_precheck_tools(),
            failover_tools=_make_failover_tools(execute=_failing_failover),
            postcheck_tools=tools,
        )
        assert called["postcheck"] is False
