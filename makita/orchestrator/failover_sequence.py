"""MAKITA Failover Sequence Orchestrator.

Coordinates the full failover sequence across three strict phases:
  Phase 1 — Pre-Checks  (halt on failure)
  Phase 2 — Failover    (halt on failure)
  Phase 3 — Post-Checks (report failures as warnings)

Tool functions are loaded from the MCP server modules by default but can
be overridden via dependency injection for testing.
"""

from __future__ import annotations

import importlib
import re
from typing import Callable


def _safe_error(exc: Exception) -> str:
    """Return error type and message with internal details like ARNs and endpoints redacted."""
    msg = str(exc)
    msg = re.sub(r"arn:aws[a-zA-Z0-9:/_.*-]+", "[REDACTED_ARN]", msg)
    msg = re.sub(r"https?://[^\s\"',]+", "[REDACTED_URL]", msg)
    msg = re.sub(r"\b\d{12}\b", "[REDACTED_ACCOUNT]", msg)
    return f"{type(exc).__name__}: {msg}"


# ---------------------------------------------------------------------------
# Default tool loaders — import from mcp-servers/workload via importlib (hyphen path)
# ---------------------------------------------------------------------------

def _load_precheck_tools() -> dict:
    """Load pre-check tool functions from the precheck MCP server."""
    mod = importlib.import_module("mcp-servers.workloads.postgresql.precheck.server")
    return {
        "verify_replication_health": mod.verify_replication_health,
        "verify_primary_status": mod.verify_primary_status,
        "verify_replica_readiness": mod.verify_replica_readiness,
    }


def _load_failover_tools() -> dict:
    """Load failover tool functions from the failover MCP server."""
    mod = importlib.import_module("mcp-servers.workloads.postgresql.failover.server")
    return {
        "execute_failover": mod.execute_failover,
    }


def _load_postcheck_tools() -> dict:
    """Load post-check tool functions from the postcheck MCP server."""
    mod = importlib.import_module("mcp-servers.workloads.postgresql.postcheck.server")
    return {
        "verify_new_primary_health": mod.verify_new_primary_health,
        "verify_endpoints": mod.verify_endpoints,
        "verify_replication_established": mod.verify_replication_established,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_failover_sequence(
    cluster_name: str,
    primary_region: str,
    dr_region: str,
    on_step: Callable[[str], None] | None = None,
    # Tool function overrides for testing
    precheck_tools: dict | None = None,
    failover_tools: dict | None = None,
    postcheck_tools: dict | None = None,
) -> dict:
    """Execute the full failover sequence: Pre-Checks → Failover → Post-Checks.

    Args:
        cluster_name: PostgreSQL cluster name (e.g. "makita-pg-cluster").
        primary_region: Current primary region (e.g. "us-east-1").
        dr_region: Disaster-recovery region (e.g. "us-west-2").
        on_step: Optional callback for chat step display messages.
        precheck_tools: Override pre-check tool functions (for testing).
        failover_tools: Override failover tool functions (for testing).
        postcheck_tools: Override post-check tool functions (for testing).

    Returns:
        A result dict with phase results and overall success status.
    """

    def step(msg: str) -> None:
        if on_step is not None:
            on_step(msg)

    # Resolve tool functions
    _precheck = precheck_tools if precheck_tools is not None else _load_precheck_tools()
    _failover = failover_tools if failover_tools is not None else _load_failover_tools()
    _postcheck = postcheck_tools if postcheck_tools is not None else _load_postcheck_tools()

    result: dict = {
        "success": False,
        "phase": "not_started",
        "pre_check_results": [],
        "failover_result": None,
        "post_check_results": [],
        "warnings": [],
        "error": None,
    }

    # ------------------------------------------------------------------
    # Phase 1: Pre-Checks
    # ------------------------------------------------------------------
    step("Starting Phase 1: Pre-Checks")
    result["phase"] = "pre_checks"

    pre_checks = [
        (
            "verify_replication_health",
            lambda: _precheck["verify_replication_health"](cluster_name=cluster_name),
        ),
        (
            "verify_primary_status",
            lambda: _precheck["verify_primary_status"](
                cluster_name=cluster_name, primary_region=primary_region
            ),
        ),
        (
            "verify_replica_readiness",
            lambda: _precheck["verify_replica_readiness"](
                cluster_name=cluster_name, dr_region=dr_region
            ),
        ),
    ]

    for check_name, check_fn in pre_checks:
        step(f"Running pre-check: {check_name}")
        try:
            check_result = check_fn()
        except Exception as exc:
            check_result = {
                "check_name": check_name,
                "passed": False,
                "details": {},
                "error": _safe_error(exc),
            }

        result["pre_check_results"].append(check_result)

        if not check_result.get("passed", False):
            error_detail = check_result.get("error") or f"Pre-check failed: {check_name}"
            result["error"] = error_detail
            step(f"Pre-check failed: {check_name} — {error_detail}")
            return result

    step("All pre-checks passed")

    # ------------------------------------------------------------------
    # Phase 2: Failover
    # ------------------------------------------------------------------
    step("Starting Phase 2: Failover execution")
    result["phase"] = "failover"

    try:
        failover_result = _failover["execute_failover"](
            primary_region=primary_region,
            dr_region=dr_region,
            cluster_name=cluster_name,
        )
    except Exception as exc:
        failover_result = {"success": False, "error": _safe_error(exc)}

    result["failover_result"] = failover_result

    if not failover_result.get("success", False):
        error_detail = failover_result.get("error") or "Failover execution failed"
        result["error"] = error_detail
        step(f"Failover failed — {error_detail}")
        return result

    step("Failover completed successfully")

    # ------------------------------------------------------------------
    # Phase 3: Post-Checks
    # ------------------------------------------------------------------
    step("Starting Phase 3: Post-Checks")
    result["phase"] = "post_checks"

    post_checks = [
        (
            "verify_new_primary_health",
            lambda: _postcheck["verify_new_primary_health"](
                cluster_name=cluster_name, dr_region=dr_region
            ),
        ),
        (
            "verify_endpoints",
            lambda: _postcheck["verify_endpoints"](cluster_name=cluster_name),
        ),
        (
            "verify_replication_established",
            lambda: _postcheck["verify_replication_established"](
                cluster_name=cluster_name
            ),
        ),
    ]

    for check_name, check_fn in post_checks:
        step(f"Running post-check: {check_name}")
        try:
            check_result = check_fn()
        except Exception as exc:
            check_result = {
                "check_name": check_name,
                "passed": False,
                "details": {},
                "error": _safe_error(exc),
            }

        result["post_check_results"].append(check_result)

        if not check_result.get("passed", False):
            warning = check_result.get("error") or f"Post-check failed: {check_name}"
            result["warnings"].append(warning)
            step(f"Post-check warning: {check_name} — {warning}")

    # Post-check failures are warnings — failover is still considered complete
    result["success"] = True
    step("Failover sequence complete")

    return result
