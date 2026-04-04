"""MAKITA Event Integration — top-level failover with ticketing and event logging.

Wires together:
  - orchestrator.ticketing      — ticket creation / updates
  - event-logs.event_logger     — event log file creation / appending
  - orchestrator.failover_sequence — the three-phase failover sequence

Requirements: 14.1, 14.2, 14.3, 14.4
"""

from __future__ import annotations

import importlib
from typing import Callable

from orchestrator.ticketing import (
    TicketUpdateContext,
    create_tickets,
    update_tickets,
)
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
    support_tools: dict | None = None,
    servicenow_tools: dict | None = None,
    event_logger=None,
) -> dict:
    """Run the full failover sequence with ticketing and event logging.

    1. Create AWS Support case + ServiceNow ticket
    2. Create event log files for both
    3. Run the failover sequence with an on_step callback that
       appends events to both log files and updates tickets at
       key phase transitions
    4. Return failover result along with case_id and ticket_id
    """
    el = event_logger if event_logger is not None else _load_event_logger()

    # ---- 1. Create tickets (Req 13.1, 13.2) ----
    subject = f"PostgreSQL Failover DR Operation — {cluster_name}"
    description = (
        f"Automated failover of {cluster_name} "
        f"from {primary_region} to {dr_region}"
    )
    case_id, ticket_id = create_tickets(
        subject=subject,
        description=description,
        support_tools=support_tools,
        servicenow_tools=servicenow_tools,
    )

    # ---- 2. Create event log files (Req 14.1, 14.2) ----
    el.create_event_log(case_id, f"AWS Support case {case_id} created")
    el.create_event_log(ticket_id, f"ServiceNow ticket {ticket_id} created")

    # ---- 3. Build on_step callback ----
    # Phase transitions that should also trigger a ticket update
    _PHASE_KEYWORDS = {
        "Starting Phase 1": "pre-checks initiated",
        "All pre-checks passed": "pre-checks passed",
        "Starting Phase 2": "failover initiated",
        "Failover completed": "failover execution completed",
        "Starting Phase 3": "post-checks initiated",
        "Failover sequence complete": "failover complete",
        "Pre-check failed": "pre-check failure",
        "Failover failed": "failover failure",
        "Post-check warning": "post-check warning",
    }

    def _on_step(msg: str) -> None:
        # Append event to both log files (Req 14.3, 14.4)
        el.append_event(case_id, msg)
        el.append_event(ticket_id, msg)

        # Update tickets at key phase transitions
        for keyword, status in _PHASE_KEYWORDS.items():
            if keyword in msg:
                phase = "pre-check"
                if "Phase 2" in msg or "Failover" in msg:
                    phase = "failover"
                elif "Phase 3" in msg or "Post-check" in msg:
                    phase = "post-check"

                ctx = TicketUpdateContext(
                    phase=phase,
                    status=status,
                    primary_region=primary_region,
                    dr_region=dr_region,
                )
                update_tickets(
                    case_id,
                    ticket_id,
                    ctx,
                    support_tools=support_tools,
                    servicenow_tools=servicenow_tools,
                )
                break

        # Forward to caller's callback if provided
        if on_step is not None:
            on_step(msg)

    # ---- 4. Run failover sequence ----
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
        "case_id": case_id,
        "ticket_id": ticket_id,
        "failover_result": failover_result,
    }
