"""MAKITA Event Integration — top-level failover with event logging.

Wires together:
  - event-logs.event_logger     — event log file creation / appending
  - orchestrator.failover_sequence — the three-phase failover sequence
"""

from __future__ import annotations

import importlib
from typing import Callable

from orchestrator.failover_sequence import run_failover_sequence


def _load_event_logger():
    """Import event-logs.event_logger via importlib (hyphenated package)."""
    return importlib.import_module("event-logs.event_logger")


def run_failover_with_logging(
    cluster_name: str,
    primary_region: str,
    dr_region: str,
    on_step: Callable[[str], None] | None = None,
    # DI overrides for testing
    precheck_tools: dict | None = None,
    failover_tools: dict | None = None,
    postcheck_tools: dict | None = None,
    event_logger=None,
) -> dict:
    """Run the full failover sequence with event logging.

    1. Create an event log file
    2. Run the failover sequence with an on_step callback that
       appends events to the log file
    3. Return failover result along with log_id
    """
    el = event_logger if event_logger is not None else _load_event_logger()

    log_id = f"{cluster_name}-failover"
    el.create_event_log(log_id, f"Failover initiated for {cluster_name}")

    def _on_step(msg: str) -> None:
        el.append_event(log_id, msg)
        if on_step is not None:
            on_step(msg)

    failover_result = run_failover_sequence(
        cluster_name=cluster_name,
        primary_region=primary_region,
        dr_region=dr_region,
        on_step=_on_step,
        precheck_tools=precheck_tools,
        failover_tools=failover_tools,
        postcheck_tools=postcheck_tools,
    )

    return {
        "log_id": log_id,
        "failover_result": failover_result,
    }
