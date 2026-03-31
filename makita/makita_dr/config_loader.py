"""Configuration loader for makita-dr parameters from AWS Systems Manager Parameter Store."""

from typing import Dict

import boto3

from makita_dr.models import DRConfig


class MissingConfigError(Exception):
    """Raised when a required configuration parameter is missing from Parameter Store."""

    def __init__(self, parameter_name: str):
        self.parameter_name = parameter_name
        super().__init__(f"Missing required parameter: {parameter_name}")


class ConfigLoader:
    """Loads DR configuration from AWS Systems Manager Parameter Store."""

    PARAM_PREFIX = "/makita-dr/"

    # Parameters that use SecureString (sensitive values)
    _SECURE_PARAMS = frozenset({"servicenow_api_key", "slack_bot_token"})

    # Mapping from DRConfig field name to SSM parameter suffix
    _PARAM_MAP = {
        "primary_instance_id": "primary_instance_id",
        "replica_instance_id": "replica_instance_id",
        "primary_region": "primary_region",
        "dr_region": "dr_region",
        "replication_lag_threshold_seconds": "replication_lag_threshold_seconds",
        "dns_record_name": "dns_record_name",
        "dns_hosted_zone_id": "dns_hosted_zone_id",
        "servicenow_endpoint": "servicenow_endpoint",
        "servicenow_api_key": "servicenow_api_key",
        "slack_bot_token": "slack_bot_token",
        "slack_workspace_id": "slack_workspace_id",
        "support_severity": "support_severity",
        "support_service_code": "support_service_code",
        "support_category_code": "support_category_code",
        "mcp_server_endpoint": "mcp_server_endpoint",
        "lambda_function_arn": "lambda_function_arn",
        "guardrail_id": "guardrail_id",
        "guardrail_version": "guardrail_version",
        "cognito_user_pool_id": "cognito_user_pool_id",
        "cognito_client_id": "cognito_client_id",
    }

    def __init__(self, region: str = "us-east-1"):
        self._ssm = boto3.client("ssm", region_name=region)

    def load_config(self) -> DRConfig:
        """Load all makita-dr-* parameters from Parameter Store.

        Raises MissingConfigError if any required parameter is absent.
        """
        values: Dict[str, str] = {}
        for field_name, param_suffix in self._PARAM_MAP.items():
            secure = param_suffix in self._SECURE_PARAMS
            values[field_name] = self._get_parameter(param_suffix, secure=secure)

        # Convert replication_lag_threshold_seconds to int
        values["replication_lag_threshold_seconds"] = int(
            values["replication_lag_threshold_seconds"]
        )

        return DRConfig(**values)

    def _get_parameter(self, name: str, secure: bool = False) -> str:
        """Retrieve a single parameter. Uses WithDecryption for SecureString."""
        full_name = f"{self.PARAM_PREFIX}{name}"
        try:
            response = self._ssm.get_parameter(
                Name=full_name, WithDecryption=secure
            )
            return response["Parameter"]["Value"]
        except self._ssm.exceptions.ParameterNotFound:
            raise MissingConfigError(full_name)
