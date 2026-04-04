"""
AgentCore policy enforcement tests for the MAKITA AgentCore stack.

Validates that the policy documents in makita-agentcore-stack.yaml enforce
the four governance constraints: resource prefix, Env tag, region, principal.

Validates: Requirements 23.9, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6
"""

import yaml
import pytest
from pathlib import Path


TEMPLATE_PATH = Path(__file__).parent.parent / "infrastructure" / "makita-agentcore-stack.yaml"


class _CfnLoader(yaml.SafeLoader):
    pass


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
def policies(template):
    """Extract policy documents from the Custom Resource properties."""
    resources = template.get("Resources", {})
    custom = resources.get("MakitaAgentCoreResources", {})
    props = custom.get("Properties", {})
    policy_list = props.get("Policies", [])
    return {p["PolicyName"]: p["PolicyDocument"]["Statement"] for p in policy_list}


EXPECTED_POLICIES = {
    "makita-failover-policy": "Failover",
    "makita-precheck-policy": "Pre-Check",
    "makita-postcheck-policy": "Post-Check",
}


def _deny_statements(stmts):
    return [s for s in stmts if s["Effect"] == "Deny"]


def _allow_statements(stmts):
    return [s for s in stmts if s["Effect"] == "Allow"]


class TestPolicyResourcesExist:
    def test_three_policies_exist(self, policies):
        for name in EXPECTED_POLICIES:
            assert name in policies, f"Expected policy '{name}' not found"

    def test_each_policy_has_statements(self, policies):
        for name in EXPECTED_POLICIES:
            assert len(policies[name]) >= 2


class TestDenyNonMakitaResources:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_denies_non_makita_resources(self, policies, policy_name):
        deny_stmts = _deny_statements(policies[policy_name])
        found = any(
            s.get("Condition", {}).get("StringNotLike", {}).get("aws:ResourceTag/Name") == "makita-*"
            for s in deny_stmts
        )
        assert found, f"Policy '{policy_name}' missing Deny for non-makita-* resources"


class TestDenyUnauthorizedRegions:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_denies_unauthorized_regions(self, policies, policy_name):
        deny_stmts = _deny_statements(policies[policy_name])
        found = False
        for s in deny_stmts:
            regions = s.get("Condition", {}).get("StringNotEquals", {}).get("aws:RequestedRegion", [])
            if isinstance(regions, str):
                regions = [regions]
            if "us-east-1" in regions and "us-west-2" in regions:
                found = True
                break
        assert found, f"Policy '{policy_name}' missing Deny for unauthorized regions"


class TestDenyNonMakitaPrincipals:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_denies_non_makita_principals(self, policies, policy_name):
        deny_stmts = _deny_statements(policies[policy_name])
        found = any(
            s.get("Condition", {}).get("StringNotLike", {}).get("aws:PrincipalTag/Name") == "makita-*"
            for s in deny_stmts
        )
        assert found, f"Policy '{policy_name}' missing Deny for non-makita-* principals"


class TestDenyMissingEnvTag:
    @pytest.mark.parametrize("policy_name,label", list(EXPECTED_POLICIES.items()))
    def test_policy_denies_resources_without_env_prod1(self, policies, policy_name, label):
        deny_stmts = _deny_statements(policies[policy_name])
        found = any(
            s.get("Condition", {}).get("StringNotEquals", {}).get("aws:ResourceTag/Env") == "prod1"
            for s in deny_stmts
        )
        assert found, f"{label} policy missing Deny for resources without Env=prod1"


class TestAllowWhenConstraintsPass:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_has_allow_statement(self, policies, policy_name):
        assert len(_allow_statements(policies[policy_name])) >= 1

    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_allow_targets_makita_resources(self, policies, policy_name):
        for s in _allow_statements(policies[policy_name]):
            resource = s.get("Resource", "")
            if isinstance(resource, list):
                assert any("makita-" in r for r in resource)
            else:
                assert "makita-" in resource

    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_allow_constrains_regions(self, policies, policy_name):
        for s in _allow_statements(policies[policy_name]):
            regions = s.get("Condition", {}).get("StringEquals", {}).get("aws:RequestedRegion", [])
            if isinstance(regions, str):
                regions = [regions]
            assert "us-east-1" in regions
            assert "us-west-2" in regions

    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_allow_constrains_principal(self, policies, policy_name):
        for s in _allow_statements(policies[policy_name]):
            principal = s.get("Condition", {}).get("StringEquals", {}).get("aws:PrincipalTag/Name", "")
            assert "makita-" in str(principal)
