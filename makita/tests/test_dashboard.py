"""
CloudWatch Dashboard tests for the MAKITA CloudFormation template.

Validates the CloudWatch Dashboard resource in infrastructure/makita-stack.yaml
by parsing the YAML directly and asserting on dashboard naming, widget regions,
instance references, and metric types.

Validates: Requirement 23.14
"""

import json
import yaml
import pytest
from pathlib import Path


TEMPLATE_PATH = Path(__file__).parent.parent / "infrastructure" / "makita-stack.yaml"


# ---------------------------------------------------------------------------
# Custom YAML loader that handles CloudFormation intrinsic functions
# ---------------------------------------------------------------------------
class _CfnLoader(yaml.SafeLoader):
    """YAML loader that treats CloudFormation tags as plain data."""


def _cfn_tag_constructor(loader, tag_suffix, node):
    """Generic constructor for any CloudFormation !Tag."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_CfnLoader.add_multi_constructor("!", _cfn_tag_constructor)


@pytest.fixture(scope="module")
def template():
    """Load and parse the CloudFormation template."""
    with open(TEMPLATE_PATH, "r") as f:
        return yaml.load(f, Loader=_CfnLoader)


@pytest.fixture(scope="module")
def dashboard_resource(template):
    """Extract the CloudWatch Dashboard resource."""
    resources = template.get("Resources", {})
    dashboards = {
        k: v for k, v in resources.items()
        if v["Type"] == "AWS::CloudWatch::Dashboard"
    }
    assert len(dashboards) >= 1, "Expected at least one CloudWatch Dashboard resource"
    # Return the first (and expected only) dashboard
    name, res = next(iter(dashboards.items()))
    return res


@pytest.fixture(scope="module")
def dashboard_body(dashboard_resource):
    """Parse the DashboardBody JSON from the dashboard resource."""
    body_raw = dashboard_resource["Properties"]["DashboardBody"]
    # DashboardBody comes from !Sub so it's a string after YAML loading
    return json.loads(body_raw)


@pytest.fixture(scope="module")
def widgets(dashboard_body):
    """Extract the widgets list from the dashboard body."""
    return dashboard_body.get("widgets", [])


@pytest.fixture(scope="module")
def metric_widgets(widgets):
    """Extract only metric-type widgets (exclude text widgets)."""
    return [w for w in widgets if w.get("type") == "metric"]


# =========================================================================
# Requirement 23.14 — Dashboard name uses makita- prefix
# =========================================================================

class TestDashboardNaming:
    """Validate the dashboard name starts with makita-."""

    def test_dashboard_name_starts_with_makita(self, dashboard_resource):
        name = dashboard_resource["Properties"]["DashboardName"]
        assert name.startswith("makita-"), (
            f"DashboardName '{name}' does not start with 'makita-'"
        )


# =========================================================================
# Requirement 23.14 — Dashboard metrics reference both regions
# =========================================================================

class TestDashboardRegions:
    """Validate widgets reference metrics from us-east-1 and us-west-2."""

    def test_widgets_reference_us_east_1(self, metric_widgets):
        regions = {w["properties"].get("region") for w in metric_widgets}
        assert "us-east-1" in regions, (
            "No metric widget references us-east-1"
        )

    def test_widgets_reference_us_west_2(self, metric_widgets):
        regions = {w["properties"].get("region") for w in metric_widgets}
        assert "us-west-2" in regions, (
            "No metric widget references us-west-2"
        )


# =========================================================================
# Requirement 23.14 — Dashboard references PostgreSQL instances
# =========================================================================

class TestDashboardInstances:
    """Validate widgets reference makita-pg-primary and makita-pg-replica."""

    def _all_db_identifiers(self, metric_widgets):
        """Collect all DBInstanceIdentifier values from metric widgets."""
        identifiers = set()
        for w in metric_widgets:
            for metric_entry in w["properties"].get("metrics", []):
                # Metric format: ["Namespace", "MetricName", "DimName", "DimValue", ...]
                for i, item in enumerate(metric_entry):
                    if item == "DBInstanceIdentifier" and i + 1 < len(metric_entry):
                        identifiers.add(metric_entry[i + 1])
        return identifiers

    def test_widgets_reference_makita_pg_primary(self, metric_widgets):
        ids = self._all_db_identifiers(metric_widgets)
        assert "makita-pg-primary" in ids, (
            f"No widget references makita-pg-primary. Found: {ids}"
        )

    def test_widgets_reference_makita_pg_replica(self, metric_widgets):
        ids = self._all_db_identifiers(metric_widgets)
        assert "makita-pg-replica" in ids, (
            f"No widget references makita-pg-replica. Found: {ids}"
        )


# =========================================================================
# Requirement 23.14 — Dashboard includes key metrics
# =========================================================================

class TestDashboardMetrics:
    """Validate widgets include CPU utilization and replication lag metrics."""

    def _all_metric_names(self, metric_widgets):
        """Collect all metric names from metric widgets."""
        names = set()
        for w in metric_widgets:
            for metric_entry in w["properties"].get("metrics", []):
                # Metric format: ["Namespace", "MetricName", ...]
                if len(metric_entry) >= 2:
                    names.add(metric_entry[1])
        return names

    def test_includes_cpu_utilization(self, metric_widgets):
        names = self._all_metric_names(metric_widgets)
        assert "CPUUtilization" in names, (
            f"No widget includes CPUUtilization metric. Found: {names}"
        )

    def test_includes_replica_lag(self, metric_widgets):
        names = self._all_metric_names(metric_widgets)
        assert "ReplicaLag" in names, (
            f"No widget includes ReplicaLag metric. Found: {names}"
        )
