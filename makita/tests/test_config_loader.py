"""Unit tests for makita_dr.config_loader using moto to mock SSM Parameter Store."""

from typing import Optional, Set

import boto3
import pytest
from moto import mock_aws

from makita_dr.config_loader import ConfigLoader, MissingConfigError
from makita_dr.models import DRConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All required parameters with their test values and types
_ALL_PARAMS = {
    "primary_instance_id": ("makita-dr-primary", "String"),
    "replica_instance_id": ("makita-dr-replica", "String"),
    "primary_region": ("us-east-1", "String"),
    "dr_region": ("us-east-2", "String"),
    "replication_lag_threshold_seconds": ("30", "String"),
    "dns_record_name": ("db.example.com", "String"),
    "dns_hosted_zone_id": ("Z1234567890", "String"),
    "servicenow_endpoint": ("http://localhost:8080", "String"),
    "servicenow_api_key": ("sn-secret-key", "SecureString"),
    "slack_bot_token": ("xoxb-test-token", "SecureString"),
    "slack_workspace_id": ("W123", "String"),
    "support_severity": ("high", "String"),
    "support_service_code": ("amazon-rds", "String"),
    "support_category_code": ("failover", "String"),
    "mcp_server_endpoint": ("http://localhost:9000", "String"),
    "lambda_function_arn": (
        "arn:aws:lambda:us-east-1:123456789012:function:makita-dr-summary",
        "String",
    ),
    "guardrail_id": ("gr-123", "String"),
    "guardrail_version": ("1", "String"),
    "cognito_user_pool_id": ("us-east-1_abc", "String"),
    "cognito_client_id": ("client123", "String"),
}


def _put_all_params(ssm, *, exclude: Optional[Set[str]] = None):
    """Put all required parameters into SSM, optionally excluding some."""
    exclude = exclude or set()
    for name, (value, param_type) in _ALL_PARAMS.items():
        if name not in exclude:
            ssm.put_parameter(
                Name=f"/makita-dr/{name}",
                Value=value,
                Type=param_type,
            )


# ---------------------------------------------------------------------------
# MissingConfigError tests
# ---------------------------------------------------------------------------


class TestMissingConfigError:
    def test_stores_parameter_name(self):
        err = MissingConfigError("/makita-dr/some_param")
        assert err.parameter_name == "/makita-dr/some_param"

    def test_message_contains_parameter_name(self):
        err = MissingConfigError("/makita-dr/slack_bot_token")
        assert "/makita-dr/slack_bot_token" in str(err)

    def test_is_exception(self):
        assert issubclass(MissingConfigError, Exception)


# ---------------------------------------------------------------------------
# ConfigLoader tests
# ---------------------------------------------------------------------------


class TestConfigLoaderHappyPath:
    @mock_aws
    def test_load_config_returns_drconfig(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        _put_all_params(ssm)

        loader = ConfigLoader(region="us-east-1")
        config = loader.load_config()

        assert isinstance(config, DRConfig)

    @mock_aws
    def test_load_config_string_values(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        _put_all_params(ssm)

        config = ConfigLoader(region="us-east-1").load_config()

        assert config.primary_instance_id == "makita-dr-primary"
        assert config.replica_instance_id == "makita-dr-replica"
        assert config.primary_region == "us-east-1"
        assert config.dr_region == "us-east-2"
        assert config.dns_record_name == "db.example.com"
        assert config.dns_hosted_zone_id == "Z1234567890"
        assert config.servicenow_endpoint == "http://localhost:8080"
        assert config.slack_workspace_id == "W123"
        assert config.support_severity == "high"
        assert config.mcp_server_endpoint == "http://localhost:9000"
        assert config.guardrail_id == "gr-123"
        assert config.cognito_user_pool_id == "us-east-1_abc"
        assert config.cognito_client_id == "client123"

    @mock_aws
    def test_load_config_int_conversion(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        _put_all_params(ssm)

        config = ConfigLoader(region="us-east-1").load_config()

        assert config.replication_lag_threshold_seconds == 30
        assert isinstance(config.replication_lag_threshold_seconds, int)

    @mock_aws
    def test_load_config_secure_string_values(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        _put_all_params(ssm)

        config = ConfigLoader(region="us-east-1").load_config()

        assert config.servicenow_api_key == "sn-secret-key"
        assert config.slack_bot_token == "xoxb-test-token"


class TestConfigLoaderMissingParams:
    @mock_aws
    def test_missing_primary_instance_id(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        _put_all_params(ssm, exclude={"primary_instance_id"})

        loader = ConfigLoader(region="us-east-1")
        with pytest.raises(MissingConfigError) as exc_info:
            loader.load_config()

        assert exc_info.value.parameter_name == "/makita-dr/primary_instance_id"

    @mock_aws
    def test_missing_secure_param(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        _put_all_params(ssm, exclude={"slack_bot_token"})

        loader = ConfigLoader(region="us-east-1")
        with pytest.raises(MissingConfigError) as exc_info:
            loader.load_config()

        assert exc_info.value.parameter_name == "/makita-dr/slack_bot_token"

    @mock_aws
    def test_missing_mcp_param(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        _put_all_params(ssm, exclude={"lambda_function_arn"})

        loader = ConfigLoader(region="us-east-1")
        with pytest.raises(MissingConfigError) as exc_info:
            loader.load_config()

        assert exc_info.value.parameter_name == "/makita-dr/lambda_function_arn"

    @mock_aws
    def test_no_params_at_all(self):
        """When no parameters exist, the first one looked up should raise."""
        loader = ConfigLoader(region="us-east-1")
        with pytest.raises(MissingConfigError):
            loader.load_config()


class TestConfigLoaderParamPrefix:
    def test_prefix_value(self):
        assert ConfigLoader.PARAM_PREFIX == "/makita-dr/"

    @mock_aws
    def test_get_parameter_uses_prefix(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        ssm.put_parameter(
            Name="/makita-dr/test_param", Value="test_value", Type="String"
        )

        loader = ConfigLoader(region="us-east-1")
        value = loader._get_parameter("test_param")
        assert value == "test_value"

    @mock_aws
    def test_get_parameter_secure(self):
        ssm = boto3.client("ssm", region_name="us-east-1")
        ssm.put_parameter(
            Name="/makita-dr/secret", Value="s3cret", Type="SecureString"
        )

        loader = ConfigLoader(region="us-east-1")
        value = loader._get_parameter("secret", secure=True)
        assert value == "s3cret"

    @mock_aws
    def test_get_parameter_missing_raises(self):
        loader = ConfigLoader(region="us-east-1")
        with pytest.raises(MissingConfigError) as exc_info:
            loader._get_parameter("nonexistent")

        assert exc_info.value.parameter_name == "/makita-dr/nonexistent"
