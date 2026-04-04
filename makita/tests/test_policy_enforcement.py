"""
AgentCore policy enforcement tests for the MAKITA CloudFormation template.

Validates that each AgentCore Policy resource in infrastructure/makita-stack.yaml
enforces the four governance constraints:
  1. Resource prefix: makita-* (deny non-makita-* resources)
  2. Resource tag: Env=prod1 (deny resources without this tag)
  3. Region: us-east-1 and us-west-2 only (deny unauthorized regions)
  4. Principal prefix: makita-* (deny non-makita-* principals)

Also validates that an Allow statement permits operations when all constraints pass.

Validates: Requirements 23.9, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6
"""

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
    with open(TEMPLATE_PATH, "r") as f:
        return yaml.load(f, Loader=_CfnLoader)


@pytest.fixture(scope="module")
def resources(template):
    return template.get("Resources", {})


@pytest.fixture(scope="module")
def policy_resources(resources):
    """Extract all AgentCore Policy resources and their PolicyDocument statements."""
    policies = {}
    for name, res in resources.items():
        if res["Type"] == "AWS::AgentCore::Policy":
            doc = res["Properties"]["PolicyDocument"]
            policies[name] = doc["Statement"]
    return policies


# Map of logical resource name to friendly label for test IDs
EXPECTED_POLICIES = {
    "MakitaFailoverPolicy": "Failover",
    "MakitaPrecheckPolicy": "Pre-Check",
    "MakitaPostcheckPolicy": "Post-Check",
}


# =========================================================================
# Helpers
# =========================================================================

def _deny_statements(statements):
    return [s for s in statements if s["Effect"] == "Deny"]


def _allow_statements(statements):
    return [s for s in statements if s["Effect"] == "Allow"]


# =========================================================================
# Requirement 23.9 — Operations on non-makita-* resources are denied
# =========================================================================

class TestDenyNonMakitaResources:
    """Validates: Requirement 23.9 (resource prefix enforcement)"""

    @pytest.mark.parametrize("policy_name", EXPECTED_POLICIES.keys())
    def test_policy_denies_non_makita_resources(self, policy_resources, policy_name):
        """Each policy must have a Deny statement for non-makita-* resources."""
        stmts = policy_resources[policy_name]
        deny_stmts = _deny_statements(stmts)

        found = False
        for stmt in deny_stmts:
            condition = stmt.get("Condition", {})
            not_like = condition.get("StringNotLike", {})
            if "aws:ResourceTag/Name" in not_like:
                val = not_like["aws:ResourceTag/Name"]
                if val == "makita-*" or (isinstance(val, list) and "makita-*" in val):
                    found = True
                    break

        assert found, (
            f"Policy '{policy_name}' missing Deny statement for "
            "non-makita-* resources (StringNotLike aws:ResourceTag/Name)"
        )


# =========================================================================
# Requirement 23.9 — Operations targeting unauthorized regions are denied
# =========================================================================

class TestDenyUnauthorizedRegions:
    """Validates: Requirement 23.9 (region enforcement)"""

    @pytest.mark.parametrize("policy_name", EXPECTED_POLICIES.keys())
    def test_policy_denies_unauthorized_regions(self, policy_resources, policy_name):
        """Each policy must have a Deny statement for regions other than us-east-1/us-west-2."""
        stmts = policy_resources[policy_name]
        deny_stmts = _deny_statements(stmts)

        found = False
        for stmt in deny_stmts:
            condition = stmt.get("Condition", {})
            not_equals = condition.get("StringNotEquals", {})
            regions = not_equals.get("aws:RequestedRegion", [])
            if isinstance(regions, str):
                regions = [regions]
            if "us-east-1" in regions and "us-west-2" in regions:
                found = True
                break

        assert found, (
            f"Policy '{policy_name}' missing Deny statement for "
            "unauthorized regions (should deny all except us-east-1, us-west-2)"
        )


# =========================================================================
# Requirement 23.9 — Operations using non-makita-* principals are denied
# =========================================================================

class TestDenyNonMakitaPrincipals:
    """Validates: Requirement 23.9 (principal enforcement)"""

    @pytest.mark.parametrize("policy_name", EXPECTED_POLICIES.keys())
    def test_policy_denies_non_makita_principals(self, policy_resources, policy_name):
        """Each policy must have a Deny statement for non-makita-* principals."""
        stmts = policy_resources[policy_name]
        deny_stmts = _deny_statements(stmts)

        found = False
        for stmt in deny_stmts:
            condition = stmt.get("Condition", {})
            not_like = condition.get("StringNotLike", {})
            if "aws:PrincipalTag/Name" in not_like:
                val = not_like["aws:PrincipalTag/Name"]
                if val == "makita-*" or (isinstance(val, list) and "makita-*" in val):
                    found = True
                    break

        assert found, (
            f"Policy '{policy_name}' missing Deny statement for "
            "non-makita-* principals (StringNotLike aws:PrincipalTag/Name)"
        )


