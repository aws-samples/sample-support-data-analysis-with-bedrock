"""Lambda handler for generating comprehensive DR failover summaries."""

from typing import Optional


def handler(event: dict, context) -> dict:
    """
    Lambda handler that generates a comprehensive DR failover summary.

    Collects pre-check results, failover steps, post-check results,
    and incident management actions from the event data.

    Returns a formatted summary string.
    """
    try:
        if event is None or not isinstance(event, dict):
            return {
                "statusCode": 400,
                "error": "Event data is missing or invalid",
            }

        # Validate required top-level fields
        required_fields = ["event_id", "status", "initiated_at"]
        missing = [f for f in required_fields if f not in event]
        if missing:
            return {
                "statusCode": 400,
                "error": f"Missing required fields: {', '.join(missing)}",
            }

        summary = _build_summary(event)
        return {"statusCode": 200, "summary": summary}

    except Exception as e:
        return {
            "statusCode": 400,
            "error": f"Failed to generate summary: {str(e)}",
        }


def _build_summary(event: dict) -> str:
    """Build a formatted summary string from the failover event data."""
    lines = []

    # Header
    lines.append("=" * 60)
    lines.append("DR FAILOVER SUMMARY")
    lines.append("=" * 60)
    lines.append("")

    # Event overview
    lines.append(f"Event ID:       {event.get('event_id', 'N/A')}")
    lines.append(f"Status:         {event.get('status', 'N/A')}")
    lines.append(f"Initiated At:   {event.get('initiated_at', 'N/A')}")
    completed_at = event.get("completed_at")
    if completed_at:
        lines.append(f"Completed At:   {completed_at}")
    lines.append(f"Primary Region: {event.get('primary_region', 'N/A')}")
    lines.append(f"DR Region:      {event.get('dr_region', 'N/A')}")
    lines.append(f"Primary DB:     {event.get('primary_instance_id', 'N/A')}")
    lines.append(f"Replica DB:     {event.get('replica_instance_id', 'N/A')}")
    lines.append("")

    # Pre-check results
    lines.append("-" * 60)
    lines.append("PRE-CHECK RESULTS")
    lines.append("-" * 60)
    pre_check = event.get("pre_check_result")
    if pre_check:
        lines.append(f"Overall Status: {pre_check.get('overall_status', 'N/A')}")
        for check in pre_check.get("checks", []):
            lines.append(
                f"  - {check.get('check_name', 'Unknown')}: "
                f"{check.get('status', 'N/A')} - {check.get('message', '')}"
            )
    else:
        lines.append("  No pre-check results available.")
    lines.append("")

    # Failover steps
    lines.append("-" * 60)
    lines.append("FAILOVER STEPS")
    lines.append("-" * 60)
    _append_promote_result(lines, event.get("promote_result"))
    _append_dns_result(lines, event.get("dns_update_result"))
    lines.append("")

    # Post-check results
    lines.append("-" * 60)
    lines.append("POST-CHECK RESULTS")
    lines.append("-" * 60)
    post_check = event.get("post_check_result")
    if post_check:
        lines.append(f"Overall Status: {post_check.get('overall_status', 'N/A')}")
        for check in post_check.get("checks", []):
            lines.append(
                f"  - {check.get('check_name', 'Unknown')}: "
                f"{check.get('status', 'N/A')} - {check.get('message', '')}"
            )
    else:
        lines.append("  No post-check results available.")
    lines.append("")

    # Incident management actions
    lines.append("-" * 60)
    lines.append("INCIDENT MANAGEMENT ACTIONS")
    lines.append("-" * 60)
    sn_ticket = event.get("servicenow_ticket_id")
    if sn_ticket:
        lines.append(f"  ServiceNow Ticket: {sn_ticket}")
    support_case = event.get("aws_support_case_id")
    if support_case:
        lines.append(f"  AWS Support Case:  {support_case}")
    slack_channel = event.get("slack_channel_id")
    if slack_channel:
        lines.append(f"  Slack Channel:     {slack_channel}")
    if not (sn_ticket or support_case or slack_channel):
        lines.append("  No incident management actions recorded.")

    actions_log = event.get("actions_log", [])
    if actions_log:
        lines.append("")
        lines.append("  Actions Log:")
        for action in actions_log:
            lines.append(f"    - {action}")
    lines.append("")

    # Error info
    error_msg = event.get("error_message")
    if error_msg:
        lines.append("-" * 60)
        lines.append("ERROR")
        lines.append("-" * 60)
        lines.append(f"  {error_msg}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def _append_promote_result(lines: list, promote: Optional[dict]) -> None:
    """Append promote result section."""
    lines.append("Replica Promotion:")
    if promote:
        lines.append(f"  Success:     {promote.get('success', 'N/A')}")
        lines.append(f"  Instance ID: {promote.get('promoted_instance_id', 'N/A')}")
        lines.append(f"  Endpoint:    {promote.get('promoted_endpoint', 'N/A')}")
        lines.append(f"  Message:     {promote.get('message', 'N/A')}")
    else:
        lines.append("  No promotion result available.")


def _append_dns_result(lines: list, dns: Optional[dict]) -> None:
    """Append DNS update result section."""
    lines.append("DNS Update:")
    if dns:
        lines.append(f"  Success:     {dns.get('success', 'N/A')}")
        lines.append(f"  Record:      {dns.get('record_name', 'N/A')}")
        lines.append(f"  New Value:   {dns.get('new_value', 'N/A')}")
        lines.append(f"  Message:     {dns.get('message', 'N/A')}")
    else:
        lines.append("  No DNS update result available.")
