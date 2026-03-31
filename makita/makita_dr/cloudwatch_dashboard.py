"""CloudWatch Dashboard manager for the makita-dr DR reference architecture."""

import json

import boto3

from makita_dr.models import DRConfig


class CloudWatchDashboardManager:
    """Creates and manages the makita-dr-dashboard CloudWatch Dashboard."""

    DASHBOARD_NAME = "makita-dr-dashboard"

    def __init__(self, config: DRConfig):
        self._config = config
        self._cw_client = boto3.client("cloudwatch", region_name=config.primary_region)

    def create_dashboard(self) -> None:
        """Create the CloudWatch Dashboard with widgets for primary/DR region RDS metrics and cross-region comparison."""
        body = self._build_dashboard_body()
        self._cw_client.put_dashboard(
            DashboardName=self.DASHBOARD_NAME,
            DashboardBody=json.dumps(body),
        )

    def _build_dashboard_body(self) -> dict:
        """Build the dashboard JSON body with all widget definitions."""
        widgets = []
        y = 0

        # Primary region RDS metrics
        widgets.append(self._metric_widget(
            title="Primary Region - DatabaseConnections",
            metrics=[[
                "AWS/RDS", "DatabaseConnections",
                "DBInstanceIdentifier", self._config.primary_instance_id,
            ]],
            region=self._config.primary_region,
            x=0, y=y, width=8, height=6,
        ))
        widgets.append(self._metric_widget(
            title="Primary Region - CPUUtilization",
            metrics=[[
                "AWS/RDS", "CPUUtilization",
                "DBInstanceIdentifier", self._config.primary_instance_id,
            ]],
            region=self._config.primary_region,
            x=8, y=y, width=8, height=6,
        ))
        widgets.append(self._metric_widget(
            title="Primary Region - DB Connections (Count)",
            metrics=[[
                "AWS/RDS", "DatabaseConnections",
                "DBInstanceIdentifier", self._config.primary_instance_id,
            ]],
            region=self._config.primary_region,
            x=16, y=y, width=8, height=6,
            stat="Sum",
        ))
        y += 6

        # DR region RDS metrics
        widgets.append(self._metric_widget(
            title="DR Region - ReplicaLag",
            metrics=[[
                "AWS/RDS", "ReplicaLag",
                "DBInstanceIdentifier", self._config.replica_instance_id,
            ]],
            region=self._config.dr_region,
            x=0, y=y, width=8, height=6,
        ))
        widgets.append(self._metric_widget(
            title="DR Region - DatabaseConnections",
            metrics=[[
                "AWS/RDS", "DatabaseConnections",
                "DBInstanceIdentifier", self._config.replica_instance_id,
            ]],
            region=self._config.dr_region,
            x=8, y=y, width=8, height=6,
        ))
        widgets.append(self._metric_widget(
            title="DR Region - CPUUtilization",
            metrics=[[
                "AWS/RDS", "CPUUtilization",
                "DBInstanceIdentifier", self._config.replica_instance_id,
            ]],
            region=self._config.dr_region,
            x=16, y=y, width=8, height=6,
        ))
        y += 6

        # Cross-region comparison widgets
        widgets.append(self._metric_widget(
            title="Cross-Region - DatabaseConnections Comparison",
            metrics=[
                [
                    "AWS/RDS", "DatabaseConnections",
                    "DBInstanceIdentifier", self._config.primary_instance_id,
                    {"region": self._config.primary_region, "label": "Primary"},
                ],
                [
                    "AWS/RDS", "DatabaseConnections",
                    "DBInstanceIdentifier", self._config.replica_instance_id,
                    {"region": self._config.dr_region, "label": "DR"},
                ],
            ],
            region=self._config.primary_region,
            x=0, y=y, width=12, height=6,
        ))
        widgets.append(self._metric_widget(
            title="Cross-Region - CPUUtilization Comparison",
            metrics=[
                [
                    "AWS/RDS", "CPUUtilization",
                    "DBInstanceIdentifier", self._config.primary_instance_id,
                    {"region": self._config.primary_region, "label": "Primary"},
                ],
                [
                    "AWS/RDS", "CPUUtilization",
                    "DBInstanceIdentifier", self._config.replica_instance_id,
                    {"region": self._config.dr_region, "label": "DR"},
                ],
            ],
            region=self._config.primary_region,
            x=12, y=y, width=12, height=6,
        ))

        return {"widgets": widgets}

    @staticmethod
    def _metric_widget(
        title: str,
        metrics: list,
        region: str,
        x: int,
        y: int,
        width: int,
        height: int,
        stat: str = "Average",
        period: int = 300,
    ) -> dict:
        """Build a single CloudWatch metric widget definition."""
        return {
            "type": "metric",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "properties": {
                "title": title,
                "metrics": metrics,
                "region": region,
                "stat": stat,
                "period": period,
                "view": "timeSeries",
            },
        }