# =========================================================================
# Requirements 25.1–25.6 — Env=prod1 tag constraint (deny if missing)
# =========================================================================

class TestDenyMissingEnvTag:
    """Validates: Requirements 25.1, 25.2, 25.3, 25.4, 25.5, 25.6"""

    @pytest.mark.parametrize(
        "policy_name,label",
        [
            ("MakitaFailoverPolicy", "Failover"),
            ("MakitaPrecheckPolicy", "Pre-Check"),
            ("MakitaPostcheckPolicy", "Post-Check"),
        ],
    )
    def test_policy_denies_resources_without_env_prod1(
        self, policy_resources, policy_name, label
    ):
        """Each policy must deny operations on resources missing Env=prod1 tag."""
        stmts = policy_resources[policy_name]
        deny_stmts = _deny_statements(stmts)

        found = False
        for stmt in deny_stmts:
            condition = stmt.get("Condition", {})
            not_equals = condition.get("StringNotEquals", {})
            env_val = not_equals.get("aws:ResourceTag/Env")
            if env_val == "prod1":
                found = True
                break

        assert found, (
            f"{label} policy '{policy_name}' missing Deny statement for "
            "resources without Env=prod1 tag (StringNotEquals aws:ResourceTag/Env)"
        )


# =========================================================================
# Requirements 25.1–25.3 — Allow when all constraints pass
# =========================================================================

class TestAllowWhenConstraintsPass:
    """Validates: Requirements 25.1, 25.2, 25.3 (Allow statement present)"""

    @pytest.mark.parametrize("policy_name", EXPECTED_POLICIES.keys())
    def test_policy_has_allow_statement(self, policy_resources, policy_name):
        """Each policy must have an Allow statement for permitted operations."""
        stmts = policy_resources[policy_name]
        allow_stmts = _allow_statements(stmts)
        assert len(allow_stmts) >= 1, (
            f"Policy '{policy_name}' has no Allow statements"
        )

    @pytest.mark.parametrize("policy_name", EXPECTED_POLICIES.keys())
    def test_allow_targets_makita_resources(self, policy_resources, policy_name):
        """Allow statement Resource should reference makita-*."""
        stmts = policy_resources[policy_name]
        allow_stmts = _allow_statements(stmts)

        for stmt in allow_stmts:
            resource = stmt.get("Resource", "")
            if isinstance(resource, list):
                assert any("makita-" in r for r in resource), (
                    f"Policy '{policy_name}' Allow Resource list doesn't reference makita-*"
                )
            else:
                assert "makita-" in resource, (
                    f"Policy '{policy_name}' Allow Resource doesn't reference makita-*"
                )

    @pytest.mark.parametrize("policy_name", EXPECTED_POLICIES.keys())
    def test_allow_constrains_regions(self, policy_resources, policy_name):
        """Allow statement should constrain to us-east-1 and us-west-2."""
        stmts = policy_resources[policy_name]
        allow_stmts = _allow_statements(stmts)

        for stmt in allow_stmts:
            condition = stmt.get("Condition", {})
            regions = (
                condition.get("StringEquals", {})
                .get("aws:RequestedRegion", [])
            )
            if isinstance(regions, str):
                regions = [regions]
            assert "us-east-1" in regions, (
                f"Policy '{policy_name}' Allow missing us-east-1 region constraint"
            )
            assert "us-west-2" in regions, (
                f"Policy '{policy_name}' Allow missing us-west-2 region constraint"
            )

    @pytest.mark.parametrize("policy_name", EXPECTED_POLICIES.keys())
    def test_allow_constrains_principal(self, policy_resources, policy_name):
        """Allow statement should constrain principal to makita-*."""
        stmts = policy_resources[policy_name]
        allow_stmts = _allow_statements(stmts)

        for stmt in allow_stmts:
            condition = stmt.get("Condition", {})
            principal_val = (
                condition.get("StringEquals", {})
                .get("aws:PrincipalTag/Name", "")
            )
            assert "makita-" in str(principal_val), (
                f"Policy '{policy_name}' Allow missing makita-* principal constraint"
            )


# =========================================================================
# Structural: all three expected policies exist
# =========================================================================

class TestPolicyResourcesExist:
    """Verify all three AgentCore Policy resources are defined."""

    def test_three_policies_exist(self, policy_resources):
        for name in EXPECTED_POLICIES:
            assert name in policy_resources, (
                f"Expected AgentCore Policy '{name}' not found in template"
            )

    def test_each_policy_has_statements(self, policy_resources):
        for name in EXPECTED_POLICIES:
            stmts = policy_resources[name]
            assert len(stmts) >= 2, (
                f"Policy '{name}' should have at least an Allow and a Deny statement"
            )
