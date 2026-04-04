"""Unit tests for the event logging module."""

import os
import re
import sys

import pytest

# Add project root to path so event-logs package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from importlib import import_module

# event-logs is not a valid Python identifier, so import dynamically
event_logger = import_module("event-logs.event_logger")
create_event_log = event_logger.create_event_log
append_event = event_logger.append_event

ISO_8601_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


@pytest.fixture(autouse=True)
def use_tmp_dir(tmp_path, monkeypatch):
    """Redirect EVENT_LOGS_DIR to a temp directory for every test."""
    monkeypatch.setattr(event_logger, "EVENT_LOGS_DIR", str(tmp_path))
    return tmp_path


class TestCreateEventLog:
    def test_creates_file_and_returns_path(self, use_tmp_dir):
        path = create_event_log("makita-case-20240101-001", "Case created")
        assert os.path.isfile(path)
        assert path == os.path.join(str(use_tmp_dir), "event-log-makita-case-20240101-001.md")

    def test_file_contains_header(self, use_tmp_dir):
        path = create_event_log("INC0010001", "Ticket created")
        content = open(path).read()
        assert "# Event Log: INC0010001" in content

    def test_file_contains_events_section(self, use_tmp_dir):
        path = create_event_log("INC0010001", "Ticket created")
        content = open(path).read()
        assert "## Events" in content

    def test_initial_event_has_iso_timestamp(self, use_tmp_dir):
        path = create_event_log("case-1", "Initial event")
        content = open(path).read()
        assert ISO_8601_PATTERN.search(content)

    def test_initial_event_description_present(self, use_tmp_dir):
        path = create_event_log("case-1", "AWS Support case created")
        content = open(path).read()
        assert "AWS Support case created" in content


class TestAppendEvent:
    def test_appends_entry(self, use_tmp_dir):
        create_event_log("case-1", "Created")
        append_event("case-1", "Pre-checks initiated")
        content = open(os.path.join(str(use_tmp_dir), "event-log-case-1.md")).read()
        assert "Pre-checks initiated" in content

    def test_appended_entry_has_iso_timestamp(self, use_tmp_dir):
        create_event_log("case-1", "Created")
        append_event("case-1", "Failover initiated")
        content = open(os.path.join(str(use_tmp_dir), "event-log-case-1.md")).read()
        # Should have at least two ISO timestamps (initial + appended)
        matches = ISO_8601_PATTERN.findall(content)
        assert len(matches) >= 2

    def test_raises_if_log_does_not_exist(self, use_tmp_dir):
        with pytest.raises(FileNotFoundError):
            append_event("nonexistent", "Should fail")

    def test_multiple_appends(self, use_tmp_dir):
        create_event_log("case-1", "Created")
        append_event("case-1", "Step 1")
        append_event("case-1", "Step 2")
        append_event("case-1", "Step 3")
        content = open(os.path.join(str(use_tmp_dir), "event-log-case-1.md")).read()
        lines = [l for l in content.splitlines() if l.startswith("- **")]
        assert len(lines) == 4  # initial + 3 appends


class TestFileNaming:
    def test_case_id_in_filename(self, use_tmp_dir):
        path = create_event_log("makita-case-20240101-001", "Created")
        assert "event-log-makita-case-20240101-001.md" in path

    def test_ticket_id_in_filename(self, use_tmp_dir):
        path = create_event_log("INC0010001", "Created")
        assert "event-log-INC0010001.md" in path
