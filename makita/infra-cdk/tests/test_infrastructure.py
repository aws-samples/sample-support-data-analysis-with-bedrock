"""
Infrastructure provisioning tests for the MAKITA CloudFormation template.

Validates the CloudFormation template at infrastructure/workloads/postgresql/makita-postgresql-stack.yaml
by parsing the YAML directly and asserting on resource structure, naming
conventions, tags, Parameter Store parameters, and tagging exceptions.

Validates: Requirements 23.1, 23.2, 24.1, 24.2, 24.3, 24.4, 24.5, 24.6,
           24.7, 24.8, 24.9, 24.10
"""

import re
import yaml
import pytest
from pathlib import Path


TEMPLATE_PATH = Path(__file__).parent.parent.parent / "infra-cfn" / "workloads" / "postgresql" / "makita-postgresql-stack.yaml"


# ---------------------------------------------------------------------------
# Custom YAML loader that handles CloudFormation intrinsic functions
# (!Ref, !GetAtt, !Sub, !Select, !GetAZs, !Join, !If, !Equals, etc.)
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


# Register a multi-constructor that catches every ! tag
_CfnLoader.add_multi_constructor("!", _cfn_tag_constructor)


@pytest.fixture(scope="module")
def template():
    """Load and parse the CloudFormation template."""
    with open(TEMPLATE_PATH, "r") as f:
        return yaml.load(f, Loader=_CfnLoader)


@pytest.fixture(scope="module")
def resources(template):
    """Extract the Resources section from the template."""
    return template.get("Resources", {})


@pytest.fixture(scope="module")
def outputs(template):
    """Extract the Outputs section from the template."""
    return template.get("Outputs", {})


# -------------------------------------------------------------------------
# Helper: resource types that do NOT support CloudFormation Tags property
# -------------------------------------------------------------------------
TAGGING_EXCEPTION_TYPES = {
    "AWS::EC2::VPCGatewayAttachment",
    "AWS::SecretsManager::SecretTargetAttachment",
}

# Resource types where tags use map syntax (Key: Value) instead of list-of-dicts
MAP_TAG_TYPES = {
    "AWS::SSM::Parameter",
}

# Mandatory tags every taggable resource must carry
MANDATORY_TAGS = {
    "auto-delete": "no",
    "Env": "prod1",
}


def _extract_tags(resource_props, resource_type):
    """Return a dict of {Key: Value} from a resource's Tags property.

    Handles both list-of-dicts format (most resources) and map format
    (e.g., AWS::SSM::Parameter).
    """
    tags_raw = resource_props.get("Tags", {})
    if isinstance(tags_raw, list):
        return {t["Key"]: t["Value"] for t in tags_raw}
    elif isinstance(tags_raw, dict):
        return dict(tags_raw)
    return {}


# =========================================================================
# Requirement 23.1 — CloudFormation stack deployment & makita- prefix
# =========================================================================

class TestCloudFormationStructure:
    """Validate the CloudFormation template is well-formed."""

    def test_template_has_format_version(self, template):
        assert "AWSTemplateFormatVersion" in template

    def test_template_has_description(self, template):
        assert "Description" in template
        assert "MAKITA" in template["Description"]

    def test_template_has_resources(self, template):
        assert "Resources" in template
        assert len(template["Resources"]) > 0

    def test_template_has_outputs(self, template):
        assert "Outputs" in template


