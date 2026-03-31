"""DR Orchestrator — central coordination component for the DR failover workflow.

Wires together all components: ConfigLoader, IncidentManager (Slack, ServiceNow,
AWS Support), PreCheckEngine, RDSFailoverManager, PostCheckEngine, DRMCPServer,
and CloudWatchDashboardManager.

Every action is logged to the Slack channel. If any failover step raises an
exception the orchestrator halts, logs the error, updates tickets with failure
status, and returns immediately.
"""

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from makita_dr.cloudwatch_dashboard import CloudWatchDashboardManager
from makita_dr.incident_manager import IncidentManager
from makita_dr.mcp_server import DRMCPServer
from makita_dr.models import (
    DRConfig,
    FailoverEvent,
    FailoverResult,
    FailoverStatus,
)
from makita_dr.post_check_engine import PostCheckEngine
from makita_dr.pre_check_engine import PreCheckEngine
from makita_dr.rds_failover import RDSFailoverManager

logger = logging.getLogger(__name__)


class DROrchestrator:
    """Central coordination component that drives the DR failover workflow."""

    def __init__(
        self,
        config: DRConfig,
        incident_manager: Optional[IncidentManager] = None,
        pre_check_engine: Optional[PreCheckEngine] = None,
        post_check_engine: Optional[PostCheckEngine] = None,
        rds_failover_manager: Optional[RDSFailoverManager] = None,
        mcp_server: Optional[DRMCPServer] = None,
        dashboard_manager: Optional[CloudWatchDashboardManager] = None,
    ):
        """Initialize with configuration and optional injected dependencies."""
        self._config = config
        self._incident_manager = incident_manager or IncidentManager(config)
        self._pre_check_engine = pre_check_engine or PreCheckEngine(config)
        self._post_check_engine = post_check_engine or PostCheckEngine(config)
        self._rds_failover = rds_failover_manager or RDSFailoverManager(config)
        self._mcp_server = mcp_server or DRMCPServer(config)
        self._dashboard_manager = dashboard_manager or CloudWatchDashboardManager(config)

        # Mutable state for the current failover event
        self._event: Optional[FailoverEvent] = None
        self._channel_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initiate_failover(self) -> FailoverResult:
        """Execute the full DR failover workflow.

        Steps:
        1. Create Slack channel and post initial summary
        2. Create incident tickets (ServiceNow, AWS Support)
        3. Run pre-checks
        4. Identify RDS instances
        5. Promote RDS read replica
        6. Update DNS/connection strings
        7. Verify read-write mode
        8. Run post-checks
        9. Update incident tickets
        10. Generate and post failover summary via MCP
        """
        self._event = FailoverEvent(
            event_id=str(uuid.uuid4()),
            status=FailoverStatus.IN_PROGRESS,
            initiated_at=datetime.now(timezone.utc),
            primary_region=self._config.primary_region,
            dr_region=self._config.dr_region,
            primary_instance_id=self._config.primary_instance_id,
            replica_instance_id=self._config.replica_instance_id,
        )

        try:
            # Step 1: Slack channel + initial message
            self._step_create_slack_channel()
            self._step_post_initial_message()

            # Step 2: Incident tickets
            self._step_create_incident_tickets()

            # Step 3: Pre-checks
            self._step_run_pre_checks()

            # Steps 4-7: RDS failover sequence
            self._step_identify_instances()
            self._step_promote_replica()
            self._step_update_dns()
            self._step_verify_read_write()

            # Step 8: Post-checks
            self._step_run_post_checks()

            # Step 9: Update tickets with success
            self._step_update_tickets(FailoverStatus.COMPLETED)

            # Step 10: MCP summary + Slack final summary
            summary = self._step_generate_summary()

            # Mark completed
            self._event.status = FailoverStatus.COMPLETED
            self._event.completed_at = datetime.now(timezone.utc)
            self._log("Failover completed successfully")

            return FailoverResult(event=self._event, summary=summary)

        except Exception as exc:
            return self._handle_failure(exc)

    def handle_slack_question(self, question: str) -> str:
        """Respond to @makita questions in the Slack channel.

        Delegates to the incident manager's handle_mention method.
        """
        if self._channel_id is None or self._event is None:
            return "No active DR event. Please initiate a failover first."

        return self._incident_manager.handle_mention(
            self._channel_id, question, self._event
        )

    # ------------------------------------------------------------------
    # Workflow steps (each logs its action to Slack)
    # ------------------------------------------------------------------

    def _step_create_slack_channel(self) -> None:
        channel_id = self._incident_manager.create_slack_channel()
        self._channel_id = channel_id
        self._event.slack_channel_id = channel_id
        self._log("Slack channel created")

    def _step_post_initial_message(self) -> None:
        self._incident_manager.post_initial_message(self._channel_id, self._event)
        self._log("Initial DR event summary posted to Slack")

    def _step_create_incident_tickets(self) -> None:
        event_summary = self._build_event_summary()

        snow_id = self._incident_manager.create_servicenow_ticket(event_summary)
        self._event.servicenow_ticket_id = snow_id
        self._log(f"ServiceNow ticket created: {snow_id}")

        support_id = self._incident_manager.create_support_ticket(event_summary)
        self._event.aws_support_case_id = support_id
        self._log(f"AWS Support case created: {support_id}")

    def _step_run_pre_checks(self) -> None:
        self._log("Running pre-failover checks")
        result = self._pre_check_engine.run_all_checks()
        self._event.pre_check_result = result

        if not result.passed:
            failed = [c for c in result.checks if c.status.value == "failed"]
            details = "; ".join(f"{c.check_name}: {c.message}" for c in failed)
            raise RuntimeError(f"Pre-checks failed: {details}")

        self._log("Pre-failover checks passed")

    def _step_identify_instances(self) -> None:
        self._log("Identifying RDS primary instance and read replica")
        self._rds_failover.identify_instances()
        self._log(
            f"Identified primary '{self._config.primary_instance_id}' "
            f"and replica '{self._config.replica_instance_id}'"
        )

    def _step_promote_replica(self) -> None:
        self._log("Promoting RDS read replica")
        result = self._rds_failover.promote_read_replica()
        self._event.promote_result = result

        if not result.success:
            raise RuntimeError(f"Replica promotion failed: {result.message}")

        self._log(f"Read replica promoted: {result.promoted_endpoint}")

    def _step_update_dns(self) -> None:
        self._log("Updating DNS records")
        result = self._rds_failover.update_dns()
        self._event.dns_update_result = result

        if not result.success:
            raise RuntimeError(f"DNS update failed: {result.message}")

        self._log(f"DNS updated: {result.record_name} → {result.new_value}")

    def _step_verify_read_write(self) -> None:
        self._log("Verifying promoted instance is in read-write mode")
        is_rw = self._rds_failover.verify_read_write()

        if not is_rw:
            raise RuntimeError("Promoted instance is not in read-write mode")

        self._log("Promoted instance verified as read-write")

    def _step_run_post_checks(self) -> None:
        self._log("Running post-failover checks")
        result = self._post_check_engine.run_all_checks()
        self._event.post_check_result = result

        if not result.passed:
            failed = [c for c in result.checks if c.status.value == "failed"]
            details = "; ".join(f"{c.check_name}: {c.message}" for c in failed)
            raise RuntimeError(f"Post-checks failed: {details}")

        self._log("Post-failover checks passed")

    def _step_update_tickets(self, status: FailoverStatus) -> None:
        status_str = status.value
        details = {"event_id": self._event.event_id}

        if self._event.servicenow_ticket_id:
            self._incident_manager.update_servicenow_ticket(
                self._event.servicenow_ticket_id, status_str, details
            )
            self._log(f"ServiceNow ticket updated to {status_str}")

        if self._event.aws_support_case_id:
            self._incident_manager.update_support_ticket(
                self._event.aws_support_case_id, status_str
            )
            self._log(f"AWS Support case updated to {status_str}")

    def _step_generate_summary(self) -> Optional[str]:
        self._log("Generating failover summary via MCP")
        event_data = self._serialize_event()
        result = self._mcp_server.generate_failover_summary(event_data)

        summary = result.get("summary") if result.get("status") == "success" else None

        if summary:
            self._incident_manager.post_slack_message(
                self._channel_id,
                f"📝 *Failover Summary*\n{summary}",
            )
            self._log("Failover summary posted to Slack")
        else:
            error_msg = result.get("message", "Unknown error")
            self._log(f"Failed to generate summary: {error_msg}")

        return summary

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_failure(self, exc: Exception) -> FailoverResult:
        """Handle a failure during the failover workflow."""
        error_msg = str(exc)
        logger.error("Failover failed: %s", error_msg)

        self._event.status = FailoverStatus.FAILED
        self._event.error_message = error_msg
        self._event.completed_at = datetime.now(timezone.utc)

        # Log error to Slack if channel exists
        if self._channel_id:
            self._log(f"❌ Failover FAILED: {error_msg}")

        # Update tickets with failure status
        try:
            self._step_update_tickets(FailoverStatus.FAILED)
        except Exception as ticket_exc:
            logger.error("Failed to update tickets after failure: %s", ticket_exc)

        return FailoverResult(event=self._event, summary=None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, action: str) -> None:
        """Log an action to the Slack channel and the event's actions_log."""
        self._event.actions_log.append(action)
        if self._channel_id:
            try:
                self._incident_manager.log_action(self._channel_id, action)
            except Exception as exc:
                logger.warning("Failed to log action to Slack: %s", exc)

    def _build_event_summary(self) -> dict:
        """Build the event summary dict used for ticket creation."""
        return {
            "summary": (
                f"DR Failover from {self._config.primary_region} "
                f"to {self._config.dr_region}"
            ),
            "affected_resources": (
                f"Primary: {self._config.primary_instance_id}, "
                f"Replica: {self._config.replica_instance_id}"
            ),
            "primary_region": self._config.primary_region,
            "dr_region": self._config.dr_region,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "in-progress",
        }

    def _serialize_event(self) -> dict:
        """Serialize the FailoverEvent to a dict for the MCP summary Lambda."""
        data = {
            "event_id": self._event.event_id,
            "status": self._event.status.value,
            "initiated_at": self._event.initiated_at.isoformat(),
            "primary_region": self._event.primary_region,
            "dr_region": self._event.dr_region,
            "primary_instance_id": self._event.primary_instance_id,
            "replica_instance_id": self._event.replica_instance_id,
            "actions_log": self._event.actions_log,
        }
        if self._event.completed_at:
            data["completed_at"] = self._event.completed_at.isoformat()
        if self._event.pre_check_result:
            data["pre_check_result"] = {
                "overall_status": self._event.pre_check_result.overall_status.value,
                "checks": [
                    {
                        "check_name": c.check_name,
                        "status": c.status.value,
                        "message": c.message,
                    }
                    for c in self._event.pre_check_result.checks
                ],
            }
        if self._event.post_check_result:
            data["post_check_result"] = {
                "overall_status": self._event.post_check_result.overall_status.value,
                "checks": [
                    {
                        "check_name": c.check_name,
                        "status": c.status.value,
                        "message": c.message,
                    }
                    for c in self._event.post_check_result.checks
                ],
            }
        if self._event.promote_result:
            data["promote_result"] = {
                "success": self._event.promote_result.success,
                "promoted_instance_id": self._event.promote_result.promoted_instance_id,
                "promoted_endpoint": self._event.promote_result.promoted_endpoint,
                "message": self._event.promote_result.message,
            }
        if self._event.dns_update_result:
            data["dns_update_result"] = {
                "success": self._event.dns_update_result.success,
                "record_name": self._event.dns_update_result.record_name,
                "new_value": self._event.dns_update_result.new_value,
                "message": self._event.dns_update_result.message,
            }
        if self._event.servicenow_ticket_id:
            data["servicenow_ticket_id"] = self._event.servicenow_ticket_id
        if self._event.aws_support_case_id:
            data["aws_support_case_id"] = self._event.aws_support_case_id
        if self._event.error_message:
            data["error_message"] = self._event.error_message
        return data
