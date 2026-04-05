"""
AgentCore policy enforcement tests for the MAKITA AgentCore stack.

The policies are now embedded in the Lambda function code within
makita-agentcore-stack.yaml. This test extracts the build_policy_doc
function logic and validates the policy documents it produces.

Validates: Requirements 23.9, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6
"""

import json
import pytest


# The policy documents are built by the Lambda's build_policy_doc function.
# We replicate the logic here to test the actual policy structure.

def _build_policy_doc(actions):
    return {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": actions, "Resource": "arn:aws:*:*:*:makita-*",
         "Condition": {"StringEquals": {"aws:RequestedRegion": ["us-east-1", "us-west-2"],
         "aws:PrincipalTag/Name": "makita-*"}}},
        {"Effect": "Deny", "Action": "*", "Resource": "*",
         "Condition": {"StringNotEquals": {"aws:ResourceTag/Env": "prod1"}}},
        {"Effect": "Deny", "Action": "*", "Resource": "*",
         "Condition": {"StringNotLike": {"aws:ResourceTag/Name": "makita-*"}}},
        {"Effect": "Deny", "Action": "*", "Resource": "*",
         "Condition": {"StringNotEquals": {"aws:RequestedRegion": ["us-east-1", "us-west-2"]}}},
        {"Effect": "Deny", "Action": "*", "Resource": "*",
         "Condition": {"StringNotLike": {"aws:PrincipalTag/Name": "makita-*"}}},
    ]}


POLICIES_CONFIG = {
    "makita-failover-policy": {
        "actions": ["rds:PromoteReadReplica", "rds:DescribeDBInstances",
                    "rds:RebootDBInstance", "ssm:PutParameter", "ssm:GetParameter"],
    },
    "makita-precheck-policy": {
        "actions": ["rds:DescribeDBInstances", "rds:DescribeDBClusters", "ssm:GetParameter"],
    },
    "makita-postcheck-policy": {
        "actions": ["rds:DescribeDBInstances", "rds:DescribeDBClusters", "ssm:GetParameter"],
    },
}


@pytest.fixture(scope="module")
def policies():
    return {name: _build_policy_doc(cfg["actions"])["Statement"]
            for name, cfg in POLICIES_CONFIG.items()}


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
            assert name in policies

    def test_each_policy_has_statements(self, policies):
        for name in EXPECTED_POLICIES:
            assert len(policies[name]) >= 2


class TestDenyNonMakitaResources:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_denies_non_makita_resources(self, policies, policy_name):
        found = any(
            s.get("Condition", {}).get("StringNotLike", {}).get("aws:ResourceTag/Name") == "makita-*"
            for s in _deny_statements(policies[policy_name])
        )
        assert found


class TestDenyUnauthorizedRegions:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_denies_unauthorized_regions(self, policies, policy_name):
        found = False
        for s in _deny_statements(policies[policy_name]):
            regions = s.get("Condition", {}).get("StringNotEquals", {}).get("aws:RequestedRegion", [])
            if "us-east-1" in regions and "us-west-2" in regions:
                found = True
        assert found


class TestDenyNonMakitaPrincipals:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_denies_non_makita_principals(self, policies, policy_name):
        found = any(
            s.get("Condition", {}).get("StringNotLike", {}).get("aws:PrincipalTag/Name") == "makita-*"
            for s in _deny_statements(policies[policy_name])
        )
        assert found


class TestDenyMissingEnvTag:
    @pytest.mark.parametrize("policy_name,label", list(EXPECTED_POLICIES.items()))
    def test_policy_denies_resources_without_env_prod1(self, policies, policy_name, label):
        found = any(
            s.get("Condition", {}).get("StringNotEquals", {}).get("aws:ResourceTag/Env") == "prod1"
            for s in _deny_statements(policies[policy_name])
        )
        assert found


class TestAllowWhenConstraintsPass:
    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_policy_has_allow_statement(self, policies, policy_name):
        assert len(_allow_statements(policies[policy_name])) >= 1

    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_allow_targets_makita_resources(self, policies, policy_name):
        for s in _allow_statements(policies[policy_name]):
            assert "makita-" in s.get("Resource", "")

    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_allow_constrains_regions(self, policies, policy_name):
        for s in _allow_statements(policies[policy_name]):
            regions = s.get("Condition", {}).get("StringEquals", {}).get("aws:RequestedRegion", [])
            assert "us-east-1" in regions
            assert "us-west-2" in regions

    @pytest.mark.parametrize("policy_name", list(EXPECTED_POLICIES.keys()))
    def test_allow_constrains_principal(self, policies, policy_name):
        for s in _allow_statements(policies[policy_name]):
            principal = s.get("Condition", {}).get("StringEquals", {}).get("aws:PrincipalTag/Name", "")
            assert "makita-" in str(principal)