class TestMakitaPrefixOnResources:
    """Validate all resource names/identifiers use the makita- prefix.

    Validates: Requirement 23.1
    """

    def test_all_logical_ids_start_with_makita(self, resources):
        """Every logical resource ID should start with 'Makita'."""
        for logical_id in resources:
            assert logical_id.startswith("Makita"), (
                f"Logical ID '{logical_id}' does not start with 'Makita'"
            )

    def test_rds_instance_identifiers_have_makita_prefix(self, resources):
        """RDS DBInstanceIdentifier values should start with makita-."""
        for name, res in resources.items():
            if res["Type"] == "AWS::RDS::DBInstance":
                db_id = res["Properties"].get("DBInstanceIdentifier", "")
                assert db_id.startswith("makita-"), (
                    f"RDS instance '{name}' identifier '{db_id}' missing makita- prefix"
                )

    def test_iam_role_names_have_makita_prefix(self, resources):
        """IAM RoleName values should start with makita-."""
        for name, res in resources.items():
            if res["Type"] == "AWS::IAM::Role":
                role_name = res["Properties"].get("RoleName", "")
                assert role_name.startswith("makita-"), (
                    f"IAM role '{name}' RoleName '{role_name}' missing makita- prefix"
                )

    def test_bedrock_guardrail_names_have_makita_prefix(self, resources):
        """Bedrock Guardrail Name values should start with makita-."""
        for name, res in resources.items():
            if res["Type"] == "AWS::Bedrock::Guardrail":
                guardrail_name = res["Properties"].get("Name", "")
                assert guardrail_name.startswith("makita-"), (
                    f"Bedrock Guardrail '{name}' Name '{guardrail_name}' "
                    "missing makita- prefix"
                )


class TestCorrectRegions:
    """Validate resources reference the correct regions (us-east-1 / us-west-2).

    Validates: Requirement 23.1
    """

    def test_primary_region_parameter_value(self, resources):
        param = resources["MakitaParamPrimaryRegion"]["Properties"]
        assert param["Value"] == "us-east-1"

    def test_dr_region_parameter_value(self, resources):
        param = resources["MakitaParamDrRegion"]["Properties"]
        assert param["Value"] == "us-west-2"

    def test_agentcore_policies_allow_correct_regions(self, resources):
        """Each AgentCore Policy should reference us-east-1 and us-west-2."""
        for name, res in resources.items():
            if res["Type"] != "AWS::AgentCore::Policy":
                continue
            doc = res["Properties"]["PolicyDocument"]
            statements = doc["Statement"]
            allow_stmts = [s for s in statements if s["Effect"] == "Allow"]
            for stmt in allow_stmts:
                regions = (
                    stmt.get("Condition", {})
                    .get("StringEquals", {})
                    .get("aws:RequestedRegion", [])
                )
                assert "us-east-1" in regions, (
                    f"Policy '{name}' Allow statement missing us-east-1"
                )
                assert "us-west-2" in regions, (
                    f"Policy '{name}' Allow statement missing us-west-2"
                )


# =========================================================================
# Requirement 23.2 — Parameter Store parameters with /makita/ prefix
# =========================================================================

class TestParameterStoreParameters:
    """Validate SSM Parameters use /makita/ prefix and expected values.

    Validates: Requirement 23.2
    """

    EXPECTED_PARAMS = {
        "/makita/db/primary-endpoint",
        "/makita/db/replica-endpoint",
        "/makita/db/primary-region",
        "/makita/db/dr-region",
        "/makita/db/cluster-name",
        "/makita/db/replication-status",
        "/makita/db/port",
        "/makita/mcp/failover-server-arn",
        "/makita/mcp/precheck-server-arn",
        "/makita/mcp/postcheck-server-arn",
    }

    def test_all_ssm_parameters_have_makita_prefix(self, resources):
        """Every SSM Parameter Name should start with /makita/."""
        for name, res in resources.items():
            if res["Type"] != "AWS::SSM::Parameter":
                continue
            param_name = res["Properties"].get("Name", "")
            assert param_name.startswith("/makita/"), (
                f"SSM Parameter '{name}' Name '{param_name}' missing /makita/ prefix"
            )

    def test_expected_parameters_exist(self, resources):
        """All expected SSM parameters should be defined in the template."""
        actual_names = set()
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                actual_names.add(res["Properties"]["Name"])
        missing = self.EXPECTED_PARAMS - actual_names
        assert not missing, f"Missing SSM parameters: {missing}"

    def test_primary_region_param_value(self, resources):
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/primary-region":
                    assert res["Properties"]["Value"] == "us-east-1"

    def test_dr_region_param_value(self, resources):
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/dr-region":
                    assert res["Properties"]["Value"] == "us-west-2"

    def test_port_param_value(self, resources):
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/port":
                    assert res["Properties"]["Value"] == "5432"

    def test_cluster_name_param_value(self, resources):
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/cluster-name":
                    assert res["Properties"]["Value"] == "makita-pg-cluster"

    def test_replication_status_param_value(self, resources):
        for name, res in resources.items():
            if res["Type"] == "AWS::SSM::Parameter":
                if res["Properties"]["Name"] == "/makita/db/replication-status":
                    assert res["Properties"]["Value"] == "active"


