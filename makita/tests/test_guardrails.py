"""
Bedrock Guardrails enforcement tests for the MAKITA CloudFormation template.

Validates the Bedrock Guardrail resources in infrastructure/workloads/postgresql/makita-postgresql-stack.yaml
by parsing the YAML directly and asserting on content policy, topic policy,
prompt injection detection, and blocked messaging configuration.

Validates: Requirement 23.10
"""

import yaml
import pytest
from pathlib import Path


TEMPLATE_PATH = Path(__file__).parent.parent / "infrastructure" / "workloads" / "postgresql" / "makita-postgresql-stack.yaml"


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
def resources(template):
    """Extract the Resources section from the template."""
    return template.get("Resources", {})


@pytest.fixture(scope="module")
def guardrails(resources):
    """Extract all Bedrock Guardrail resources."""
    return {
        k: v for k, v in resources.items()
        if v["Type"] == "AWS::Bedrock::Guardrail"
    }


# Expected guardrail logical IDs and their Name property values
EXPECTED_GUARDRAILS = {
    "MakitaFailoverGuardrail": "makita-failover-guardrail",
    "MakitaPrecheckGuardrail": "makita-precheck-guardrail",
    "MakitaPostcheckGuardrail": "makita-postcheck-guardrail",
}


# =========================================================================
# Guardrail existence and naming
# =========================================================================

class TestGuardrailExistence:
    """Validate all three Bedrock Guardrail resources exist with makita- prefix."""

    def test_three_guardrails_exist(self, guardrails):
        assert len(guardrails) >= 3, (
            f"Expected at least 3 Bedrock Guardrail resources, found {len(guardrails)}"
        )

    @pytest.mark.parametrize(
        "logical_id,expected_name",
        list(EXPECTED_GUARDRAILS.items()),
    )
    def test_guardrail_name_starts_with_makita(
        self, guardrails, logical_id, expected_name
    ):
        assert logical_id in guardrails, (
            f"Missing guardrail resource: {logical_id}"
        )
        name = guardrails[logical_id]["Properties"]["Name"]
        assert name.startswith("makita-"), (
            f"Guardrail '{logical_id}' Name '{name}' missing makita- prefix"
        )
        assert name == expected_name


# =========================================================================
# Prompt injection detection and blocking (Requirement 23.10)
# =========================================================================

class TestPromptInjectionDetection:
    """Validate prompt injection detection via PROMPT_ATTACK content filter.

    Validates: Requirement 23.10 — prompt injection attempts are detected
    and blocked.
    """

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_content_policy_has_prompt_attack_filter(self, guardrails, logical_id):
        """Each guardrail must include a PROMPT_ATTACK filter in ContentPolicyConfig."""
        props = guardrails[logical_id]["Properties"]
        filters = props["ContentPolicyConfig"]["FiltersConfig"]
        filter_types = [f["Type"] for f in filters]
        assert "PROMPT_ATTACK" in filter_types, (
            f"Guardrail '{logical_id}' missing PROMPT_ATTACK content filter"
        )

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_prompt_attack_input_strength_is_high(self, guardrails, logical_id):
        """PROMPT_ATTACK filter must have HIGH InputStrength to block injection."""
        props = guardrails[logical_id]["Properties"]
        filters = props["ContentPolicyConfig"]["FiltersConfig"]
        prompt_attack = [f for f in filters if f["Type"] == "PROMPT_ATTACK"]
        assert len(prompt_attack) == 1
        assert prompt_attack[0]["InputStrength"] == "HIGH", (
            f"Guardrail '{logical_id}' PROMPT_ATTACK InputStrength is not HIGH"
        )


# =========================================================================
# Malicious prompt blocking (Requirement 23.10)
# =========================================================================

