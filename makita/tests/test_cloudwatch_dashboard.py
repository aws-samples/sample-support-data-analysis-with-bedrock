"""Unit tests for CloudWatch Dashboard manager."""

import json

import boto3
import pytest
from moto import mock_aws

from makita_dr.cloudwatch_dashboard import CloudWatchDashboardManager
from makita_dr.models import DRConfig


def _make_config(**overrides) -> DRConfig:
    defaults = dict(
        primary_instance_id="makita-dr-primary",
        replica_instance_id="makita-dr-replica",
        primary_region="us-east-1",
        dr_region="us-east-2",
        replication_lag_threshold_seconds=30,
        dns_record_name="db.example.com",
        dns_hosted_zone_id="Z12345",
        servicenow_endpoint="http://localhost:8080",
        servicenow_api_key="key",
        slack_bot_token="xoxb-token",
        slack_workspace_id="W123",
        support_severity="high",
        support_service_code="amazon-rds",
        support_category_code="other",
        mcp_server_endpoint="http://localhost:9000",
        lambda_function_arn="arn:aws:lambda:us-east-1:123456789012:function:makita-dr-summary",
        guardrail_id="gr-123",
        guardrail_version="1",
        cognito_user_pool_id="us-east-1_abc",
        cognito_client_id="client123",
    )
    defaults.update(overrides)
    return DRConfig(**defaults)


class TestCloudWatchDashboardManager:
    """Tests for CloudWatchDashboardManager."""

    def test_dashboard_name_has_makita_dr_prefix(self):
        assert CloudWatchDashboardManager.DASHBOARD_NAME.startswith("makita-dr-")

    @mock_aws
    def test_create_dashboard_puts_dashboard(self):
        config = _make_config()
        mgr = CloudWatchDashboardManager(config)
        mgr.create_dashboard()

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        resp = cw.list_dashboards()
        names = [e["DashboardName"] for e in resp["DashboardEntries"]]
        assert "makita-dr-dashboard" in names

    @mock_aws
    def test_dashboard_body_contains_all_widget_sections(self):
        config = _make_config()
        mgr = CloudWatchDashboardManager(config)
        mgr.create_dashboard()

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        resp = cw.get_dashboard(DashboardName="makita-dr-dashboard")
        body = json.loads(resp["DashboardBody"])

        widgets = body["widgets"]
        titles = [w["properties"]["title"] for w in widgets]

        # Primary region widgets (Req 12.2)
        assert any("Primary" in t and "DatabaseConnections" in t for t in titles)
        assert any("Primary" in t and "CPUUtilization" in t for t in titles)

        # DR region widgets (Req 12.3)
        assert any("DR" in t and "ReplicaLag" in t for t in titles)
        assert any("DR" in t and "DatabaseConnections" in t for t in titles)
        assert any("DR" in t and "CPUUtilization" in t for t in titles)

        # Cross-region comparison widgets (Req 12.4)
        assert any("Cross-Region" in t for t in titles)

    @mock_aws
    def test_primary_widgets_reference_primary_instance(self):
        config = _make_config(primary_instance_id="my-primary-db")
        mgr = CloudWatchDashboardManager(config)
        mgr.create_dashboard()

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        resp = cw.get_dashboard(DashboardName="makita-dr-dashboard")
        body = json.loads(resp["DashboardBody"])

        primary_widgets = [
            w for w in body["widgets"]
            if "Primary Region" in w["properties"]["title"]
        ]
        for w in primary_widgets:
            flat_metrics = str(w["properties"]["metrics"])
            assert "my-primary-db" in flat_metrics

    @mock_aws
    def test_dr_widgets_reference_replica_instance(self):
        config = _make_config(replica_instance_id="my-replica-db")
        mgr = CloudWatchDashboardManager(config)
        mgr.create_dashboard()

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        resp = cw.get_dashboard(DashboardName="makita-dr-dashboard")
        body = json.loads(resp["DashboardBody"])

        dr_widgets = [
            w for w in body["widgets"]
            if "DR Region" in w["properties"]["title"]
        ]
        for w in dr_widgets:
            flat_metrics = str(w["properties"]["metrics"])
            assert "my-replica-db" in flat_metrics

    @mock_aws
    def test_cross_region_widgets_contain_both_instances(self):
        config = _make_config(
            primary_instance_id="primary-inst",
            replica_instance_id="replica-inst",
        )
        mgr = CloudWatchDashboardManager(config)
        mgr.create_dashboard()

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        resp = cw.get_dashboard(DashboardName="makita-dr-dashboard")
        body = json.loads(resp["DashboardBody"])

        cross_widgets = [
            w for w in body["widgets"]
            if "Cross-Region" in w["properties"]["title"]
        ]
        assert len(cross_widgets) >= 2
        for w in cross_widgets:
            flat = str(w["properties"]["metrics"])
            assert "primary-inst" in flat
            assert "replica-inst" in flat

    @mock_aws
    def test_cross_region_widgets_have_primary_and_dr_labels(self):
        config = _make_config()
        mgr = CloudWatchDashboardManager(config)
        mgr.create_dashboard()

        cw = boto3.client("cloudwatch", region_name="us-east-1")
        resp = cw.get_dashboard(DashboardName="makita-dr-dashboard")
        body = json.loads(resp["DashboardBody"])

        cross_widgets = [
            w for w in body["widgets"]
            if "Cross-Region" in w["properties"]["title"]
        ]
        for w in cross_widgets:
            flat = str(w["properties"]["metrics"])
            assert "Primary" in flat
            assert "DR" in flat

    def test_build_dashboard_body_returns_widgets_key(self):
        config = _make_config()
        mgr = CloudWatchDashboardManager(config)
        # Access internal method directly to test structure
        body = mgr._build_dashboard_body()
        assert "widgets" in body
        assert isinstance(body["widgets"], list)
        assert len(body["widgets"]) == 8  # 3 primary + 3 DR + 2 cross-region

    def test_all_widgets_are_metric_type(self):
        config = _make_config()
        mgr = CloudWatchDashboardManager(config)
        body = mgr._build_dashboard_body()
        for w in body["widgets"]:
            assert w["type"] == "metric"
