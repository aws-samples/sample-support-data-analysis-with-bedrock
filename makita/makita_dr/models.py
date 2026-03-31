"""Data models for the makita-dr DR reference architecture."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class FailoverStatus(Enum):
    """Status of the overall DR failover workflow."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class CheckStatus(Enum):
    """Status of an individual validation check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DRConfig:
    """Configuration loaded from Parameter Store."""

    # RDS
    primary_instance_id: str
    replica_instance_id: str
    primary_region: str  # us-east-1
    dr_region: str  # us-east-2
    replication_lag_threshold_seconds: int
    dns_record_name: str
    dns_hosted_zone_id: str

    # ServiceNow stub
    servicenow_endpoint: str
    servicenow_api_key: str  # SecureString

    # Slack
    slack_bot_token: str  # SecureString
    slack_workspace_id: str

    # AWS Support
    support_severity: str
    support_service_code: str
    support_category_code: str

    # MCP Server
    mcp_server_endpoint: str
    lambda_function_arn: str
    guardrail_id: str
    guardrail_version: str

    # Cognito
    cognito_user_pool_id: str
    cognito_client_id: str


@dataclass
class CheckResult:
    """Result of a single validation check."""

    check_name: str
    status: CheckStatus
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    details: Optional[dict] = None


@dataclass
class PreCheckResult:
    """Aggregated result of all pre-failover checks."""

    checks: list  # list[CheckResult]
    overall_status: CheckStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def passed(self) -> bool:
        return self.overall_status == CheckStatus.PASSED


@dataclass
class PostCheckResult:
    """Aggregated result of all post-failover checks."""

    checks: list  # list[CheckResult]
    overall_status: CheckStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def passed(self) -> bool:
        return self.overall_status == CheckStatus.PASSED


@dataclass
class PromoteResult:
    """Result of RDS read replica promotion."""

    success: bool
    promoted_instance_id: str
    promoted_endpoint: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DNSUpdateResult:
    """Result of DNS record update."""

    success: bool
    record_name: str
    new_value: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FailoverEvent:
    """Complete record of a DR failover event."""

    event_id: str
    status: FailoverStatus
    initiated_at: datetime
    completed_at: Optional[datetime] = None
    primary_region: str = "us-east-1"
    dr_region: str = "us-east-2"
    primary_instance_id: str = ""
    replica_instance_id: str = ""
    pre_check_result: Optional[PreCheckResult] = None
    post_check_result: Optional[PostCheckResult] = None
    promote_result: Optional[PromoteResult] = None
    dns_update_result: Optional[DNSUpdateResult] = None
    servicenow_ticket_id: Optional[str] = None
    aws_support_case_id: Optional[str] = None
    slack_channel_id: Optional[str] = None
    error_message: Optional[str] = None
    actions_log: list = field(default_factory=list)  # list[str]


@dataclass
class FailoverResult:
    """Final result of the DR failover workflow."""

    event: FailoverEvent
    summary: Optional[str] = None