class TestMaliciousPromptBlocking:
    """Validate content filtering blocks malicious prompts.

    Validates: Requirement 23.10 — malicious prompts are blocked via
    content policy filters for harmful categories.
    """

    HARMFUL_CATEGORIES = {"SEXUAL", "VIOLENCE", "HATE", "INSULTS", "MISCONDUCT"}

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_all_harmful_categories_present(self, guardrails, logical_id):
        """Each guardrail must filter all harmful content categories."""
        props = guardrails[logical_id]["Properties"]
        filters = props["ContentPolicyConfig"]["FiltersConfig"]
        filter_types = {f["Type"] for f in filters}
        missing = self.HARMFUL_CATEGORIES - filter_types
        assert not missing, (
            f"Guardrail '{logical_id}' missing harmful content filters: {missing}"
        )

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_harmful_filters_have_high_strength(self, guardrails, logical_id):
        """All harmful content filters must use HIGH input and output strength."""
        props = guardrails[logical_id]["Properties"]
        filters = props["ContentPolicyConfig"]["FiltersConfig"]
        for f in filters:
            if f["Type"] in self.HARMFUL_CATEGORIES:
                assert f["InputStrength"] == "HIGH", (
                    f"Guardrail '{logical_id}' filter {f['Type']} "
                    f"InputStrength is {f['InputStrength']}, expected HIGH"
                )
                assert f["OutputStrength"] == "HIGH", (
                    f"Guardrail '{logical_id}' filter {f['Type']} "
                    f"OutputStrength is {f['OutputStrength']}, expected HIGH"
                )


# =========================================================================
# Topic policy — restrict to DR operations (Requirement 23.10)
# =========================================================================

class TestTopicPolicyConfig:
    """Validate topic policy restricts guardrails to DR operations only."""

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_topic_policy_exists(self, guardrails, logical_id):
        """Each guardrail must have a TopicPolicyConfig."""
        props = guardrails[logical_id]["Properties"]
        assert "TopicPolicyConfig" in props, (
            f"Guardrail '{logical_id}' missing TopicPolicyConfig"
        )

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_topic_policy_has_deny_topic(self, guardrails, logical_id):
        """Each guardrail must have at least one DENY topic for non-DR operations."""
        props = guardrails[logical_id]["Properties"]
        topics = props["TopicPolicyConfig"]["TopicsConfig"]
        deny_topics = [t for t in topics if t["Type"] == "DENY"]
        assert len(deny_topics) >= 1, (
            f"Guardrail '{logical_id}' has no DENY topics in TopicPolicyConfig"
        )

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_deny_topic_has_examples(self, guardrails, logical_id):
        """Each DENY topic must include examples of blocked operations."""
        props = guardrails[logical_id]["Properties"]
        topics = props["TopicPolicyConfig"]["TopicsConfig"]
        for topic in topics:
            if topic["Type"] == "DENY":
                examples = topic.get("Examples", [])
                assert len(examples) >= 1, (
                    f"Guardrail '{logical_id}' DENY topic '{topic['Name']}' "
                    "has no examples"
                )


# =========================================================================
# Blocked messaging — structured error responses (Requirement 23.10)
# =========================================================================

class TestBlockedMessaging:
    """Validate BlockedInputMessaging and BlockedOutputsMessaging properties.

    Validates: Requirement 23.10 — policy violations return structured
    error responses.
    """

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_blocked_input_messaging_set(self, guardrails, logical_id):
        """Each guardrail must have a non-empty BlockedInputMessaging property."""
        props = guardrails[logical_id]["Properties"]
        msg = props.get("BlockedInputMessaging", "")
        assert msg and len(msg.strip()) > 0, (
            f"Guardrail '{logical_id}' missing or empty BlockedInputMessaging"
        )

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_blocked_outputs_messaging_set(self, guardrails, logical_id):
        """Each guardrail must have a non-empty BlockedOutputsMessaging property."""
        props = guardrails[logical_id]["Properties"]
        msg = props.get("BlockedOutputsMessaging", "")
        assert msg and len(msg.strip()) > 0, (
            f"Guardrail '{logical_id}' missing or empty BlockedOutputsMessaging"
        )

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_blocked_input_messaging_mentions_guardrail(self, guardrails, logical_id):
        """BlockedInputMessaging should reference the guardrail policy."""
        props = guardrails[logical_id]["Properties"]
        msg = props["BlockedInputMessaging"].lower()
        assert "guardrail" in msg or "blocked" in msg or "policy" in msg, (
            f"Guardrail '{logical_id}' BlockedInputMessaging does not "
            "reference guardrail/blocked/policy"
        )

    @pytest.mark.parametrize("logical_id", list(EXPECTED_GUARDRAILS.keys()))
    def test_blocked_outputs_messaging_mentions_guardrail(self, guardrails, logical_id):
        """BlockedOutputsMessaging should reference the guardrail policy."""
        props = guardrails[logical_id]["Properties"]
        msg = props["BlockedOutputsMessaging"].lower()
        assert "guardrail" in msg or "blocked" in msg or "policy" in msg, (
            f"Guardrail '{logical_id}' BlockedOutputsMessaging does not "
            "reference guardrail/blocked/policy"
        )