# =========================================================================
# Requirements 24.1–24.9 — Mandatory resource tags
# =========================================================================

class TestMandatoryResourceTags:
    """Validate mandatory tags (auto-delete=no, Env=prod1) on all taggable resources.

    Validates: Requirements 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7, 24.8, 24.9
    """

    def _taggable_resources(self, resources):
        """Yield (logical_id, resource) for resources that support tags."""
        for logical_id, res in resources.items():
            rtype = res["Type"]
            if rtype not in TAGGING_EXCEPTION_TYPES:
                yield logical_id, res

    def test_all_taggable_resources_have_auto_delete_tag(self, resources):
        """Every taggable resource must have auto-delete=no."""
        for logical_id, res in self._taggable_resources(resources):
            tags = _extract_tags(res.get("Properties", {}), res["Type"])
            assert tags.get("auto-delete") == "no", (
                f"Resource '{logical_id}' ({res['Type']}) missing "
                "tag auto-delete=no"
            )

    def test_all_taggable_resources_have_env_tag(self, resources):
        """Every taggable resource must have Env=prod1."""
        for logical_id, res in self._taggable_resources(resources):
            tags = _extract_tags(res.get("Properties", {}), res["Type"])
            assert tags.get("Env") == "prod1", (
                f"Resource '{logical_id}' ({res['Type']}) missing "
                "tag Env=prod1"
            )

    def test_postgresql_resources_tagged(self, resources):
        """Requirement 24.3 — PostgreSQL instances carry mandatory tags."""
        rds_resources = {
            k: v for k, v in resources.items()
            if v["Type"] == "AWS::RDS::DBInstance"
        }
        assert len(rds_resources) >= 1, "Expected at least 1 RDS instance"
        for logical_id, res in rds_resources.items():
            tags = _extract_tags(res["Properties"], res["Type"])
            for key, val in MANDATORY_TAGS.items():
                assert tags.get(key) == val, (
                    f"RDS '{logical_id}' missing tag {key}={val}"
                )

    def test_iam_roles_tagged(self, resources):
        """Requirement 24.4 — IAM roles carry mandatory tags."""
        iam_roles = {
            k: v for k, v in resources.items()
            if v["Type"] == "AWS::IAM::Role"
        }
        assert len(iam_roles) >= 1, "Expected at least 1 IAM role"
        for logical_id, res in iam_roles.items():
            tags = _extract_tags(res["Properties"], res["Type"])
            for key, val in MANDATORY_TAGS.items():
                assert tags.get(key) == val, (
                    f"IAM Role '{logical_id}' missing tag {key}={val}"
                )

    def test_ssm_parameters_tagged(self, resources):
        """Requirement 24.5 — SSM Parameters carry mandatory tags."""
        ssm_params = {
            k: v for k, v in resources.items()
            if v["Type"] == "AWS::SSM::Parameter"
        }
        assert len(ssm_params) >= 1, "Expected at least 1 SSM Parameter"
        for logical_id, res in ssm_params.items():
            tags = _extract_tags(res["Properties"], res["Type"])
            for key, val in MANDATORY_TAGS.items():
                assert tags.get(key) == val, (
                    f"SSM Parameter '{logical_id}' missing tag {key}={val}"
                )

    def test_bedrock_guardrails_tagged(self, resources):
        """Requirement 24.7 — Bedrock Guardrails carry mandatory tags."""
        guardrails = {
            k: v for k, v in resources.items()
            if v["Type"] == "AWS::Bedrock::Guardrail"
        }
        assert len(guardrails) >= 1, "Expected at least 1 Bedrock Guardrail"
        for logical_id, res in guardrails.items():
            tags = _extract_tags(res["Properties"], res["Type"])
            for key, val in MANDATORY_TAGS.items():
                assert tags.get(key) == val, (
                    f"Bedrock Guardrail '{logical_id}' missing tag {key}={val}"
                )


