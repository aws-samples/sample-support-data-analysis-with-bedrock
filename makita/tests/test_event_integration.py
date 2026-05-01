"""Tests for orchestrator.event_integration — failover with event logging."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrator.event_integration import run_failover_with_logging


def _make_fake_tools(results):
    return {name: (lambda r=r: lambda **kw: r)(r) for name, r in results.items()}


@pytest.fixture()
def fake_precheck_tools():
    return _make_fake_tools({
        "verify_replication_health": {"passed": True},
        "verify_primary_status": {"passed": True},
        "verify_replica_readiness": {"passed": True},
    })


@pytest.fixture()
def fake_failover_tools():
    return _make_fake_tools({
        "execute_failover": {"success": True},
    })


@pytest.fixture()
def fake_postcheck_tools():
    return _make_fake_tools({
        "verify_new_primary_health": {"passed": True},
        "verify_endpoints": {"passed": True},
        "verify_replication_established": {"passed": True},
    })


@pytest.fixture()
def fake_event_logger():
    logs = {}

    class FakeLogger:
        def create_event_log(self, log_id, description):
            logs[log_id] = [description]

        def append_event(self, log_id, description):
            logs[log_id].append(description)

    return FakeLogger(), logs


def _run(fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger, on_step=None):
    logger, _ = fake_event_logger
    return run_failover_with_logging(
        cluster_name="test-cluster",
        primary_region="us-east-1",
        dr_region="us-west-2",
        on_step=on_step,
        precheck_tools=fake_precheck_tools,
        failover_tools=fake_failover_tools,
        postcheck_tools=fake_postcheck_tools,
        event_logger=logger,
    )


class TestReturnStructure:
    def test_returns_log_id(self, fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger):
        result = _run(fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger)
        assert "log_id" in result

    def test_returns_failover_result(self, fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger):
        result = _run(fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger)
        assert "failover_result" in result


class TestEventLogCreation:
    def test_creates_event_log(self, fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger):
        _, logs = fake_event_logger
        _run(fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger)
        assert len(logs) == 1


class TestEventLogAppending:
    def test_events_appended(self, fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger):
        _, logs = fake_event_logger
        _run(fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger)
        log_id = list(logs.keys())[0]
        assert len(logs[log_id]) > 1  # initial + step events


class TestOnStepForwarding:
    def test_caller_callback_receives_messages(self, fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger):
        messages = []
        _run(fake_precheck_tools, fake_failover_tools, fake_postcheck_tools, fake_event_logger, on_step=messages.append)
        assert len(messages) > 0
