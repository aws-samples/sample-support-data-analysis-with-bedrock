"""Event logging module for MAKITA disaster recovery operations.

Creates and appends to markdown event log files for AWS Support cases
and ServiceNow tickets.
"""

import os
from datetime import datetime, timezone

# Directory where event log files are stored
EVENT_LOGS_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_log_path(identifier: str) -> str:
    """Return the file path for an event log given a case/ticket identifier."""
    return os.path.join(EVENT_LOGS_DIR, f"event-log-{identifier}.md")


def _utc_timestamp() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_event_log(identifier: str, initial_event: str) -> str:
    """Create a new markdown event log file.

    Args:
        identifier: The case ID or ticket ID (e.g. "makita-case-20240101-001").
        initial_event: Description of the initial event.

    Returns:
        The file path of the created event log.
    """
    path = _get_log_path(identifier)
    timestamp = _utc_timestamp()
    content = (
        f"# Event Log: {identifier}\n"
        f"\n"
        f"## Events\n"
        f"\n"
        f"- **{timestamp}** — {initial_event}\n"
    )
    with open(path, "w") as f:
        f.write(content)
    return path


def append_event(identifier: str, event_description: str) -> None:
    """Append a timestamped entry to an existing event log file.

    Args:
        identifier: The case ID or ticket ID.
        event_description: Description of the event to log.

    Raises:
        FileNotFoundError: If the event log file does not exist.
    """
    path = _get_log_path(identifier)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Event log not found: {path}")
    timestamp = _utc_timestamp()
    with open(path, "a") as f:
        f.write(f"- **{timestamp}** — {event_description}\n")
