"""Incident Manager for DR workflow — Slack, ServiceNow, and AWS Support integrations."""

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import boto3
import pysnow
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from makita_dr.models import DRConfig, FailoverEvent, FailoverStatus

logger = logging.getLogger(__name__)


class IncidentManager:
    """Coordinates incident management across Slack, ServiceNow, and AWS Support."""

    def __init__(self, config: DRConfig, support_endpoint_url: Optional[str] = None):
        self.config = config
        self._slack_client = WebClient(token=config.slack_bot_token)
        self._snow_client = self._build_snow_client(config)
        self._support_client = self._build_support_client(support_endpoint_url)

    @staticmethod
    def _build_snow_client(config: DRConfig) -> pysnow.Client:
        """Create a pysnow Client pointed at the ServiceNow stub server."""
        parsed = urlparse(config.servicenow_endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port
        if port:
            host = f"{host}:{port}"
        use_ssl = parsed.scheme == "https"
        return pysnow.Client(
            host=host,
            user="admin",
            password=config.servicenow_api_key,
            use_ssl=use_ssl,
        )

    @staticmethod
    def _build_support_client(endpoint_url: Optional[str] = None):
        """Create a Boto3 Support client, optionally routed to a stub server."""
        kwargs: dict = {
            "service_name": "support",
            "region_name": "us-east-1",
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        return boto3.client(**kwargs)

    # ------------------------------------------------------------------
    # Slack operations
    # ------------------------------------------------------------------

    def create_slack_channel(self) -> str:
        """Create a Slack channel named ``makita-dr-YYYYMMDD``.

        Returns the channel ID of the newly created channel.
        """
        channel_name = f"makita-dr-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        response = self._slack_client.conversations_create(
            name=channel_name,
            is_private=False,
        )
        channel_id = response["channel"]["id"]
        logger.info("Created Slack channel %s (%s)", channel_name, channel_id)
        return channel_id

    def post_slack_message(self, channel_id: str, message: str) -> None:
        """Post a plain-text message to the given Slack channel."""
        self._slack_client.chat_postMessage(
            channel=channel_id,
            text=message,
        )

    def post_initial_message(self, channel_id: str, event: FailoverEvent) -> None:
        """Post the initial DR event summary to the Slack channel.

        The message includes the event summary, affected database resources,
        and the current failover status.
        """
        message = (
            f"🚨 *DR Failover Event Initiated*\n"
            f"Event ID: {event.event_id}\n"
            f"Status: {event.status.value}\n"
            f"Primary Region: {event.primary_region}\n"
            f"DR Region: {event.dr_region}\n"
            f"Primary Instance: {event.primary_instance_id}\n"
            f"Replica Instance: {event.replica_instance_id}\n"
            f"Initiated At: {event.initiated_at.isoformat()}"
        )
        self.post_slack_message(channel_id, message)

    def log_action(self, channel_id: str, action: str) -> None:
        """Log a DR workflow action as a message in the Slack channel."""
        timestamp = datetime.now(timezone.utc).isoformat()
        message = f"📋 *Action Log* [{timestamp}]: {action}"
        self.post_slack_message(channel_id, message)

    def post_status_update(self, channel_id: str, status: FailoverStatus) -> None:
        """Post a status update message when the failover status changes."""
        message = f"🔄 *Status Update*: Failover status changed to *{status.value}*"
        self.post_slack_message(channel_id, message)

    def handle_mention(self, channel_id: str, question: str, event: FailoverEvent) -> str:
        """Handle an @makita mention in the Slack channel.

        Parses the question and responds with the requested information.
        Returns the response text that was posted.
        """
        response_text = self._build_mention_response(question, event)
        self.post_slack_message(channel_id, response_text)
        return response_text

    def _build_mention_response(self, question: str, event: FailoverEvent) -> str:
        """Build a response to an @makita mention based on the question content."""
        q_lower = question.lower()

        if "status" in q_lower:
            return self._build_status_response(event)

        # Default: return a general summary of the DR event
        return (
            f"DR Event {event.event_id} — Status: {event.status.value}. "
            f"Failover from {event.primary_region} to {event.dr_region}."
        )

    def _build_status_response(self, event: FailoverEvent) -> str:
        """Build a detailed status response including completed steps and pending actions."""
        completed_steps = list(event.actions_log)
        pending_actions = _determine_pending_actions(event)

        lines = [
            f"📊 *DR Status Report*",
            f"Event ID: {event.event_id}",
            f"Current Status: *{event.status.value}*",
            "",
            "*Completed Steps:*",
        ]
        if completed_steps:
            for step in completed_steps:
                lines.append(f"  ✅ {step}")
        else:
            lines.append("  (none)")

        lines.append("")
        lines.append("*Pending Actions:*")
        if pending_actions:
            for action in pending_actions:
                lines.append(f"  ⏳ {action}")
        else:
            lines.append("  (none)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # ServiceNow operations (using pysnow SDK against stub server)
    # ------------------------------------------------------------------

    def create_servicenow_ticket(self, event_summary: dict) -> str:
        """Create a ServiceNow incident ticket via pysnow. Returns sys_id."""
        incident = self._snow_client.resource(api_path="/table/incident")
        now_ts = datetime.now(timezone.utc).isoformat()

        payload = {
            "short_description": event_summary.get("summary", "DR Failover Event"),
            "description": (
                f"DR Failover Event\n"
                f"Summary: {event_summary.get('summary', '')}\n"
                f"Affected Resources: {event_summary.get('affected_resources', '')}\n"
                f"Timestamp: {event_summary.get('timestamp', now_ts)}"
            ),
            "urgency": "1",
            "state": event_summary.get("status", "in-progress"),
            "u_affected_resources": str(event_summary.get("affected_resources", "")),
            "u_event_timestamp": event_summary.get("timestamp", now_ts),
        }

        result = incident.create(payload=payload)
        sys_id = result["sys_id"]
        logger.info("Created ServiceNow ticket sys_id=%s", sys_id)
        return sys_id

    def update_servicenow_ticket(self, ticket_id: str, status: str, details: dict) -> None:
        """Update a ServiceNow ticket with current status and details."""
        incident = self._snow_client.resource(api_path="/table/incident")

        payload = {
            "state": status,
            "work_notes": (
                f"Status updated to: {status}\n"
                f"Details: {details}"
            ),
        }
        # Merge any extra detail fields into the payload
        for key, value in details.items():
            if key not in payload:
                payload[key] = str(value)

        incident.update(query={"sys_id": ticket_id}, payload=payload)
        logger.info("Updated ServiceNow ticket sys_id=%s to status=%s", ticket_id, status)

    # ------------------------------------------------------------------
    # AWS Support operations (using actual Boto3 SDK against stub)
    # ------------------------------------------------------------------

    def create_support_ticket(self, event_summary: dict) -> str:
        """Create an AWS Support case via Boto3 Support APIs. Returns case ID.

        The communication body includes the DR event summary, affected AWS
        resources, severity level, and Primary/DR region identifiers.

        Validates: Requirements 6.2, 6.3, 6.4
        """
        primary_region = event_summary.get("primary_region", self.config.primary_region)
        dr_region = event_summary.get("dr_region", self.config.dr_region)
        affected = event_summary.get("affected_resources", "")
        summary_text = event_summary.get("summary", "DR Failover Event")

        communication_body = (
            f"DR Failover Event\n"
            f"Summary: {summary_text}\n"
            f"Affected Resources: {affected}\n"
            f"Primary Region: {primary_region}\n"
            f"DR Region: {dr_region}\n"
            f"Severity: {self.config.support_severity}\n"
            f"Timestamp: {event_summary.get('timestamp', datetime.now(timezone.utc).isoformat())}"
        )

        response = self._support_client.create_case(
            subject=f"DR Failover: {summary_text}",
            serviceCode=self.config.support_service_code,
            categoryCode=self.config.support_category_code,
            severityCode=self.config.support_severity,
            communicationBody=communication_body,
            language="en",
        )

        case_id = response["caseId"]
        logger.info("Created AWS Support case %s", case_id)
        return case_id

    def update_support_ticket(self, case_id: str, status: str) -> None:
        """Update an AWS Support case with the current failover status.

        Validates: Requirements 6.5
        """
        communication_body = (
            f"Failover status update: {status}\n"
            f"Updated at: {datetime.now(timezone.utc).isoformat()}"
        )

        self._support_client.add_communication_to_case(
            caseId=case_id,
            communicationBody=communication_body,
        )
        logger.info("Updated AWS Support case %s with status=%s", case_id, status)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _determine_pending_actions(event: FailoverEvent) -> list:
    """Determine pending actions based on the current event state."""
    pending = []

    if event.status == FailoverStatus.NOT_STARTED:
        pending.extend([
            "Create incident tickets",
            "Run pre-failover checks",
            "Promote read replica",
            "Update DNS",
            "Run post-failover checks",
            "Generate failover summary",
        ])
    elif event.status == FailoverStatus.IN_PROGRESS:
        if event.pre_check_result is None:
            pending.append("Run pre-failover checks")
        if event.promote_result is None:
            pending.extend(["Promote read replica", "Update DNS"])
        elif event.dns_update_result is None:
            pending.append("Update DNS")
        if event.post_check_result is None:
            pending.append("Run post-failover checks")
        pending.append("Generate failover summary")
    # COMPLETED / FAILED → no pending actions

    return pending
